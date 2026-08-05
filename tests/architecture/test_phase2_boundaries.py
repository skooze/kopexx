"""Phase 2 boundaries: the parser path exists, and none of the things it could become do.

Phase 2 built the first thing in this project that reaches a real model with a real filing. Six
things must not follow it into the repository, and each has a guard here rather than a paragraph
somewhere:

    1. A PROGRAMMATIC SEMANTIC PARSER. The backend transports and validates. It never decides what
       filing content means, and the deleted parser must not return under a new name.
    2. A UNIVERSAL FILING TAXONOMY. No enum of section kinds, no required hierarchy, no canonical
       vocabulary a model's output is normalised into.
    3. A DATABASE OR A CACHE. Persistence follows measured model output; Redis is a Phase 4
       decision that has not been taken.
    4. A HARDCODED MODEL FACT. Identifiers, regions, limits and prices are SUPPLIED from the
       reviewed snapshot, exactly as the qualifying-form set is supplied.
    5. A BROWSER-TO-PROVIDER PATH. All model access is server-side; the browser receives no
       credential, no endpoint and no filesystem path.
    6. AN UNAUTHORIZED STAGE. Only the parsing stage runs. The image, summary and analysis
       selectors exist so the progressive workflow is real, and invoking one is a scope violation.

CREDENTIAL VARIABLE NAMES ARE ASSEMBLED, NEVER WRITTEN OUT, for the same reason
`test_phase1_aws_boundary.py` assembles them: the AWS-identity guard fails the build when those
literals appear in a tracked file that is not the policy itself, and its allowlist is deliberately
hard to join.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
PACKAGES = REPO_ROOT / "packages"
PROMPTS = REPO_ROOT / "prompts"

pytestmark = pytest.mark.architecture

_PREFIX = "AWS_"
CREDENTIAL_VARIABLES = tuple(
    _PREFIX + suffix for suffix in ("ACCESS_KEY_ID", "SECRET_ACCESS_KEY", "SESSION_TOKEN")
)

#: The packages Phase 2 added. Named explicitly so the guards below cannot go vacuous by scanning
#: a directory that quietly stopped existing.
PHASE_2_PACKAGES = (
    "evaluation_store",
    "source_transport",
    "coverage_validation",
    "prompt_registry",
    "orchestrator",
    "review_api",
    "review_web",
)


def _python_files(root: Path) -> list[Path]:
    return [p for p in root.rglob("*.py") if "__pycache__" not in p.parts]


def _string_constants(path: Path) -> list[tuple[int, str]]:
    """Evaluated string literals only, so a docstring or a comment explaining a rule stays legal."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    docstrings = {
        node.body[0].value
        for node in ast.walk(tree)
        if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef)
        and node.body
        and isinstance(node.body[0], ast.Expr)
        and isinstance(node.body[0].value, ast.Constant)
    }
    return [
        (node.lineno, node.value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and node not in docstrings
    ]


# --- anti-vacuity -------------------------------------------------------------------------------


def test_the_phase_2_packages_exist_and_carry_code() -> None:
    """Every guard below scans these. A missing one would make the scan silently empty."""
    for name in PHASE_2_PACKAGES:
        package = PACKAGES / name
        assert package.is_dir(), f"packages/{name} does not exist"
        modules = [p for p in _python_files(package) if p.name != "__init__.py"]
        assert modules, f"packages/{name} contains only __init__.py, so nothing is enforced"
    assert len(_python_files(PACKAGES)) >= 60, "too few modules for these guards to be meaningful"


# --- 1. no programmatic semantic parser -----------------------------------------------------------


def test_no_runtime_package_names_a_filing_section() -> None:
    """PRODUCT-DIRECTION-INVARIANT rule 1: the backend never decides what a filing MEANS.

    The deleted parser decided in code what a Part, an Item, a footnote and a signature block were,
    and it worked beautifully on the one company it had ever seen. This guard fails if any of those
    words comes back as a string literal the interpreter can match against — a matcher, a mapping
    key, a set member. Prose explaining the rule stays legal, which is why only evaluated constants
    are inspected.

    `packages/review_web` is scanned too. A renderer that special-cased a section name would be the
    same taxonomy wearing a stylesheet.
    """
    forbidden = re.compile(
        r"^(md&a|md and a|risk[ _]factors?|item[ _]?\d+[a-z]?|part[ _]?[ivx]+|footnote|"
        r"signature[ _]block|certification|exhibit[ _]?\d*|financial[ _]statements?)$",
        re.IGNORECASE,
    )
    offenders: list[str] = []
    for path in _python_files(PACKAGES):
        for line, value in _string_constants(path):
            if forbidden.match(value.strip()):
                offenders.append(f"{path.relative_to(REPO_ROOT)}:{line}: {value!r}")
    assert not offenders, (
        "a filing section name is written into runtime source. The selected parsing model names "
        f"filing content; backend code never does: {offenders}"
    )


def test_a_prose_mention_of_a_section_name_is_still_permitted() -> None:
    """MUTATION PROOF for the guard above.

    Without this, the previous test would pass just as happily over a codebase that had removed
    every explanatory comment — and the explanations are how the next reader learns why the rule
    exists. This asserts the words DO appear in prose somewhere, so the guard is provably matching
    evaluated literals rather than text.
    """
    prose = (PACKAGES / "source_transport" / "dispositions.py").read_text(encoding="utf-8")
    assert "footnote" in prose.lower(), "the rule's own explanation has been removed from the code"


def test_the_deleted_parser_packages_have_not_returned() -> None:
    """ADR-0017 deleted five packages. A Phase 2 package must not be one of them renamed."""
    deleted = (
        "footnote_extractor",
        "footnote_canonicalizer",
        "table_parser",
        "persistence",
        "dera_notes",
    )
    present = [name for name in deleted if (PACKAGES / name).exists()]
    assert not present, f"a deleted package has returned: {present}"


# --- 2. no universal filing taxonomy --------------------------------------------------------------


def test_the_validator_cannot_issue_a_complete_verdict() -> None:
    """A COMPLETE status is a claim nothing this project measures can support.

    The complete-content invariant asks whether every human-readable source RANGE is represented.
    What the validator measures are coverage SIGNALS. If a COMPLETE member existed, something would
    eventually set it, and a false complete is precisely what rules.md section 21 rule 5 forbids.
    """
    from packages.coverage_validation import ValidationStatus

    names = {member.name for member in ValidationStatus}
    assert "COMPLETE" not in names, (
        "ValidationStatus gained a COMPLETE member. Nothing measured against the preserved bytes "
        f"establishes it. Members: {sorted(names)}"
    )
    assert "PARTIAL" in names and "REVIEW_REQUIRED" in names, (
        "the honest verdicts are missing, so this guard would be checking an empty enum"
    )


def test_the_parsed_reader_requires_no_node_type_vocabulary() -> None:
    """An unfamiliar model-chosen label must be represented, not rejected and not dropped."""
    from packages.coverage_validation import read

    document = read(
        "artifact: {}\n"
        "document: []\n"
        "nodes:\n"
        '  - id: "x1"\n'
        "    order: 0\n"
        "    type: a label no backend has ever heard of\n"
        "    title: Whatever The Filing Called It\n"
        "    surprising_key: kept\n"
        "unresolved: []\n"
        "metadata: {}\n"
    )
    assert document.nodes[0].node_type == "a label no backend has ever heard of"
    assert document.nodes[0].extra["surprising_key"] == "kept", (
        "an unknown key was dropped; the whole point of the first experiments is to see what "
        "models actually emit"
    )


# --- 3. no database and no cache ------------------------------------------------------------------


def test_no_package_imports_a_database_driver_an_orm_or_a_cache_client() -> None:
    """Persistence follows measured model output. Redis is a Phase 4 decision, not a Phase 2 one."""
    forbidden = re.compile(
        r"^\s*(import|from)\s+(sqlalchemy|alembic|psycopg|psycopg2|sqlite3|redis|pymongo|asyncpg)\b"
    )
    offenders: list[str] = []
    for path in _python_files(PACKAGES):
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if forbidden.match(line):
                offenders.append(f"{path.relative_to(REPO_ROOT)}:{number}")
    assert not offenders, f"a database or cache client is imported by shipped source: {offenders}"


def test_the_declared_dependencies_add_no_database_cache_or_web_framework() -> None:
    """The runtime dependency list is the other half of the same guard."""
    text = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    body = text.split("[project.optional-dependencies]")[0]
    for name in (
        "sqlalchemy",
        "alembic",
        "psycopg",
        "redis",
        "fastapi",
        "flask",
        "django",
        "starlette",
        "uvicorn",
    ):
        assert f'"{name}' not in body.lower(), f"{name} was added as a runtime dependency"


def test_evaluation_evidence_is_gitignored() -> None:
    """Evaluation runs hold exact model responses and preserved filings. They are host state."""
    import subprocess

    for candidate in (
        "var/evaluation-runs/example/run.yaml",
        "var/evaluation-runs/spend-journal.yaml",
    ):
        result = subprocess.run(["git", "check-ignore", "-q", candidate], cwd=REPO_ROOT, timeout=30)
        assert result.returncode == 0, f"{candidate} is not gitignored"


# --- 4. no hardcoded model fact -------------------------------------------------------------------


def test_the_routing_module_names_no_region() -> None:
    """Region routing is DERIVED from the reviewed snapshot, never written down here.

    `test_phase1_aws_boundary.py` already forbids a region literal anywhere in shipped source. This
    adds the specific case Phase 2 created: the router chooses a region, and the temptation to name
    a fallback in it is exactly the form-family defect with a bill attached.
    """
    source = (PACKAGES / "model_catalog" / "routing.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    region = re.compile(r"^(us|eu|ap|sa|ca|me|af|il)-[a-z]+-\d(-\w+)?$")
    offenders = [
        f"line {node.lineno}: {node.value!r}"
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and region.match(node.value)
    ]
    assert not offenders, f"the router names a region of its own: {offenders}"
    assert "verified_regions[0]" in source, (
        "the router no longer derives its region from the snapshot; this guard would be vacuous"
    )


def test_the_parser_prompt_is_hash_locked_and_is_not_markdown() -> None:
    """A prompt version that has been used is evidence. Editing it in place is not possible."""
    from packages.prompt_registry import PromptRegistry

    registry = PromptRegistry.from_directory(PROMPTS / "parser")
    assert registry.versions, "no prompt versions are declared"
    for version in registry.versions:
        assert version.filename.endswith(".txt"), (
            f"{version.filename} is not a .txt prompt; model-visible prompts are never Markdown"
        )
        assert len(version.sha256) == 64
    # `from_directory` re-hashes every file and raises on a mismatch, so reaching this line at all
    # is the proof. Asserting it explicitly keeps the intent visible to the next reader.
    assert registry.active_for("parsing").text.strip(), "the active parser prompt is empty"


def test_the_sdk_may_not_retry_underneath_the_cost_ceiling() -> None:
    """A retry the ledger cannot see is a charge the ceiling was never enforced against.

    botocore retries on its own by default, and a Converse call is BILLABLE FROM THE MOMENT IT IS
    ISSUED. An SDK-level retry is therefore a second charge that `RetryBudget` never counted and
    the durable spend journal never recorded — the ceiling would have been checked against a number
    smaller than the bill. The one permitted automatic retry belongs to the orchestrator, which
    reserves for it before it happens.

    Asserted on the module's declared constants rather than by constructing a client, because the
    suite may not import a provider SDK at all.
    """
    from packages.llm_gateway.providers import bedrock

    assert bedrock.SDK_MAX_ATTEMPTS == 1, (
        "botocore's max_attempts counts the FIRST attempt, so anything above 1 is a retry the "
        f"spend journal never sees: {bedrock.SDK_MAX_ATTEMPTS}"
    )
    source = (PACKAGES / "llm_gateway" / "providers" / "bedrock.py").read_text(encoding="utf-8")
    assert '"max_attempts": SDK_MAX_ATTEMPTS' in source, (
        "the client is constructed without an explicit retry configuration, so the SDK default "
        "applies and the SDK default retries"
    )
    # MEASURED, NOT GUESSED. The SDK's default read timeout is 60 seconds; the first real parse of
    # a preserved filing took 158. A default-timeout client turns a working model into a failure.
    assert bedrock.READ_TIMEOUT_SECONDS >= 300, (
        "the read timeout is at or below the order of magnitude that already timed out on a real "
        f"filing: {bedrock.READ_TIMEOUT_SECONDS}s"
    )


# --- 5. no browser-to-provider path ----------------------------------------------------------------


def test_no_review_response_can_carry_a_credential_or_a_provider_endpoint() -> None:
    """SECURITY-INVARIANT: the browser never holds a credential and never learns an endpoint."""
    offenders: list[str] = []
    for name in ("review_api", "review_web"):
        for path in _python_files(PACKAGES / name):
            text = path.read_text(encoding="utf-8")
            for marker in (*CREDENTIAL_VARIABLES, "amazonaws.com", "bedrock-runtime"):
                if marker in text:
                    offenders.append(f"{path.relative_to(REPO_ROOT)}: {marker}")
    assert not offenders, f"the browser-facing packages mention provider material: {offenders}"


def test_the_review_packages_import_no_provider_sdk_and_no_http_client() -> None:
    """The browser-facing half reaches nothing. All model and SEC access is elsewhere."""
    forbidden = re.compile(r"^\s*(import|from)\s+(boto3|botocore|httpx|requests|urllib3)\b")
    offenders: list[str] = []
    for name in ("review_web",):
        for path in _python_files(PACKAGES / name):
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if forbidden.match(line):
                    offenders.append(f"{path.relative_to(REPO_ROOT)}:{number}")
    assert not offenders, f"the rendering package reaches the network: {offenders}"


def test_every_review_response_carries_the_security_headers() -> None:
    """A strict content policy is what lets a preserved filing be displayed without a sanitizer."""
    from packages.review_api import SECURITY_HEADERS

    policy = SECURITY_HEADERS["Content-Security-Policy"]
    assert "default-src 'none'" in policy
    assert "unsafe-inline" not in policy, (
        "the policy allows inline script or style. The review UI serves its stylesheet and script "
        "from their own routes precisely so it does not have to."
    )
    assert SECURITY_HEADERS["X-Content-Type-Options"] == "nosniff"
    assert SECURITY_HEADERS["X-Frame-Options"] == "DENY"


def test_binding_beyond_loopback_without_a_secret_is_refused() -> None:
    """The unsafe combination must not be reachable by forgetting something."""
    from packages.configuration import ReviewSettings

    with pytest.raises(ValueError, match="loopback"):
        ReviewSettings(bind_host="0.0.0.0", dev_auth_secret=None)  # noqa: S104
    # Mutation proof: the same host WITH a secret is accepted, so the assertion above cannot be
    # passing because the constructor rejects every non-default host.
    assert not ReviewSettings(
        bind_host="0.0.0.0",  # noqa: S104
        dev_auth_secret="a-sufficiently-long-development-secret",
    ).loopback_only


# --- 6. only the authorized stage runs -------------------------------------------------------------


def test_only_a_selected_stage_can_run_and_none_is_substituted() -> None:
    """SUPERSEDED BY PHASE 3, AND STRENGTHENED RATHER THAN DELETED.

    This test used to assert that `create_run` raised `StageNotAuthorizedError` for any non-parsing
    role, which was correct while no other stage existed. Phase 3 implements image, summary and
    analysis, so the blanket refusal is gone and the guard it was really protecting is not: a stage
    runs ONLY because the user selected it, and no role ever borrows another role's model.

    Read from the source because the property is structural. `run_optional_stages` iterates the
    three labels the RUN RECORD carries, so a blank selector produces no entry and therefore no
    call — there is no `if summary_enabled` to get wrong, which is rules.md section 21 rule 8.
    """
    source = (PACKAGES / "orchestrator" / "service.py").read_text(encoding="utf-8")
    assert "def run_optional_stages" in source, "the optional stages have no runner"
    # THE THREE ROLES ARE READ FROM THE RUN, never defaulted and never inferred from the parser.
    for field in ("run.image_label", "run.summary_label", "run.analysis_label"):
        assert field in source, f"the optional stages do not read {field}"
    assert "if not label or role.value in job.stages:" in source, (
        "a stage no longer skips an unselected role, or re-runs one that already ran"
    )
    # MUTATION PROOF: a substitution would have to name the parsing label somewhere in the runner.
    runner = source.split("def run_optional_stages", 1)[1].split("def _stage_instruction", 1)[0]
    assert "parsing_label" not in runner, (
        "the optional-stage runner names the parsing label; a blank role can borrow the parser"
    )


def test_a_blank_optional_role_runs_no_stage_and_borrows_no_model() -> None:
    """rules.md section 21 rule 8. A blank role is a complete configuration, not a missing one."""
    from packages.model_catalog import ModelRole, RoleSelection

    selection = RoleSelection(parsing="some label")
    assert selection.selected_roles == (ModelRole.PARSING,)
    assert selection.label_for(ModelRole.SUMMARY) is None, (
        "a blank role reported a model; the parsing model was borrowed to fill it"
    )
    # Mutation proof: a role that IS selected appears, so the assertion above is not vacuous.
    filled = RoleSelection(parsing="a", summary="b")
    assert ModelRole.SUMMARY in filled.selected_roles
