"""Invariants of the browser-facing API contract, enforced by parsing it.

WHY THIS FILE EXISTS. `docs/api/openapi.yaml` is an ARCHITECTURAL CONTRACT for a beta that does not
exist: no server has been built, no endpoint has ever been called. Until now it was validated only
by whoever happened to run a parser by hand — the Commit 2 report recorded that its parse and its
`$ref` resolution were local ad hoc checks and that no test read the file. A specification nothing
executes and nothing validates drifts silently, and this one is load-bearing: the UX
specification, the data dictionary and the roadmap are all written to agree with it.

UPDATED IN PHASE 2, BECAUSE PART OF IT IS NOW REAL. The parser-review application is implemented
and served by `packages/review_api`. This file therefore does one thing it could not do before: it
compares the document against the application's OWN ROUTE TABLE in BOTH directions. An operation
marked IMPLEMENTED that no route serves fails the build, and a route the application serves that
the document does not describe fails it too. A one-directional check would let the specification
quietly fall behind the code, which is the failure this whole file exists to prevent.

WHAT THIS STILL DELIBERATELY DOES NOT DO. It does not mock or serve the API, and it asserts nothing
about what any operation should RETURN. The beta response shapes remain provisional and are
redesigned once real model artifacts exist.

THE JSON HERE IS CORRECT AND IS NOT A BOUNDARY VIOLATION. This document describes browser-facing
JSON, and a browser is not a model (ADR-0013). The LLM content boundary governs model-visible
content, which never includes any payload defined in this file.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from ruamel.yaml import YAML

REPO_ROOT = Path(__file__).resolve().parents[2]
SPEC = REPO_ROOT / "docs" / "api" / "openapi.yaml"

pytestmark = pytest.mark.architecture

# Only these two statuses may appear.
#
# `IMPLEMENTED` WAS ADDED IN PHASE 2, AND ADDING IT WAS THE EDIT THAT HAD TO BE JUSTIFIED — which
# is exactly why the set was written this way. It is justified by
# `test_every_implemented_operation_is_actually_served`, which makes the value checkable rather
# than a claim: an operation may call itself implemented only while a real route answers it.
ALLOWED_STATUSES = frozenset({"PLANNED", "IMPLEMENTED"})

HTTP_METHODS = frozenset({"get", "put", "post", "delete", "options", "head", "patch", "trace"})


@pytest.fixture(scope="module")
def spec() -> dict[str, Any]:
    return YAML(typ="safe", pure=True).load(SPEC.read_text(encoding="utf-8"))


def _operations(spec: dict[str, Any]) -> list[tuple[str, str, dict[str, Any]]]:
    """(path, method, operation) for every operation in the document."""
    found = []
    for path, item in (spec.get("paths") or {}).items():
        if not isinstance(item, dict):
            continue
        for method, operation in item.items():
            if method.lower() in HTTP_METHODS and isinstance(operation, dict):
                found.append((path, method.lower(), operation))
    return found


def _refs(node: Any, trail: str = "") -> list[tuple[str, str]]:
    """Every `$ref` in the document, with the JSON-pointer trail that reached it."""
    found: list[tuple[str, str]] = []
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "$ref" and isinstance(value, str):
                found.append((trail or "/", value))
            else:
                found.extend(_refs(value, f"{trail}/{key}"))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            found.extend(_refs(value, f"{trail}/{index}"))
    return found


def _resolve(spec: dict[str, Any], pointer: str) -> Any:
    """Walk a local JSON pointer, returning a sentinel when any segment is missing."""
    missing = object()
    current: Any = spec
    for raw in pointer.lstrip("#/").split("/"):
        segment = raw.replace("~1", "/").replace("~0", "~")
        if isinstance(current, dict) and segment in current:
            current = current[segment]
        elif isinstance(current, list) and segment.isdigit() and int(segment) < len(current):
            current = current[int(segment)]
        else:
            return missing
    return current


# --- anti-vacuity ------------------------------------------------------------------------------


def test_the_specification_parses_and_has_something_to_check(spec: dict[str, Any]) -> None:
    """A guard over an empty or unparsed document enforces nothing."""
    assert SPEC.is_file(), "docs/api/openapi.yaml must exist for this guard to be live"
    assert isinstance(spec, dict), "the specification did not parse to a mapping"
    assert len(_operations(spec)) >= 10, "too few operations for this suite to be meaningful"
    assert len(_refs(spec)) >= 20, "too few references for the resolution check to be meaningful"
    assert spec.get("components", {}).get("schemas"), "no component schemas to resolve against"


# --- the document itself -----------------------------------------------------------------------


def test_the_openapi_version_is_declared_and_supported(spec: dict[str, Any]) -> None:
    """A missing or 2.x version silently changes what every other assertion means."""
    version = spec.get("openapi")
    assert isinstance(version, str), "no `openapi:` version is declared"
    major, minor, *_ = version.split(".")
    assert (int(major), int(minor)) >= (3, 1), f"OpenAPI {version} is below the declared 3.1"


def test_every_local_reference_resolves(spec: dict[str, Any]) -> None:
    """An unresolved `$ref` is a specification that cannot be read by any tool, including a human.

    Reported with the trail that reached it, because `#/components/schemas/Foo` appearing four
    times says nothing about which operation is broken.
    """
    missing = object()
    unresolved = []
    for trail, ref in _refs(spec):
        if not ref.startswith("#/"):
            continue
        if _resolve(spec, ref) is missing:
            unresolved.append(f"{trail} -> {ref}")
    assert not unresolved, f"unresolved local references: {unresolved}"


def test_no_reference_leaves_the_document(spec: dict[str, Any]) -> None:
    """An external `$ref` makes the contract depend on a file or a URL nothing pins."""
    external = [f"{trail} -> {ref}" for trail, ref in _refs(spec) if not ref.startswith("#/")]
    assert not external, f"external references are not permitted: {external}"


def test_no_component_schema_is_orphaned(spec: dict[str, Any]) -> None:
    """A schema nothing references is a shape the contract does not actually promise."""
    referenced = {ref for _, ref in _refs(spec)}
    orphans = [
        name
        for name in spec["components"]["schemas"]
        if f"#/components/schemas/{name}" not in referenced
    ]
    assert not orphans, f"component schemas defined but never referenced: {orphans}"


# --- the document must not claim something exists --------------------------------------------


def test_no_active_server_is_declared(spec: dict[str, Any]) -> None:
    """NO SERVER EXISTS. A `servers:` entry is a claim that one does.

    An empty list is accepted and a commented-out block is fine; a populated entry is not. This is
    the single most misleading thing this file could contain, because tooling turns a server URL
    into a working "try it" button for an endpoint that has never been built.
    """
    servers = spec.get("servers")
    assert not servers, (
        f"the specification declares {len(servers or [])} server(s): {servers}. No server has been "
        "built or deployed, and naming one implies otherwise."
    )


def test_every_operation_declares_an_honest_implementation_status(spec: dict[str, Any]) -> None:
    """rules.md section 13: never describe planned behaviour as implemented.

    Every operation must say what it is. An operation with no status reads as built, which is the
    default this check exists to remove.
    """
    wrong = []
    for path, method, operation in _operations(spec):
        status = operation.get("x-implementation-status")
        if status not in ALLOWED_STATUSES:
            wrong.append(f"{method.upper()} {path}: {status!r}")
    assert not wrong, (
        "operations must be marked with one of "
        f"{sorted(ALLOWED_STATUSES)} while unimplemented: {wrong}"
    )


def test_the_document_states_plainly_what_is_and_is_not_implemented(spec: dict[str, Any]) -> None:
    """A status extension is machine-readable. A human reads the description first.

    The document used to say NOTHING was implemented, and that was true. Part of it now is, so the
    assertion changed from "must say nothing is built" to "must say plainly which half is which".
    The version still may not look released: a partially implemented contract carrying 1.0.0 would
    imply a stability nothing here has.
    """
    info = spec.get("info", {})
    text = f"{info.get('summary', '')} {info.get('description', '')}".upper()
    assert "NOT IMPLEMENTED" in text, "info must still name the half that has not been built"
    assert "IMPLEMENTED" in text, "info must name the half that has"
    version = str(info.get("version", ""))
    assert version.startswith("0."), (
        f"a partly implemented contract must not carry a released-looking version: {version}"
    )


def test_every_implemented_operation_is_actually_served(spec: dict[str, Any]) -> None:
    """The specification and the application must not be able to drift apart.

    Checked in BOTH directions on purpose. A one-directional check catches a specification that
    over-claims and misses one that has fallen behind — and a contract missing an endpoint the
    application really serves is the more dangerous of the two, because nothing else in the
    repository would ever notice.

    The application is constructed with no service, no worker and no policy. Registration only
    binds methods to paths; nothing is invoked, so this needs no store, no catalog, no snapshot and
    no network.
    """
    from packages.review_api.handlers import ReviewApp

    served = set(ReviewApp(service=None, worker=None, policy=None).router.implemented())
    declared = {
        (method.upper(), path)
        for path, method, operation in _operations(spec)
        if operation.get("x-implementation-status") == "IMPLEMENTED"
    }
    assert served, "the application registered no routes; this guard would enforce nothing"
    missing_from_spec = sorted(served - declared)
    missing_from_app = sorted(declared - served)
    assert not missing_from_spec, (
        "the application serves routes the contract does not describe as IMPLEMENTED: "
        f"{missing_from_spec}"
    )
    assert not missing_from_app, (
        f"the contract claims routes the application does not serve: {missing_from_app}"
    )


def test_planned_operations_are_not_served_by_the_application(spec: dict[str, Any]) -> None:
    """A PLANNED operation that quietly acquired a route is an unlabelled implementation."""
    from packages.review_api.handlers import ReviewApp

    served = set(ReviewApp(service=None, worker=None, policy=None).router.implemented())
    planned = {
        (method.upper(), path)
        for path, method, operation in _operations(spec)
        if operation.get("x-implementation-status") == "PLANNED"
    }
    assert planned, "no PLANNED operations remain; this guard would enforce nothing"
    overlap = sorted(served & planned)
    assert not overlap, f"these operations are served but still marked PLANNED: {overlap}"


def test_no_operation_exposes_a_provider_credential_or_endpoint(spec: dict[str, Any]) -> None:
    """SECURITY-INVARIANT: the browser never calls a model provider and never holds a credential.

    All model access is server-side through packages/llm_gateway. A field carrying a provider
    endpoint or key material in a browser-facing payload would move that boundary.
    """
    raw = SPEC.read_text(encoding="utf-8").lower()
    for forbidden in (
        "aws_access_key",
        "aws_secret",
        "aws_session_token",
        "bedrock-runtime",
        "secret_access_key",
    ):
        assert forbidden not in raw, f"the browser-facing contract mentions {forbidden!r}"
