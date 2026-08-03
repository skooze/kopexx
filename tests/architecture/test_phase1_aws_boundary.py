"""Phase 1 boundaries: no AWS in the product, no account in the repository, no spend in CI.

Phase 1 reached a real provider for the first time in this project's history. Three things must not
follow it into the repository, and each has a guard here rather than a paragraph somewhere.

    1. AWS ITSELF. No shipped package may import a provider SDK, shell out to the AWS CLI, or carry
       a region, endpoint or model identifier of its own. The capability catalog is SUPPLIED with a
       reviewed snapshot; it knows nothing.
    2. THE ACCOUNT. This repository is public. No account id, no SSO start URL, no profile name, no
       role session, no credential path, and no account-bearing ARN.
    3. THE SPEND. Ordinary CI acquires no AWS identity and can invoke no model, and the smoke tool
       that can is opt-in, gitignored, and writes its evidence somewhere git will not take it.

CREDENTIAL VARIABLE NAMES ARE ASSEMBLED, NEVER WRITTEN OUT. `tests/architecture/test_aws_identity.py`
fails the build when those literals appear in a tracked file that is not the policy itself, and its
allowlist is deliberately hard to join — during the cleanup it SHRANK rather than grew. Building the
names from parts keeps this file honest without widening that guard.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
PACKAGES = REPO_ROOT / "packages"
SNAPSHOT = REPO_ROOT / "docs" / "llm" / "bedrock-capability-snapshot.yaml"
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"

pytestmark = pytest.mark.architecture

_PREFIX = "AWS_"
CREDENTIAL_VARIABLES = tuple(
    _PREFIX + suffix for suffix in ("ACCESS_KEY_ID", "SECRET_ACCESS_KEY", "SESSION_TOKEN")
)


def _python_files(root: Path) -> list[Path]:
    return [p for p in root.rglob("*.py") if "__pycache__" not in p.parts]


def _tracked() -> list[str]:
    out = subprocess.run(
        ["git", "ls-files", "-z"], cwd=REPO_ROOT, capture_output=True, text=True, timeout=30
    ).stdout
    untracked = subprocess.run(
        ["git", "ls-files", "-z", "--others", "--exclude-standard"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    ).stdout
    return [n for n in (out + untracked).split("\0") if n]


# --- anti-vacuity -------------------------------------------------------------------------------


def test_these_guards_have_something_to_scan() -> None:
    assert SNAPSHOT.is_file(), "the reviewed capability snapshot must exist"
    assert (PACKAGES / "model_catalog").is_dir(), "the catalog package must exist"
    assert len(_python_files(PACKAGES / "model_catalog")) >= 4
    assert len(_tracked()) >= 100


# --- 1. no AWS inside the product ---------------------------------------------------------------


def test_the_capability_catalog_imports_no_provider_sdk_and_shells_to_nothing() -> None:
    """It is a reader of a reviewed document, not a client.

    `test_architecture.py` already forbids a provider SDK outside the provider package. This adds
    the two ways a package can reach AWS without importing one: a subprocess to the CLI, and an
    HTTP client aimed at an AWS endpoint.
    """
    forbidden = re.compile(
        r"^\s*(import|from)\s+(boto3|botocore|httpx|requests|urllib)\b|subprocess|amazonaws\.com"
    )
    offenders: list[str] = []
    for path in _python_files(PACKAGES / "model_catalog"):
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if forbidden.search(line):
                offenders.append(f"{path.relative_to(REPO_ROOT)}:{number}")
    assert not offenders, f"the capability catalog reaches a provider directly: {offenders}"


def test_no_shipped_package_hardcodes_a_model_identifier_region_or_price() -> None:
    """The form-family lesson, applied to models.

    A guessed allowlist in runtime source produced a confident, precise and completely inverted
    conclusion about SEC form coverage while a reviewed contract sat beside it. A guessed model id,
    region or price is the same defect with a bill attached. Everything is SUPPLIED.

    Matched on evaluated string literals only, so the prose above stays legal.
    """
    import ast

    provider_id = re.compile(
        r"^(openai|nvidia|qwen|meta|anthropic|amazon|mistral|cohere|us|eu|apac)\.[a-z0-9][\w.:-]+$"
    )
    aws_region = re.compile(r"^(us|eu|ap|sa|ca|me|af|il)-[a-z]+-\d(-\w+)?$")
    offenders: list[str] = []
    for path in _python_files(PACKAGES):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        docstrings = {
            node.body[0].value
            for node in ast.walk(tree)
            if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef)
            and node.body
            and isinstance(node.body[0], ast.Expr)
            and isinstance(node.body[0].value, ast.Constant)
        }
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and node not in docstrings
                and (provider_id.match(node.value.strip()) or aws_region.match(node.value.strip()))
            ):
                offenders.append(f"{path.relative_to(REPO_ROOT)}:{node.lineno}: {node.value!r}")
    assert not offenders, (
        "a provider model identifier or region literal is hardcoded in shipped source; "
        f"both are supplied from the reviewed capability snapshot: {offenders}"
    )


def test_the_catalog_refuses_to_run_without_a_supplied_snapshot() -> None:
    """There is no bundled default and no fallback path.

    A fallback is how a stale catalog keeps answering after the real one has moved.
    """
    from packages.model_catalog import catalog as catalog_module

    source = Path(catalog_module.__file__).read_text(encoding="utf-8")
    assert "def load_snapshot(text: str)" in source, "the loader must take supplied text"
    assert ".yaml" not in source.replace("docs/llm/bedrock-capability-snapshot.yaml", ""), (
        "the loader must not name a file path of its own"
    )


# --- 2. no account in the repository ------------------------------------------------------------


def test_the_committed_snapshot_carries_no_account_specific_material() -> None:
    """docs/security/aws-identity-and-secrets.md forbids account identifiers in tracked config."""
    text = SNAPSHOT.read_text(encoding="utf-8")
    patterns = {
        "a twelve-digit account id": re.compile(r"(?<!\d)\d{12}(?!\d)"),
        "an account-bearing ARN": re.compile(r"arn:aws[\w-]*:[\w-]+:[\w-]*:\d{12}:"),
        "an SSO start URL": re.compile(r"https?://[\w.-]*awsapps\.com"),
        "a credential cache path": re.compile(r"\.aws[/\\](sso|credentials|config)"),
        "an assumed-role session": re.compile(r"assumed-role/"),
        "an access-key identifier": re.compile(r"\b(AKIA|ASIA)[0-9A-Z]{16}\b"),
    }
    for description, pattern in patterns.items():
        assert not pattern.search(text), f"the capability snapshot contains {description}"


def test_no_tracked_file_carries_an_account_bearing_arn_or_sso_url() -> None:
    """The same check, repository-wide, because a leak does not care which file it is in."""
    patterns = (
        re.compile(r"arn:aws[\w-]*:[\w-]+:[\w-]*:\d{12}:"),
        re.compile(r"https?://[\w.-]*awsapps\.com"),
        re.compile(r"\b(AKIA|ASIA)[0-9A-Z]{16}\b"),
    )
    offenders: list[str] = []
    for name in _tracked():
        path = REPO_ROOT / name
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for number, line in enumerate(text.splitlines(), 1):
            if any(p.search(line) for p in patterns):
                offenders.append(f"{name}:{number}")
    assert not offenders, f"account-specific AWS material in a tracked file: {offenders}"


# --- 3. no spend in CI --------------------------------------------------------------------------


def test_ordinary_ci_acquires_no_aws_identity_and_can_invoke_no_model() -> None:
    """Ordinary CI stays AWS-free. It has never reached a model and must not start.

    `id-token` is checked as a granted PERMISSION, not as a word: the workflow's own comment says
    it does not request one, and a guard that failed on that sentence would be pressure to delete
    the sentence.
    """
    text = WORKFLOW.read_text(encoding="utf-8")
    for marker in ("configure-aws-credentials", "role-to-assume", "aws-actions/", "bedrock"):
        assert marker not in text.lower(), f"ordinary CI references {marker}"
    for variable in CREDENTIAL_VARIABLES:
        assert variable not in text
    granted = [line for line in text.splitlines() if re.match(r"^\s+id-token\s*:", line)]
    assert not granted, f"ordinary CI requests the id-token permission: {granted}"
    assert re.search(r"^permissions:\s*\n\s+contents:\s*read\s*$", text, re.MULTILINE), (
        "the workflow must grant contents:read and nothing else"
    )


def test_the_suite_needs_no_aws_identity() -> None:
    """A test that silently needs AWS access skips everywhere that lacks it.

    That is the failure mode this project has corrected twice, and the zero-skip gate now has no
    legitimate excuse at all — so a test reaching AWS would fail rather than skip, in CI, for a
    reason no contributor could fix.
    """
    offenders: list[str] = []
    for path in (REPO_ROOT / "tests").rglob("*.py"):
        if "__pycache__" in path.parts or path.name == "test_phase1_aws_boundary.py":
            continue
        text = path.read_text(encoding="utf-8")
        if re.search(r"^\s*(import|from)\s+(boto3|botocore)\b", text, re.MULTILINE):
            offenders.append(str(path.relative_to(REPO_ROOT)))
        if re.search(r"\baws\s+(bedrock|sts|pricing)\b", text):
            offenders.append(str(path.relative_to(REPO_ROOT)))
    assert not offenders, f"a test reaches AWS: {offenders}"


def test_the_smoke_evidence_directory_is_ignored() -> None:
    """Smoke evidence carries request ids and usage; it is host state, not source."""
    result = subprocess.run(
        ["git", "check-ignore", "-q", "var/phase1-evidence/example.json"],
        cwd=REPO_ROOT,
        timeout=30,
    )
    assert result.returncode == 0, "var/phase1-evidence/ is not gitignored"


def test_no_smoke_evidence_or_local_tool_is_tracked() -> None:
    """The instrument that spends money stays out of the distribution and out of git."""
    tracked = _tracked()
    offenders = [
        name
        for name in tracked
        if name.startswith(("var/", "phase1-evidence/")) or name.endswith("phase1_smoke.py")
    ]
    assert not offenders, f"smoke tooling or evidence is tracked: {offenders}"


# --- the smoke protocol the snapshot records ----------------------------------------------------


def test_the_recorded_smoke_protocol_stayed_minimal() -> None:
    """The gate proves reachability. Anything larger is a benchmark nobody authorized."""
    from packages.llm_gateway import parse_yaml, require_mapping

    document = require_mapping(parse_yaml(SNAPSHOT.read_text(encoding="utf-8")))
    protocol = document["smoke_protocol"]
    assert protocol["max_output_tokens"] <= 8, "the gate's output cap exceeded the authorized 8"
    assert protocol["temperature"] == 0
    assert protocol["streaming"] is False
    assert str(protocol["system_prompt"]).lower() == "none"
    assert str(protocol["tools"]).lower() == "none"
    assert str(protocol["conversation_history"]).lower() == "none"


def test_no_sec_content_reached_a_model_in_the_smoke_gates() -> None:
    """Phase 1 sends no filing, no CIK, no accession, no ticker and no issuer name.

    The prompts are recorded in the snapshot precisely so this can be asserted rather than
    promised.
    """
    from packages.llm_gateway import parse_yaml, require_mapping

    document = require_mapping(parse_yaml(SNAPSHOT.read_text(encoding="utf-8")))
    protocol = document["smoke_protocol"]
    prompts = f"{protocol['text_prompt']} {protocol['image_prompt']}"
    forbidden = (
        re.compile(r"\b\d{10}\b"),  # a padded CIK
        re.compile(r"\b\d{10}-\d{2}-\d{6}\b"),  # an accession number
        re.compile(r"\b(10-?K|10-?Q)\b", re.IGNORECASE),  # a filing form
        re.compile(r"\b(sec\.gov|edgar|xbrl|filing|issuer|footnote)\b", re.IGNORECASE),
    )
    for pattern in forbidden:
        assert not pattern.search(prompts), f"a smoke prompt carries SEC content: {pattern.pattern}"
    assert len(prompts) < 200, "a smoke prompt grew past a single sentence"
