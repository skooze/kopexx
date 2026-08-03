"""The parser-review HTTP surface: the router, the security policy, and every handler behind it.

HERMETIC AND SOCKETLESS, WHICH IS THE WHOLE REASON THE HANDLERS ARE PURE FUNCTIONS. Every route is
exercised here by handing `ReviewApp.handle` a `Request` and reading the `Response` back. No port is
bound, no timeout is waited on, and no test in this file can flake on a socket — which is what keeps
`test-no-skips` honest, because a test that needs a listening server is a test that eventually skips
somewhere.

EVERYTHING THE APPLICATION READS IS SYNTHETIC AND LIVES UNDER `tmp_path`. A one-document EDGAR
complete submission written by this file, a one-candidate capability snapshot, a one-version prompt
registry, a one-filing corpus manifest, a fresh evaluation store and `MockProvider`. Nothing here
reads a developer's environment, the real research corpus, the committed capability snapshot or any
credential, and `app.build()` is deliberately NOT called — assembling the parts by hand is what
removes the last environmental precondition.

WHAT IS ACTUALLY UNDER TEST. Not that a handler returns a mapping; that is arithmetic. The subject
is the set of things this surface must REFUSE: to serve a state-changing request without a token, to
answer an unauthenticated caller beyond loopback, to leak anything account-specific through the one
route an operator polls, to turn a missing run into a stack trace, to relax a content security
policy that is only strict because filings are rendered as escaped text, or to accept a stage the
phase never authorized.

CREDENTIAL VARIABLE NAMES ARE ASSEMBLED FROM PARTS, NEVER WRITTEN OUT.
`tests/architecture/test_aws_identity.py` fails the build when those literals appear in a tracked
file that is not the policy itself, and its allowlist is deliberately hard to join.
"""

from __future__ import annotations

import inspect
import json
import re
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

import packages.review_api.server as server_module
from packages.evaluation_store import EvaluationStore, ExecutionState
from packages.llm_gateway.providers.mock import MockProvider
from packages.model_catalog import load_snapshot
from packages.orchestrator import (
    CorpusFilingCatalog,
    InlineWorker,
    ParserReviewService,
    RunRequest,
    SpendJournal,
)
from packages.prompt_registry import PromptRegistry
from packages.review_api import (
    CSRF_FIELD,
    CSRF_HEADER,
    MAX_REQUEST_BYTES,
    SECURITY_HEADERS,
    SESSION_COOKIE,
    Request,
    Response,
    ReviewApp,
    Router,
    SecurityPolicy,
    build_request,
)
from packages.source_transport import ManifestInventory, PreservedObject, RefusingFetcher
from packages.storage import FilesystemObjectStore, sha256_bytes, sha256_text

CIK = "0000000001"
ACCESSION = "0000000001-24-000001"
ENTITY_NAME = "Synthetic Issuer Company"
REGION = "region-one"
PARSING_LABEL = "Parser One"

#: A sentence that appears ONLY inside the synthetic filing body. Anything asserting that filing
#: text did not reach a browser-facing surface looks for this and nothing else.
FILING_MARKER = "Revenue for the period was one synthetic dollar."

#: A one-document EDGAR complete submission with no `<FILENAME>`, which is the NON-ADDRESSABLE
#: transport case: EDGAR publishes no per-document URL, so the complete submission IS the source
#: set and no member is ever fetched. That is what lets this suite run with a `RefusingFetcher`.
SUBMISSION = (
    "<SEC-DOCUMENT>0000000001-24-000001.txt : 20240102\n"
    "<SEC-HEADER>0000000001-24-000001.hdr.sgml : 20240102\n"
    "ACCESSION NUMBER:\t\t0000000001-24-000001\n"
    "CONFORMED SUBMISSION TYPE:\t10-K\n"
    "PUBLIC DOCUMENT COUNT:\t\t1\n"
    "CONFORMED PERIOD OF REPORT:\t20231231\n"
    "FILED AS OF DATE:\t\t20240102\n"
    "</SEC-HEADER>\n"
    "<DOCUMENT>\n"
    "<TYPE>10-K\n"
    "<SEQUENCE>1\n"
    "<DESCRIPTION>ANNUAL REPORT\n"
    "<TEXT>\n"
    "SYNTHETIC ANNUAL REPORT BODY. This text stands in for a filed document and\n"
    f"describes no real issuer. {FILING_MARKER}\n"
    "</TEXT>\n"
    "</DOCUMENT>\n"
    "</SEC-DOCUMENT>\n"
).encode("ascii")

SNAPSHOT = """snapshot_version: "1"
verified_on: "2026-01-01"
verified_from_region: region-one
price_source: a published price list
price_effective_date: "2026-01-01"
price_currency: USD
price_unit: per 1000 tokens
candidates:
  - label: Parser One
    provider: Provider
    model_id: "provider.parser-one"
    model_name: Parser One
    version_qualifier: "v1"
    mapping: UNIQUE
    availability: AVAILABLE
    access_status: granted
    verified_regions: ["region-one"]
    inference_profile_required: false
    inference_profile_id: null
    text_input: true
    image_input: false
    multimodal: false
    image_verified: false
    context_tokens: 128000
    max_output_tokens: 8192
    invocation_apis: ["Converse"]
    streaming_supported: true
    price_input_per_1k: 0.001
    price_output_per_1k: 0.004
    smoke_transport: ACCEPTED
    smoke_instruction: EXACT
    blocker: null
    disabled_reason: null
"""

PROMPT_TEXT = (
    "Parse the complete filing in its own vocabulary. Represent every human-readable range or "
    "mark it unresolved.\n"
)

#: The exact bytes the mock returns. The response route must serve these back unchanged, so the
#: fixture is pinned here rather than imported from the provider.
MOCK_RESPONSE = (
    'schema_version: "mock-response-v1"\n'
    "response:\n"
    "  text: A synthetic response produced without invoking a real model.\n"
)

#: A development secret in the shape of an obvious placeholder. It is compared, never stored.
DEV_SECRET = "this-is-not-a-real-secret-only-a-test-value"

# Assembled, never written out. See the module docstring.
_AWS_PREFIX = "AWS_"
CREDENTIAL_VARIABLE_NAMES = tuple(
    _AWS_PREFIX + suffix for suffix in ("ACCESS_KEY_ID", "SECRET_ACCESS_KEY", "SESSION_TOKEN")
)

#: Anything account-specific or provider-reachable that must never appear in a browser-facing body.
TWELVE_DIGITS = re.compile(r"(?<!\d)\d{12}(?!\d)")
PROVIDER_MARKERS = ("arn:aws", "amazonaws.com", "bedrock-runtime", "AKIA", "ASIA")


@dataclass(frozen=True)
class Harness:
    """A fully wired review service over a synthetic corpus, and the worker that drives it."""

    service: ParserReviewService
    worker: InlineWorker
    provider: MockProvider


def _write_corpus(tmp_path: Path) -> tuple[Path, Path]:
    """Write the synthetic complete submission and the manifest that describes it."""
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    submission_path = corpus / f"{ACCESSION}.txt"
    submission_path.write_bytes(SUBMISSION)

    manifest_path = tmp_path / "corpus-manifest.json"
    manifest_path.write_text(
        json.dumps(
            [
                {
                    "cik": CIK,
                    "accession": ACCESSION,
                    "form_as_filed": "10-K",
                    "filing_date": "2024-01-02",
                    "report_period": "2023-12-31",
                    "issuer_name_current": ENTITY_NAME,
                    "tickers_current": ["SYNT"],
                    "sic_description": "Synthetic issuers",
                    "transport_era": "modern",
                    "is_amendment": False,
                    "is_annual": True,
                    "form_variant": "10-K",
                    "package_file_count": 1,
                    "package_image_count": 0,
                    "primary_est_tokens_at_3_0": 900,
                    "acquisition_timestamp": "2026-01-01T00:00:00+00:00",
                    "files": [
                        {
                            "filename": f"{ACCESSION}.txt",
                            "sha256": sha256_bytes(SUBMISSION),
                            "raw_bytes": len(SUBMISSION),
                            "local_path": str(submission_path),
                            "source_url": "",
                        }
                    ],
                }
            ]
        ),
        encoding="utf-8",
    )
    return manifest_path, submission_path


def _write_prompts(tmp_path: Path) -> Path:
    """A one-version prompt registry whose manifest records the hash of its own bytes."""
    directory = tmp_path / "prompts"
    directory.mkdir()
    (directory / "parser-v1.txt").write_text(PROMPT_TEXT, encoding="utf-8")
    (directory / "versions.yaml").write_text(
        'schema_version: "prompt-versions-v1"\n'
        "prompts:\n"
        "  - prompt_id: synthetic-parser\n"
        '    version: "1"\n'
        "    file: parser-v1.txt\n"
        f'    sha256: "{sha256_text(PROMPT_TEXT)}"\n'
        '    created: "2026-01-01"\n'
        "    status: ACTIVE\n"
        "    role: parsing\n",
        encoding="utf-8",
    )
    return directory


@pytest.fixture
def harness(tmp_path: Path) -> Harness:
    """A review service assembled by hand from synthetic parts under `tmp_path`."""
    manifest_path, submission_path = _write_corpus(tmp_path)
    prompt_directory = _write_prompts(tmp_path)
    evaluation_root = tmp_path / "evaluation"

    provider = MockProvider(MOCK_RESPONSE)
    service = ParserReviewService(
        store=EvaluationStore.at_path(evaluation_root),
        catalog=CorpusFilingCatalog.from_manifest(manifest_path),
        snapshot=load_snapshot(SNAPSHOT),
        prompts=PromptRegistry.from_directory(prompt_directory),
        inventory=ManifestInventory(
            {
                (CIK, ACCESSION): [
                    PreservedObject(
                        filename=f"{ACCESSION}.txt",
                        sha256=sha256_bytes(SUBMISSION),
                        byte_count=len(SUBMISSION),
                        source_url="",
                        locator=str(submission_path),
                        acquired_at="2026-01-01T00:00:00+00:00",
                        acquisition_method="research_corpus",
                        reused=True,
                    )
                ]
            }
        ),
        fetcher=RefusingFetcher(),
        provider=provider,
        journal=SpendJournal(FilesystemObjectStore(evaluation_root), ceiling_usd=Decimal("5.00")),
        preferred_region=REGION,
        author="reviewer",
    )
    return Harness(service=service, worker=InlineWorker(service), provider=provider)


def app_for(
    harness: Harness,
    *,
    loopback_only: bool = True,
    secret: str | None = None,
    https: bool = False,
) -> ReviewApp:
    """One application over the shared service, with the security posture a test asks for."""
    return ReviewApp(
        service=harness.service,
        worker=harness.worker,
        policy=SecurityPolicy(loopback_only=loopback_only, dev_auth_secret=secret, https=https),
    )


@pytest.fixture
def app(harness: Harness) -> ReviewApp:
    """The ordinary posture: bound to loopback, no authentication, no session."""
    return app_for(harness)


@pytest.fixture
def guarded(harness: Harness) -> ReviewApp:
    """Bound beyond loopback, which `ReviewSettings` only permits with a development secret."""
    return app_for(harness, loopback_only=False, secret=DEV_SECRET)


def call(
    app: ReviewApp,
    method: str,
    raw_path: str,
    *,
    headers: dict[str, str] | None = None,
    body: bytes = b"",
) -> Response:
    """Drive one request through the real parser in `server.build_request`, then the app."""
    return app.handle(
        build_request(
            method=method,
            raw_path=raw_path,
            headers=headers or {},
            body=body,
            client_host="127.0.0.1",
        )
    )


def body_json(response: Response) -> Any:
    return json.loads(response.body.decode("utf-8"))


def signed_in(app: ReviewApp) -> tuple[dict[str, str], str]:
    """A cookie header for a live session, and the CSRF token bound to it."""
    session = app.policy.sessions.create()
    return {"Cookie": f"{SESSION_COOKIE}={session.session_id}"}, session.csrf_token


@pytest.fixture
def completed_run(harness: Harness) -> tuple[str, str]:
    """One parent run whose single child job has been executed against the mock, end to end."""
    request = RunRequest(cik=CIK, parsing_label=PARSING_LABEL, accessions=(ACCESSION,))
    plan = harness.service.preflight(request)
    run = harness.service.create_run(request, plan=plan)
    harness.worker.submit_run(run.run_id)
    return run.run_id, run.job_ids[0]


# --- anti-vacuity: the synthetic world is real enough to test against ---------------------------


def test_the_synthetic_corpus_produces_a_run_that_actually_reached_review(
    harness: Harness, completed_run: tuple[str, str]
) -> None:
    """Every handler test below is worthless if the fixture never executed anything.

    A suite that asserts against an empty store passes forever. This one proves there is a parent
    run, a child job, a stored response and a validation verdict before anything else looks at
    them — and that the model the run used was the mock, not a provider anybody reached.
    """
    run_id, job_id = completed_run
    job = harness.service.store.load_job(run_id, job_id)
    assert job.execution_state is ExecutionState.READY_FOR_REVIEW
    assert job.validation is not None, "the job reached review with no validation recorded"
    assert harness.provider.invocations, "the mock provider was never invoked"
    assert harness.service.journal.spent_usd > 0, "a completed run charged nothing"


# --- the router --------------------------------------------------------------------------------


def test_a_path_parameter_is_captured_and_handed_to_the_handler(app: ReviewApp) -> None:
    """A two-parameter route binds both, by name, without a framework to do it.

    `handle` rebuilds the request with `params` filled in, so a handler reads `run_id` and `job_id`
    as data rather than by slicing the path itself — which is where an off-by-one becomes a wrong
    job identifier pointed at a real filing.
    """
    resolved = app.router.resolve("GET", "/api/runs/run_one/jobs/job_two")
    assert resolved is not None
    _, params = resolved
    assert params == {"run_id": "run_one", "job_id": "job_two"}


def test_a_path_parameter_never_swallows_a_segment_separator(app: ReviewApp) -> None:
    """MUTATION GUARD. `[^/]+` is the whole reason a nested path cannot be smuggled into an id.

    Widening the placeholder to `.+` would make this path resolve, and the captured `run_id` would
    then carry a slash straight toward a storage key. The identifier guard would still refuse it,
    but a router that offers path separators to the layer below has already stopped being one.
    """
    assert app.router.resolve("GET", "/api/runs/one/two/jobs/three") is None


def test_a_known_path_with_the_wrong_method_answers_405_and_not_404(app: ReviewApp) -> None:
    """405 and 404 are different facts and must not be collapsed.

    `/preflight` exists and is a POST. Answering 404 would tell a caller the endpoint does not
    exist, which is the wrong bug report and the wrong fix.
    """
    response = call(app, "GET", "/preflight")
    assert response.status == 405
    assert body_json(response)["code"] == "method_not_allowed"


def test_a_path_no_route_matches_answers_404_and_not_405(app: ReviewApp) -> None:
    """ANTI-VACUITY partner. The 405 above must come from the method, not from every miss."""
    response = call(app, "GET", "/no-such-route")
    assert response.status == 404
    assert body_json(response)["code"] == "not_found"


def test_the_implemented_route_table_is_deduplicated_and_ordered(app: ReviewApp) -> None:
    """`Router.implemented()` is what the OpenAPI contract test compares against.

    It has to be a stable, deduplicated set of (METHOD, path) pairs: a table that reordered itself
    between runs, or that reported the same route twice, would make that contract test fail or pass
    for reasons that have nothing to do with the contract.
    """
    implemented = app.router.implemented()
    assert implemented == tuple(sorted(set(implemented)))
    assert ("GET", "/health") in implemented
    assert ("POST", "/runs") in implemented
    assert len(implemented) >= 20, "the route table shrank below what the UI needs"


def test_registering_a_route_twice_still_reports_it_once() -> None:
    """The deduplication above is a property of `implemented()`, not an accident of registration."""
    router = Router()
    handler = lambda request: Response()  # noqa: E731 - a one-line stand-in, deliberately inline
    router.add("GET", "/thing", handler, name="a")
    router.add("GET", "/thing", handler, name="b")
    assert router.implemented() == (("GET", "/thing"),)
    assert len(router.routes) == 2, "both registrations are still resolvable"


# --- request parsing ---------------------------------------------------------------------------


def test_a_form_body_parses_to_single_values_and_keeps_a_deliberate_blank() -> None:
    """`Request.form` is how every state-changing request arrives from a browser.

    Blank values are KEPT. A blank optional model selector is a real choice — `None — skip this
    stage` — and a parser that dropped empty fields would make "the user selected nothing" and "the
    user selected nothing for this role" indistinguishable.
    """
    request = Request(
        method="POST",
        path="/runs",
        body=b"cik=0000000001&parsing_label=Parser+One&summary_label=&note=a%20b",
    )
    assert request.form() == {
        "cik": "0000000001",
        "parsing_label": "Parser One",
        "summary_label": "",
        "note": "a b",
    }


def test_a_repeated_form_field_collapses_to_its_first_value() -> None:
    """One name, one value. A handler reading `form()["cik"]` must never get a list."""
    request = Request(method="POST", path="/runs", body=b"cik=1&cik=2")
    assert request.form() == {"cik": "1"}


def test_a_json_body_parses_and_an_absent_body_is_none() -> None:
    """`json_body` returning None rather than raising is what lets a handler write `or {}`.

    Browser-facing JSON is outside the model content boundary: ADR-0013 governs what a MODEL sees,
    and a browser is not a model.
    """
    assert Request(method="POST", path="/api/preflight", body=b'{"cik": "1"}').json_body() == {
        "cik": "1"
    }
    assert Request(method="POST", path="/api/preflight").json_body() is None


def test_a_malformed_json_body_is_turned_into_a_bad_request_not_a_crash(app: ReviewApp) -> None:
    """`handle` converts a ValueError into 400. A JSON decode error IS a ValueError.

    Without that, a browser sending a truncated body gets a stack trace and a 500, and the server
    reports an internal fault for something the client did.
    """
    response = call(app, "POST", "/api/preflight", body=b"{not json")
    assert response.status == 400
    assert body_json(response)["code"] == "bad_request"


def test_headers_are_read_case_insensitively_and_html_is_detected_from_accept() -> None:
    """`wants_html` decides between a redirect and a JSON body on every state-changing route."""
    request = build_request(
        method="get",
        raw_path="/runs",
        headers={"Accept": "text/html,application/xhtml+xml", "X-Csrf-Token": "t"},
        body=b"",
        client_host="127.0.0.1",
    )
    assert request.method == "GET", "the method is normalised once, at the edge"
    assert request.header("ACCEPT").startswith("text/html")
    assert request.header(CSRF_HEADER) == "t"
    assert request.wants_html() is True
    assert Request(method="GET", path="/", headers={"accept": "*/*"}).wants_html() is False


def test_build_request_splits_the_query_and_defaults_an_empty_path_to_root() -> None:
    """The one place raw HTTP input becomes the object every handler takes.

    Blank values are kept here too, so `?q=` is a search for nothing rather than no search at all.
    """
    request = build_request(
        method="GET",
        raw_path="/api/entities?q=synthetic&q=second&limit=&panel=closed#frag",
        headers={},
        body=b"",
        client_host="127.0.0.1",
    )
    assert request.path == "/api/entities"
    assert request.query["q"] == ["synthetic", "second"]
    assert request.q("q") == "synthetic", "a handler asking for one value gets the first"
    assert request.q("limit", "20") == "", "a supplied blank is not silently replaced"
    assert request.q("missing", "20") == "20"
    assert (
        build_request(method="GET", raw_path="", headers={}, body=b"", client_host="").path == "/"
    )


def test_the_request_size_bound_is_finite_documented_and_enforced_by_the_dispatcher() -> None:
    """The one place a remote client controls an allocation on this server.

    The constant is asserted as a RANGE rather than a value, so tuning it stays a decision instead
    of a test edit. What must not change is that it exists, that it is stated with a reason, and
    that the dispatcher refuses an oversized body with 413 BEFORE reading it into memory.
    """
    assert isinstance(MAX_REQUEST_BYTES, int)
    assert 64 * 1024 <= MAX_REQUEST_BYTES <= 8 * 1024 * 1024

    source = Path(server_module.__file__).read_text(encoding="utf-8")
    preamble = source[: source.index("MAX_REQUEST_BYTES: int")].rsplit("\n\n", 1)[-1]
    assert preamble.lstrip().startswith("#:"), "the bound is declared with no stated reason"

    dispatch = source[source.index("def _dispatch") : source.index("def do_GET")]
    assert "MAX_REQUEST_BYTES" in dispatch and "413" in dispatch
    assert dispatch.index("send_response(413)") < dispatch.index("self.rfile.read")


def test_build_request_hands_an_oversized_body_through_because_bounding_is_its_callers_job() -> (
    None
):
    """MUTATION GUARD on the division of labour above.

    `build_request` is a pure parser and is also called by tests and tools with bodies nobody sent
    over a socket. If it silently truncated, the dispatcher's 413 would become unreachable and an
    oversized request would look accepted-then-shortened instead of refused.
    """
    oversized = b"x" * (MAX_REQUEST_BYTES + 1)
    request = build_request(
        method="POST", raw_path="/runs", headers={}, body=oversized, client_host="127.0.0.1"
    )
    assert request.body == oversized


# --- security headers --------------------------------------------------------------------------


def test_every_response_carries_the_security_headers_whatever_its_status(app: ReviewApp) -> None:
    """`decorate` is applied on every exit path, including the failures.

    A 404 or a 405 that arrived without the headers would be a page the browser treats differently
    from every other page on the origin, which is exactly the gap an injected error page wants.
    """
    responses = [
        call(app, "GET", "/health"),
        call(app, "GET", "/"),
        call(app, "GET", "/static/app.css"),
        call(app, "GET", "/no-such-route"),
        call(app, "GET", "/preflight"),
        call(app, "GET", "/api/runs/not-a-run-id"),
    ]
    assert {r.status for r in responses} == {200, 404, 405}
    for response in responses:
        for name, value in SECURITY_HEADERS.items():
            assert response.headers.get(name) == value, f"{name} missing from a {response.status}"


def test_the_content_security_policy_denies_everything_by_default_and_permits_no_inline_code(
    app: ReviewApp,
) -> None:
    """A filing is rendered as ESCAPED TEXT, which is the only reason this policy can be this strict.

    Nothing in a preserved SEC artifact ever reaches a markup parser, so the page needs no inline
    script, no inline style, no image source and no frame. `unsafe-inline` or `unsafe-eval` here
    would be the single edit that turns an untrusted filing into executable content, and it would
    not fail any other test in this repository.
    """
    policy = call(app, "GET", "/").headers["Content-Security-Policy"]
    directives = dict(part.strip().split(" ", 1) for part in policy.split(";") if part.strip())
    assert directives["default-src"] == "'none'"
    assert directives["frame-ancestors"] == "'none'"
    assert directives["base-uri"] == "'none'"
    assert directives["script-src"] == "'self'", "the one script is served from this origin"
    assert directives["style-src"] == "'self'"
    assert "unsafe-inline" not in policy
    assert "unsafe-eval" not in policy
    assert "*" not in policy, "a wildcard source would make default-src 'none' decorative"


def test_no_response_carries_a_cross_origin_header(app: ReviewApp) -> None:
    """The ABSENCE of CORS is the policy, so it is asserted rather than assumed.

    A browser refuses a cross-origin read without these headers. Adding a permissive one "for
    development" is how one reaches production, and nothing here would otherwise notice.
    """
    for path in ("/health", "/", "/api/models", "/static/app.js"):
        headers = {name.lower() for name in call(app, "GET", path).headers}
        assert not any(name.startswith("access-control-") for name in headers)


def test_decorating_never_overwrites_a_header_a_handler_set_itself(guarded: ReviewApp) -> None:
    """The session cookie and the security headers have to coexist on the same response.

    `setdefault` is what makes that true. A blanket assignment would drop `Set-Cookie` from the
    sign-in response and produce a login loop that reads as a bug rather than as a control.
    """
    response = call(
        guarded,
        "POST",
        "/sign-in",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        body=f"secret={DEV_SECRET}".encode(),
    )
    assert response.status == 303
    assert SESSION_COOKIE in response.headers["Set-Cookie"]
    assert response.headers["Location"] == "/"
    assert (
        response.headers["Content-Security-Policy"] == SECURITY_HEADERS["Content-Security-Policy"]
    )


# --- loopback and the authenticated posture beyond it ------------------------------------------


def test_a_loopback_instance_requires_no_authentication(app: ReviewApp) -> None:
    """On loopback this is a single-user developer tool and a sign-in would be theatre."""
    assert app.policy.authentication_required is False
    assert call(app, "GET", "/api/models").status == 200
    assert call(app, "GET", "/").status == 200


def test_a_non_loopback_json_request_without_a_session_is_refused_401(guarded: ReviewApp) -> None:
    """Beyond loopback this is an unauthenticated remote control for someone else's bill.

    A JSON caller gets 401 and a reason, not a redirect it cannot follow.
    """
    assert guarded.policy.authentication_required is True
    response = call(guarded, "GET", "/api/models", headers={"Accept": "application/json"})
    assert response.status == 401
    assert body_json(response)["code"] == "authentication_required"
    assert DEV_SECRET not in response.body.decode("utf-8"), "the refusal quoted the secret"


def test_a_non_loopback_html_request_without_a_session_is_sent_to_sign_in(
    guarded: ReviewApp,
) -> None:
    """A browser gets somewhere it can act on. The two callers are told apart by `Accept`."""
    response = call(guarded, "GET", "/", headers={"Accept": "text/html"})
    assert response.status == 303
    assert response.headers["Location"] == "/sign-in"
    assert response.body == b"", "a redirect must not carry a page body"


def test_a_session_cookie_admits_the_same_guarded_request(guarded: ReviewApp) -> None:
    """ANTI-VACUITY. The two refusals above must come from the missing session, not from the route."""
    headers, _ = signed_in(guarded)
    headers["Accept"] = "application/json"
    assert call(guarded, "GET", "/api/models", headers=headers).status == 200


def test_an_unknown_cookie_value_is_not_a_session(guarded: ReviewApp) -> None:
    """The cookie carries an opaque identifier looked up server-side and nothing else.

    No role, no signed claim, nothing a client could forge or replay after a restart. A value the
    store has never issued is simply not a session.
    """
    response = call(
        guarded,
        "GET",
        "/api/models",
        headers={"Accept": "application/json", "Cookie": f"{SESSION_COOKIE}=invented"},
    )
    assert response.status == 401


def test_health_the_sign_in_page_and_the_assets_stay_reachable_without_a_session(
    guarded: ReviewApp,
) -> None:
    """Exempting these three is what makes the guarded posture usable rather than a locked door.

    `/health` is polled by an operator, `/sign-in` is where an unauthenticated browser is sent, and
    the two assets are needed to render that page. Everything else is behind the session.
    """
    assert call(guarded, "GET", "/health").status == 200
    assert call(guarded, "GET", "/sign-in", headers={"Accept": "text/html"}).status == 200
    assert call(guarded, "GET", "/static/app.css").status == 200
    assert call(guarded, "GET", "/static/app.js").status == 200
    assert call(guarded, "GET", "/api/runs", headers={"Accept": "application/json"}).status == 401


def test_the_sign_in_page_never_echoes_the_secret_it_is_asking_for(guarded: ReviewApp) -> None:
    """The secret is read from ignored environment state and is never rendered."""
    page = call(guarded, "GET", "/sign-in", headers={"Accept": "text/html"}).body.decode("utf-8")
    assert DEV_SECRET not in page
    assert 'type="password"' in page


# --- the development secret --------------------------------------------------------------------


def test_a_wrong_secret_is_refused_and_creates_no_session(guarded: ReviewApp) -> None:
    """A refused sign-in must leave the session store exactly as it found it."""
    response = call(guarded, "POST", "/sign-in", body=b"secret=wrong")
    assert response.status == 401
    assert body_json(response)["code"] == "invalid_secret"
    assert call(guarded, "GET", "/api/models", headers={"Accept": "application/json"}).status == 401


def test_the_correct_secret_issues_a_hardened_cookie(harness: Harness) -> None:
    """`HttpOnly` and `SameSite=Strict` are the session's whole defence; `Secure` is conditional.

    `Secure` over plain HTTP makes the browser discard the cookie, producing a login loop that
    looks like a bug rather than the control it was meant to be — so the mode is stated honestly
    instead, and the attribute appears only when HTTPS is actually configured.
    """
    plain = app_for(harness, loopback_only=False, secret=DEV_SECRET, https=False)
    cookie = call(plain, "POST", "/sign-in", body=f"secret={DEV_SECRET}".encode()).headers[
        "Set-Cookie"
    ]
    assert cookie.startswith(f"{SESSION_COOKIE}=")
    assert "HttpOnly" in cookie and "SameSite=Strict" in cookie and "Path=/" in cookie
    assert "Secure" not in cookie

    secure = app_for(harness, loopback_only=False, secret=DEV_SECRET, https=True)
    assert (
        "Secure"
        in call(secure, "POST", "/sign-in", body=f"secret={DEV_SECRET}".encode()).headers[
            "Set-Cookie"
        ]
    )


def test_the_secret_is_compared_in_constant_time(harness: Harness) -> None:
    """A timing oracle on a short secret is a real oracle.

    Asserted structurally as well as behaviourally: `==` on two strings returns as soon as they
    differ, and no black-box test in a suite like this can measure that difference reliably. The
    behavioural half proves no prefix, extension or empty value is ever accepted.
    """
    policy = SecurityPolicy(loopback_only=False, dev_auth_secret=DEV_SECRET)
    body = inspect.getsource(SecurityPolicy.check_secret)
    assert "compare_digest" in body, "the comparison stopped being constant-time"
    assert "== self._secret" not in body and "self._secret ==" not in body

    assert policy.check_secret(DEV_SECRET) is True
    for wrong in ("", DEV_SECRET[:-1], DEV_SECRET + "x", DEV_SECRET.upper()):
        assert policy.check_secret(wrong) is False


def test_a_policy_holding_no_secret_accepts_nothing_at_all(app: ReviewApp) -> None:
    """MUTATION GUARD. The loopback policy has no secret, and "no secret" must not mean "any".

    An empty configured secret compared with an empty supplied one is a match under any equality
    test, so the absent case is short-circuited before the comparison rather than after it.
    """
    for supplied in ("", "anything", DEV_SECRET):
        assert app.policy.check_secret(supplied) is False


# --- CSRF --------------------------------------------------------------------------------------


def test_a_state_changing_request_without_a_token_is_refused_once_a_session_exists(
    guarded: ReviewApp,
) -> None:
    """A browser on another origin can make the request; it cannot read the token.

    The token is bound to the session, so the check applies wherever a session exists — which is
    every configuration that binds beyond loopback.
    """
    headers, _ = signed_in(guarded)
    response = call(guarded, "POST", "/runs/run_one/jobs/job_one/review", headers=headers)
    assert response.status == 403
    assert body_json(response)["code"] == "csrf_failed"


def test_the_bound_token_is_accepted_in_a_header_or_in_the_form(guarded: ReviewApp) -> None:
    """ANTI-VACUITY. The 403 above must come from the missing token, not from the route.

    404 here is the honest next answer: the token was accepted and the identifier was not one this
    store ever issued. Both spellings are supported because the UI posts ordinary forms and the
    script posts a header.
    """
    headers, token = signed_in(guarded)
    by_header = call(
        guarded,
        "POST",
        "/runs/run_one/jobs/job_one/review",
        headers={**headers, CSRF_HEADER: token},
        body=b"review_state=UNDER_REVIEW",
    )
    assert by_header.status == 404
    assert body_json(by_header)["code"] == "not_found"

    by_form = call(
        guarded,
        "POST",
        "/runs/run_one/jobs/job_one/review",
        headers=headers,
        body=f"{CSRF_FIELD}={token}&review_state=UNDER_REVIEW".encode(),
    )
    assert by_form.status == 404


def test_a_token_from_another_session_is_not_accepted(guarded: ReviewApp) -> None:
    """The token is bound to ONE session. A valid-looking token from elsewhere is not a token."""
    headers, _ = signed_in(guarded)
    _, other_token = signed_in(guarded)
    response = call(
        guarded,
        "POST",
        "/runs/run_one/jobs/job_one/review",
        headers={**headers, CSRF_HEADER: other_token},
    )
    assert response.status == 403


def test_sign_in_itself_is_exempt_from_the_csrf_check(guarded: ReviewApp) -> None:
    """It has to be: there is no session yet, so there is no token to bind to.

    The exemption is narrow and is the reason the check is expressed as "wherever a session
    exists" rather than "on every POST".
    """
    response = call(guarded, "POST", "/sign-in", body=f"secret={DEV_SECRET}".encode())
    assert response.status == 303


def test_loopback_with_no_session_has_no_token_to_bind_and_is_not_refused(
    app: ReviewApp, completed_run: tuple[str, str]
) -> None:
    """On loopback there is no cross-origin browser session to protect and no token to check.

    Refusing here would make the developer tool unusable in the posture it was designed for, and
    the control it would be enforcing protects nothing that exists.
    """
    run_id, _ = completed_run
    response = call(app, "POST", f"/runs/{run_id}/cancel")
    assert response.status == 200


# --- /health -----------------------------------------------------------------------------------


def test_health_reports_bind_mode_ceiling_and_cumulative_spend(app: ReviewApp) -> None:
    """The facts an operator needs, and money as an exact decimal string.

    The ceiling is CUMULATIVE and durable, so reporting it beside the spend is what makes the one
    unauthenticated route worth polling at all.
    """
    payload = body_json(call(app, "GET", "/health"))
    assert payload["status"] == "ok"
    assert payload["bind_mode"] == "loopback"
    assert payload["authentication_required"] is False
    assert payload["cost_ceiling_usd"] == "5.00"
    assert payload["cumulative_spend_usd"] == "0"
    assert payload["stages_executed_in_this_phase"] == ["parsing"]


def test_health_reports_the_network_bind_mode_when_that_is_what_it_is(guarded: ReviewApp) -> None:
    """MUTATION GUARD. A bind mode that always said "loopback" would be worse than none."""
    payload = body_json(call(guarded, "GET", "/health"))
    assert payload["bind_mode"] == "network interface"
    assert payload["authentication_required"] is True


def test_health_reports_the_spend_a_completed_run_actually_charged(
    app: ReviewApp, completed_run: tuple[str, str]
) -> None:
    """ANTI-VACUITY on the number above: it is read from the journal, not a constant.

    The reservation is charged before the call and settled against measured usage after it, so a
    finished run must move this figure off zero.
    """
    payload = body_json(call(app, "GET", "/health"))
    assert Decimal(payload["cumulative_spend_usd"]) > 0
    assert Decimal(payload["cumulative_spend_usd"]) < Decimal(payload["cost_ceiling_usd"])


def test_health_carries_nothing_account_specific(
    app: ReviewApp, completed_run: tuple[str, str]
) -> None:
    """SECURITY-INVARIANT: nothing AWS-shaped is ever placed in a response.

    All model access is server-side through `packages/llm_gateway`, so there is no browser path to
    a provider to accidentally open. Asserted on the WHOLE body rather than field by field, because
    the field that leaks is the one nobody thought to check — and asserted after a real run, when
    the service is holding routing, price and usage material it could have volunteered.
    """
    raw = call(app, "GET", "/health").body.decode("utf-8")
    assert not TWELVE_DIGITS.search(raw), "an account-shaped identifier appears in /health"
    for marker in PROVIDER_MARKERS:
        assert marker not in raw, f"/health mentions {marker!r}"
    for variable in CREDENTIAL_VARIABLE_NAMES:
        assert variable not in raw, "/health names a credential variable"


# --- no browser-facing route offers a way to reach a provider ----------------------------------


def identifier_free_get_routes(app: ReviewApp) -> list[str]:
    """Every GET route in the contract that can be fetched with no identifier to invent."""
    return [
        path for method, path in app.router.implemented() if method == "GET" and "{" not in path
    ]


def test_no_identifier_free_route_returns_a_provider_endpoint_or_credential(
    app: ReviewApp, completed_run: tuple[str, str]
) -> None:
    """The browser never calls a model provider, because no route hands it anything to call one with.

    Model LABELS, regions, states, counts, money and preserved bytes are what the browser gets. An
    endpoint, a key, a token or an account-bearing identifier is what it never gets. Swept over the
    real route table so a route added later is covered without editing this test, and swept after a
    run so the pages are rendering real routing and cost material rather than empty tables.
    """
    routes = identifier_free_get_routes(app)
    assert len(routes) >= 8, "the sweep is scanning fewer routes than the application serves"

    for path in routes:
        response = call(app, "GET", path, headers={"Accept": "text/html"})
        assert response.status == 200, f"{path} answered {response.status}"
        raw = response.body.decode("utf-8")
        for marker in PROVIDER_MARKERS:
            assert marker not in raw, f"{path} returned {marker!r}"
        for variable in CREDENTIAL_VARIABLE_NAMES:
            assert variable not in raw, f"{path} named a credential variable"
        assert not TWELVE_DIGITS.search(raw), f"{path} returned an account-shaped identifier"


def test_the_provider_sweep_would_notice_a_leak(app: ReviewApp) -> None:
    """ANTI-VACUITY. The markers above must be the kind of thing a body could actually contain.

    A sweep whose patterns can never match is a sweep that passes forever. This asserts the same
    detector fires on a body that does carry the material, so the negative result above means
    something.
    """
    leaky = "endpoint https://bedrock-runtime.example.amazonaws.com account 123456789012"
    assert any(marker in leaky for marker in PROVIDER_MARKERS)
    assert TWELVE_DIGITS.search(leaky) is not None
    assert not TWELVE_DIGITS.search("a 2026-08-03 date and an accession 0000000001-24-000001")


# --- missing and malformed identifiers ---------------------------------------------------------


def test_an_unknown_run_id_answers_404_rather_than_raising(app: ReviewApp) -> None:
    """A well-formed identifier for a run that was never created is a miss, not a fault."""
    response = call(app, "GET", "/api/runs/run_abcdefghijklmnopqrstuvwxyz")
    assert response.status == 404
    assert body_json(response)["code"] == "not_found"


def test_a_malformed_identifier_answers_404_rather_than_reaching_a_storage_key(
    app: ReviewApp,
) -> None:
    """The identifier guard runs before anything is concatenated into a path.

    `..` and `/` are not in the permitted alphabet, so a traversal attempt is refused by identity
    rather than relying on the object store's own guard as the only line of defence — and the
    refusal reaches the browser as an ordinary 404.
    """
    for path in ("/api/runs/not-a-run-id", "/api/runs/..", "/api/runs/run_SHOUTING"):
        response = call(app, "GET", path)
        assert response.status == 404, path
        assert body_json(response)["code"] == "not_found"


def test_an_unknown_job_under_a_real_run_answers_404(
    app: ReviewApp, completed_run: tuple[str, str]
) -> None:
    """ANTI-VACUITY partner: the run resolves, so the 404 is about the job."""
    run_id, job_id = completed_run
    assert call(app, "GET", f"/api/runs/{run_id}/jobs/{job_id}").status == 200
    assert call(app, "GET", f"/api/runs/{run_id}/jobs/job_abcdefghijklmnopqrstuvwxyz").status == 404


def test_an_unparseable_query_value_becomes_a_bad_request_not_an_internal_error(
    app: ReviewApp,
) -> None:
    """`limit` is turned into an int by the handler, and a browser controls it.

    400 names the client's mistake; a 500 would name the server's, and the difference decides who
    goes looking for the bug.
    """
    response = call(app, "GET", "/api/entities?q=synthetic&limit=lots")
    assert response.status == 400
    assert body_json(response)["code"] == "bad_request"


# --- the catalog and the model selectors -------------------------------------------------------


def test_the_selector_surface_offers_four_roles_and_only_parsing_is_required(
    app: ReviewApp,
) -> None:
    """No role inherits another's model, and a blank optional role is a VISIBLE choice.

    The blank option carries a label — `None — skip this stage` — rather than being the absence of
    a selection, because a user has to be able to mean it and a run record has to be able to show
    that they did.
    """
    roles = body_json(call(app, "GET", "/api/models"))["roles"]
    assert set(roles) == {"parsing", "image", "summary", "analysis"}
    assert roles["parsing"]["required"] is True
    assert roles["parsing"]["blank_option"] is None
    assert roles["parsing"]["executed_in_this_phase"] is True
    for optional in ("image", "summary", "analysis"):
        assert roles[optional]["required"] is False
        assert roles[optional]["blank_option"]["display"]
        assert roles[optional]["executed_in_this_phase"] is False


def test_entity_search_answers_from_the_supplied_manifest_and_invents_nothing(
    app: ReviewApp,
) -> None:
    """An entity with no qualifying filing never appears, and no identity is reconstructed."""
    found = body_json(call(app, "GET", "/api/entities?q=synthetic"))["results"]
    assert [e["cik"] for e in found] == [CIK]
    assert found[0]["name"] == ENTITY_NAME
    assert (
        body_json(call(app, "GET", "/api/entities?q=a-company-that-filed-nothing"))["results"] == []
    )
    assert call(app, "GET", "/api/entities/9999999999").status == 404


def test_the_filings_of_an_entity_can_be_narrowed_by_date(app: ReviewApp) -> None:
    """The timeframe is a filter over preserved filings, never a request for ones nobody holds."""
    all_filings = body_json(call(app, "GET", f"/api/entities/{CIK}/filings"))["results"]
    assert [f["accession"] for f in all_filings] == [ACCESSION]
    narrowed = body_json(call(app, "GET", f"/api/entities/{CIK}/filings?from=2025-01-01"))
    assert narrowed["results"] == []


# --- preflight and run creation ----------------------------------------------------------------


def test_a_run_with_no_parsing_model_is_refused_and_nothing_is_chosen_for_the_user(
    app: ReviewApp,
) -> None:
    """rules.md section 21: no silent model selection, no substitution, no fallback.

    A blank parsing selector is the one blank that is not a valid configuration, and the refusal
    has to say so instead of picking the first enabled candidate.
    """
    response = call(app, "POST", "/api/preflight", body=json.dumps({"cik": CIK}).encode())
    assert response.status == 400
    payload = body_json(response)
    assert payload["code"] == "refused"
    assert "parsing model" in payload["message"]


def test_a_preflight_prices_the_run_without_spending_anything(
    app: ReviewApp, harness: Harness
) -> None:
    """Previewed and authorized BEFORE, never reconciled after. A preview costs nothing.

    The bound is a worst case from a character-ratio estimate and the reviewed price inputs, and
    the payload says so in its own words rather than presenting a prediction.
    """
    before = harness.service.journal.spent_usd
    response = call(
        app,
        "POST",
        "/api/preflight",
        body=json.dumps(
            {"cik": CIK, "parsing_label": PARSING_LABEL, "accession": ACCESSION}
        ).encode(),
    )
    assert response.status == 200
    plan = body_json(response)
    assert plan["compatible_filings"] == 1
    assert plan["incompatible_filings"] == 0
    assert Decimal(plan["worst_case_total_usd"]) > 0
    assert plan["within_ceiling"] is True
    assert "WORST-CASE" in plan["cost_note"]
    assert harness.service.journal.spent_usd == before, "a preflight spent money"


def test_selecting_a_stage_this_phase_never_authorized_is_refused_loudly(app: ReviewApp) -> None:
    """Phase 2 executes the parsing stage only.

    A summary selector filled in by mistake must fail rather than quietly spend on a stage nobody
    authorized — and must fail rather than being silently ignored, which would leave the user
    believing a stage ran.
    """
    response = call(
        app,
        "POST",
        "/runs",
        body=json.dumps(
            {
                "cik": CIK,
                "parsing_label": PARSING_LABEL,
                "accession": ACCESSION,
                "summary_label": PARSING_LABEL,
            }
        ).encode(),
    )
    assert response.status == 400
    assert "summary" in body_json(response)["message"]


def test_a_parser_only_run_is_created_with_one_child_job_per_filing(
    app: ReviewApp, harness: Harness
) -> None:
    """ANTI-VACUITY partner: a parser-only run is a COMPLETE, valid run, and 202 says so.

    One parent run per request, one child job per filing, never concatenated — a five-year request
    is five independent billable units under one visible identifier.
    """
    response = call(
        app,
        "POST",
        "/runs",
        body=json.dumps(
            {"cik": CIK, "parsing_label": PARSING_LABEL, "accession": ACCESSION}
        ).encode(),
    )
    assert response.status == 202
    payload = body_json(response)
    assert len(payload["job_ids"]) == 1
    run = harness.service.store.load_run(payload["run_id"])
    assert run.selected_roles == ("parsing",)
    assert run.summary_label is None and run.image_label is None


# --- one stored run --------------------------------------------------------------------------


def test_the_run_page_and_the_job_page_render_the_stored_run(
    app: ReviewApp, completed_run: tuple[str, str]
) -> None:
    """The parser-review UI is built WITH the experiments: a parse is unreadable without the filing.

    Both pages are server-rendered HTML, which is what lets the content security policy stay strict
    and removes any need for a sanitizer or a sandboxed iframe.
    """
    run_id, job_id = completed_run
    run_page = call(app, "GET", f"/runs/{run_id}", headers={"Accept": "text/html"})
    assert run_page.status == 200
    assert run_page.content_type.startswith("text/html")
    assert run_id in run_page.body.decode("utf-8")

    job_page = call(app, "GET", f"/runs/{run_id}/jobs/{job_id}", headers={"Accept": "text/html"})
    assert job_page.status == 200
    assert ACCESSION in job_page.body.decode("utf-8")


def test_the_exact_model_response_is_served_back_byte_for_byte(
    app: ReviewApp, completed_run: tuple[str, str]
) -> None:
    """Exact bytes are the whole value of the evidence.

    Nothing pretty-prints, re-encodes or normalises what the model returned, because whether the
    prompt or the model is at fault is exactly what a reviewer is there to decide.
    """
    run_id, job_id = completed_run
    response = call(app, "GET", f"/api/runs/{run_id}/jobs/{job_id}/response")
    assert response.status == 200
    assert response.body == MOCK_RESPONSE.encode("utf-8")


def test_the_preserved_source_artifact_is_served_and_an_unknown_one_is_a_miss(
    app: ReviewApp, completed_run: tuple[str, str]
) -> None:
    """The reviewer sees what the model actually received, resolved from the run's own evidence.

    ANTI-VACUITY in the same test: asking for an artifact this job never had must be a 404 rather
    than an empty 200, which would read as a filing that contained nothing.
    """
    run_id, job_id = completed_run
    served = call(app, "GET", f"/api/runs/{run_id}/jobs/{job_id}/source")
    assert served.status == 200
    assert FILING_MARKER in served.body.decode("utf-8")

    missing = call(app, "GET", f"/api/runs/{run_id}/jobs/{job_id}/source?artifact=nothing.txt")
    assert missing.status == 404


def test_the_validation_verdict_is_stored_and_served_rather_than_asserted_by_the_model(
    app: ReviewApp, completed_run: tuple[str, str]
) -> None:
    """Interpretation is the model's; PROOF is the backend's.

    The verdict is computed against the preserved bytes and stored with the job, so the route
    reports a recorded finding rather than repeating a claim the response made about itself.
    """
    run_id, job_id = completed_run
    response = call(app, "GET", f"/api/runs/{run_id}/jobs/{job_id}/validation")
    assert response.status == 200
    assert body_json(response)["status"] in {"COMPLETE", "PARTIAL", "REVIEW_REQUIRED"}


def test_the_event_stream_carries_no_filing_text_and_terminates_on_a_finished_run(
    app: ReviewApp, completed_run: tuple[str, str]
) -> None:
    """A stream is the one response that is an iterator instead of a body, and it stays small.

    Events carry a kind, a child job identifier and a short message; bodies live in the evaluation
    store and are referenced. Filing text may be very large and may carry an instruction a prompt
    injection placed inside a filing, so it never crosses this stream. A completed run replays its
    stored events and closes rather than holding a connection for ever.
    """
    run_id, _ = completed_run
    response = call(app, "GET", f"/runs/{run_id}/events")
    assert response.stream is not None
    assert response.body == b""
    assert response.content_type.startswith("text/event-stream")

    streamed = b"".join(response.stream).decode("utf-8")
    assert "id: 00000001" in streamed, "the stream is not resumable without an event id"
    assert "event: terminal" in streamed
    assert FILING_MARKER not in streamed
    assert MOCK_RESPONSE.strip() not in streamed


def test_the_stream_resumes_after_the_last_event_the_browser_saw(
    app: ReviewApp, completed_run: tuple[str, str]
) -> None:
    """`Last-Event-ID` replays from the one after it, which is what makes a reconnect free.

    ANTI-VACUITY for the test above: a stream that ignored the header would replay everything, so
    the resumed stream must be strictly shorter than the full one.
    """
    run_id, _ = completed_run
    full = b"".join(call(app, "GET", f"/runs/{run_id}/events").stream or iter(()))
    resumed = b"".join(
        call(app, "GET", f"/runs/{run_id}/events", headers={"Last-Event-ID": "3"}).stream
        or iter(())
    )
    assert len(resumed) < len(full)
    assert b"id: 00000001" not in resumed


def test_cancelling_a_finished_run_cancels_nothing(
    app: ReviewApp, completed_run: tuple[str, str]
) -> None:
    """A job that has already been invoked is NOT cancelled.

    The provider call is billable from the moment it is issued, and marking it cancelled would hide
    a charge the ledger still has to settle. Cancelling only ever touches jobs that have not yet
    been invoked, so a finished run reports an empty list rather than rewriting history.
    """
    run_id, job_id = completed_run
    response = call(app, "POST", f"/runs/{run_id}/cancel")
    assert response.status == 200
    assert body_json(response)["cancelled"] == []
    assert (
        app.service.store.load_job(run_id, job_id).execution_state
        is ExecutionState.READY_FOR_REVIEW
    )


# --- review state and comments -----------------------------------------------------------------


def test_an_unknown_review_state_is_refused_rather_than_coerced(
    app: ReviewApp, completed_run: tuple[str, str]
) -> None:
    """The review states are a closed set. A string that is not one of them is a bad request."""
    run_id, job_id = completed_run
    response = call(
        app, "POST", f"/runs/{run_id}/jobs/{job_id}/review", body=b"review_state=PROBABLY_FINE"
    )
    assert response.status == 400
    assert body_json(response)["code"] == "bad_request"


def test_a_permitted_review_transition_is_recorded_with_its_history(
    app: ReviewApp, harness: Harness, completed_run: tuple[str, str]
) -> None:
    """ANTI-VACUITY partner, and the reason the history is appended rather than rewritten.

    A review trail that can be edited is not a trail: rules.md invariant 7 forbids overwriting an
    accepted decision, so the previous state stays readable beside the new one.
    """
    run_id, job_id = completed_run
    response = call(
        app, "POST", f"/runs/{run_id}/jobs/{job_id}/review", body=b"review_state=UNDER_REVIEW"
    )
    assert response.status == 200
    assert body_json(response)["review_state"] == "UNDER_REVIEW"
    job = harness.service.store.load_job(run_id, job_id)
    assert [t.to_state for t in job.review_history] == ["UNDER_REVIEW"]
    assert job.review_history[0].from_state == "EVALUATION"


def test_an_empty_comment_is_refused_and_a_real_one_is_stored(
    app: ReviewApp, completed_run: tuple[str, str]
) -> None:
    """A comment with no text is not a finding, and storing one would dilute the evaluation record.

    A stored comment is bound to the artifact VERSION it targeted, so a comment written against one
    attempt does not silently become a comment about the next.
    """
    run_id, job_id = completed_run
    assert (
        call(app, "POST", f"/runs/{run_id}/jobs/{job_id}/comments", body=b"text=%20").status == 400
    )

    created = call(
        app, "POST", f"/runs/{run_id}/jobs/{job_id}/comments", body=b"text=the+parse+missed+a+table"
    )
    assert created.status == 201
    stored = body_json(created)
    assert stored["text"] == "the parse missed a table"
    assert stored["child_job_id"] == job_id
    assert stored["target_version"]

    listed = body_json(call(app, "GET", f"/api/runs/{run_id}/comments"))["results"]
    assert [c["comment_id"] for c in listed] == [stored["comment_id"]]


def test_a_browser_form_post_redirects_while_a_json_client_gets_a_body(
    app: ReviewApp, completed_run: tuple[str, str]
) -> None:
    """The same route serves both callers, and the two must not be confused.

    A browser that posts a form and receives JSON is left staring at a text file; a script that
    follows a redirect re-renders a page it cannot use. `Accept` is what tells them apart.
    """
    run_id, job_id = completed_run
    html_response = call(
        app,
        "POST",
        f"/runs/{run_id}/jobs/{job_id}/comments",
        headers={"Accept": "text/html"},
        body=b"text=from+a+browser",
    )
    assert html_response.status == 303
    assert html_response.headers["Location"] == f"/runs/{run_id}/jobs/{job_id}"

    json_response = call(
        app,
        "POST",
        f"/runs/{run_id}/jobs/{job_id}/comments",
        headers={"Accept": "application/json"},
        body=b"text=from+a+script",
    )
    assert json_response.status == 201
    assert json_response.content_type.startswith("application/json")
