"""AWS-IDENTITY-AND-SECRETS-INVARIANT, enforced.

Kopexx never creates, accepts, manages, persists, logs, or transports raw AWS credentials. AWS
SDKs resolve and refresh temporary credentials through an external federated provider, workload
role, or OIDC-assumed role. These checks fail the build when a tracked file introduces a way for
application code to manage a credential itself.

An SDK holds temporary credential material in memory while signing a request; that is unavoidable
and is not what these checks are about. They are about code that obtains, accepts, copies, writes,
or transports those values.

They run today, before any AWS integration exists, because a credential convention is nearly
impossible to remove once code depends on it. The cheapest moment to forbid `aws_access_key_id=` is
before the first call site.

DISTINGUISHING UNSAFE CONFIGURATION FROM DOCUMENTATION. `docs/security/aws-identity-and-secrets.md`
names every prohibited field — it has to, to prohibit them — and so does this module. A pattern
match alone cannot tell the difference, so a narrow allowlist of specific paths carries the
documents that are ABOUT the rule. The allowlist names files, never patterns: relaxing a pattern
would blind the check everywhere at once, which is how a guard stops guarding.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

pytestmark = pytest.mark.security

# Files whose SUBJECT is the prohibition. They necessarily contain the forbidden names.
# Every entry is a specific path. No globs, no directories, no pattern relaxation.
POLICY_DOCUMENTS = frozenset(
    {
        "rules.md",
        "docs/security/aws-identity-and-secrets.md",
        "tests/architecture/test_aws_identity.py",
        "CHANGELOG.md",
        # `tests/architecture/test_deterministic_extraction.py` was allowlisted here while it
        # enforced the same prohibition for the deterministic extraction packages. Both it and
        # those packages are deleted, and the allowlist shrank rather than being carried forward —
        # an entry that outlives its file is an exemption nobody is watching.
    }
)

CREDENTIAL_VARIABLES = ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN")

# An SDK client or session constructed with explicit credential arguments.
EXPLICIT_CREDENTIAL_ARGUMENT = re.compile(
    r"\b(aws_access_key_id|aws_secret_access_key|aws_session_token)\s*="
)

# A credential embedded in a URL: scheme://user:secret@host.
#
# Two deliberate exclusions, each added after this pattern produced a real match:
#
#   PostgreSQL URLs. The database credential posture is governed separately, and the CI service
#   credential in the workflow is explicitly authorised. Excluding them took two attempts. A
#   `(?!postgresql)` lookahead alone does not work: `postgresql+psycopg://` also offers a word
#   boundary before `psycopg`, so the engine simply matched there instead. The lookbehind is what
#   closes that — a scheme preceded by `+` is a driver suffix, not a new URL.
#
#   `<placeholder>` forms. Documentation shows the SHAPE of a credential without carrying one, so
#   neither the user nor the secret portion may contain `<`.
CREDENTIAL_BEARING_URL = re.compile(
    r"(?<![+\w.-])(?!postgres)[a-z][a-z0-9+.-]*://[^\s/:@<]+:(?!//)[^\s/@<]+@"
)


# EMITTING the whole environment leaks whatever the provider chain put there.
#
# Scoped to emission, not to reading. `dict(os.environ)` as an input to a settings constructor is
# how configuration is supposed to work, and an earlier form of this pattern failed on
# packages/configuration/settings.py, which does exactly the right thing. What is dangerous is
# printing, logging, or serializing the mapping.
#
# The emitting call is matched by SHAPE rather than by a literal prefix. A first attempt required
# `logger.` and therefore missed `logging.getLogger(__name__).info(os.environ)` — the same leak
# spelled the way people actually spell it.
ENVIRONMENT_DUMP = re.compile(
    r"(?:\b(?:print|pprint|repr|str|log\w*)\s*\("
    r"|\.(?:info|debug|warning|warn|error|critical|exception|log|write)\s*\("
    r"|json\.dumps\s*\("
    r"|yaml\.dump\w*\s*\()"
    r"[^)\n]*\bos\.environ\b(?!\s*(?:\.get|\.setdefault|\.pop|\[))"
    r"|f[\"']\{[^}]*os\.environ"
)


def _tracked_files(*suffixes: str) -> list[Path]:
    """Repository-owned files, from git rather than a directory walk.

    A name-based skip list is a guess about what is not ours and has already been wrong once, when
    renaming `.venv` pulled a dependency's files into a scan.
    """
    import subprocess

    try:
        out = subprocess.run(
            ["git", "ls-files", "-z"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
        ).stdout
        untracked = subprocess.run(
            ["git", "ls-files", "-z", "--others", "--exclude-standard"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
        ).stdout
        names = [n for n in (out + untracked).split("\0") if n]
    except (OSError, subprocess.SubprocessError):  # pragma: no cover - git is always present here
        names = [
            str(p.relative_to(REPO_ROOT))
            for p in REPO_ROOT.rglob("*")
            if p.is_file() and ".venv" not in p.parts and ".git" not in p.parts
        ]

    if suffixes:
        names = [n for n in names if n.endswith(suffixes)]
    return [REPO_ROOT / n for n in sorted(names)]


def _relative(path: Path) -> str:
    return str(path.relative_to(REPO_ROOT))


def _is_policy_document(path: Path) -> bool:
    return _relative(path) in POLICY_DOCUMENTS


def _scan(pattern: re.Pattern[str], paths: list[Path], *, skip_policy: bool = True) -> list[str]:
    hits = []
    for path in paths:
        if skip_policy and _is_policy_document(path):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for number, line in enumerate(text.splitlines(), 1):
            if pattern.search(line):
                hits.append(f"{_relative(path)}:{number}")
    return hits


# --- anti-vacuity ---------------------------------------------------------------------------


def test_the_checks_have_something_to_scan() -> None:
    """A guard that scans nothing passes forever."""
    assert len(_tracked_files()) >= 100
    assert len(_tracked_files(".py")) >= 40
    for name in POLICY_DOCUMENTS:
        assert (REPO_ROOT / name).exists(), f"allowlisted path does not exist: {name}"


def test_the_allowlist_is_narrow_and_path_based() -> None:
    """The allowlist must name files, never directories or patterns.

    A directory entry would exempt everything later added to it, which is how an allowlist quietly
    becomes a disabled check.
    """
    for entry in POLICY_DOCUMENTS:
        assert not entry.endswith("/"), f"directory allowlist entry: {entry}"
        assert "*" not in entry and "?" not in entry, f"glob in allowlist: {entry}"
        assert (REPO_ROOT / entry).is_file(), f"allowlist entry is not a file: {entry}"
    assert len(POLICY_DOCUMENTS) <= 8, "the allowlist is growing; each entry weakens the check"


# --- credential variables in tracked files -----------------------------------------------------


@pytest.mark.parametrize("variable", CREDENTIAL_VARIABLES)
def test_no_credential_variable_in_tracked_configuration_or_code(variable: str) -> None:
    """The variables themselves must not appear outside the documents that prohibit them.

    Catches the whole family at once: a placeholder in .env.example, a workflow `env:` entry, a
    Compose file, a task definition, a settings reader, a Terraform variable.
    """
    offenders = _scan(re.compile(rf"\b{variable}\b"), _tracked_files())
    assert not offenders, (
        f"{variable} appears in tracked files that are not the policy itself. Kopexx uses "
        f"temporary credentials from the SDK provider chain: {offenders}"
    )


def test_env_example_has_no_aws_credential_placeholder() -> None:
    """An empty placeholder is not neutral.

    It documents an unsafe authentication design as the expected one and invites the reader to
    fill it in. AWS_PROFILE and AWS_REGION serve local configuration instead.
    """
    text = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")
    for variable in CREDENTIAL_VARIABLES:
        assert variable not in text, f".env.example offers a placeholder for {variable}"
    assert "AWS_REGION" in text, "AWS_REGION is the supported non-secret region setting"


# --- SDK construction -------------------------------------------------------------------------


def test_no_sdk_client_receives_explicit_credential_arguments() -> None:
    """boto3.client(..., aws_access_key_id=...) and every variant of it.

    Clients are constructed through a session or default construction, and the provider chain
    resolves identity.
    """
    offenders = _scan(EXPLICIT_CREDENTIAL_ARGUMENT, _tracked_files(".py", ".md", ".yml", ".yaml"))
    assert not offenders, (
        f"an SDK client or session is constructed with explicit credentials: {offenders}"
    )


def test_no_configuration_model_carries_an_access_key_field() -> None:
    """A settings dataclass with an `aws_access_key_id` field is a credential the app now holds.

    Scans the shipped source only. A field name is enough: once it exists, something fills it.
    """
    field_pattern = re.compile(
        r"^\s*(aws_access_key_id|aws_secret_access_key|aws_session_token|"
        r"access_key|secret_key|session_token)\s*[:=]"
    )
    offenders = _scan(field_pattern, _tracked_files(".py"))
    assert not offenders, f"configuration model exposes a credential field: {offenders}"


def test_no_direct_credential_source_is_read() -> None:
    """Reading ~/.aws/credentials, a federation cache, or CLI output bypasses the provider chain.

    The chain already handles all of these, refreshes them, and does not hand the values to the
    application. Reimplementing it means holding what it deliberately does not expose.
    """
    patterns = re.compile(
        r"(\.aws/credentials|\.aws[/\\]credentials|"
        r"get-session-token|get_session_token|"
        r"aws\s+sts\s+get-caller-identity\s*\|.*(key|token)|"
        r"botocore\.credentials\.Credentials\(|"
        r"get_frozen_credentials\(\))"
    )
    offenders = _scan(patterns, _tracked_files(".py"))
    assert not offenders, f"credential material read or frozen directly: {offenders}"


# --- deployment surfaces ----------------------------------------------------------------------


def test_no_terraform_provider_block_carries_credentials() -> None:
    """Terraform authenticates through a temporary federated or OIDC-assumed role."""
    terraform = _tracked_files(".tf", ".tfvars", ".tf.json")
    offenders = _scan(EXPLICIT_CREDENTIAL_ARGUMENT, terraform)
    offenders += _scan(re.compile(r"\b(access_key|secret_key|token)\s*="), terraform)
    assert not offenders, f"Terraform carries credential arguments: {offenders}"


def test_no_container_or_task_definition_injects_credentials() -> None:
    """ECS task roles supply identity. Nothing is injected as an environment variable."""
    surfaces = _tracked_files(
        ".yml", ".yaml", ".json", "Dockerfile", ".dockerfile", "docker-compose.yml"
    )
    pattern = re.compile("|".join(rf"\b{v}\b" for v in CREDENTIAL_VARIABLES))
    offenders = _scan(pattern, surfaces)
    assert not offenders, (
        f"container or task configuration injects raw AWS credentials: {offenders}"
    )


def test_no_workflow_stores_a_static_aws_key() -> None:
    """CI assumes a role through OIDC. Static keys are never GitHub secrets."""
    workflows = [p for p in _tracked_files(".yml", ".yaml") if ".github/workflows" in _relative(p)]
    assert workflows, "no workflows found; this guard would enforce nothing"

    pattern = re.compile(
        r"secrets\.AWS_ACCESS_KEY_ID|secrets\.AWS_SECRET_ACCESS_KEY|secrets\.AWS_SESSION_TOKEN"
        r"|aws-access-key-id\s*:|aws-secret-access-key\s*:"
    )
    offenders = _scan(pattern, workflows)
    assert not offenders, f"workflow stores a static AWS credential: {offenders}"


def test_the_ordinary_test_workflow_requires_no_aws_access() -> None:
    """A unit-test run must never need an AWS identity.

    A test that silently needs AWS access is a test that skips in every environment lacking it —
    the failure mode this project has already corrected twice.
    """
    text = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    for marker in ("configure-aws-credentials", "role-to-assume", "aws-actions/"):
        assert marker not in text, (
            f"the default CI workflow acquires AWS identity ({marker}); it must not need one"
        )


# --- secrets, logs, and URLs -------------------------------------------------------------------


def test_no_secrets_manager_entry_is_intended_to_hold_an_aws_key() -> None:
    """Storing an AWS key in Secrets Manager makes the design circular.

    The workload would need embedded AWS credentials to fetch AWS credentials, and the embedded
    ones are exactly what this policy eliminates.
    """
    pattern = re.compile(
        r"(secret\w*[_-]?(name|id|arn)\s*[:=].*(access[_-]?key|secret[_-]?key|session[_-]?token)"
        r"|(access[_-]?key|aws[_-]?credential)\w*\s*[:=].*secretsmanager)",
        re.IGNORECASE,
    )
    offenders = _scan(pattern, _tracked_files(".py", ".yml", ".yaml", ".json", ".tf", ".md"))
    assert not offenders, f"a Secrets Manager entry appears to hold an AWS key: {offenders}"


def test_no_credential_bearing_url_in_tracked_files() -> None:
    """scheme://user:secret@host is a credential wherever it appears."""
    offenders = _scan(
        CREDENTIAL_BEARING_URL, _tracked_files(".py", ".md", ".yml", ".yaml", ".toml", ".example")
    )
    assert not offenders, f"credential-bearing URL in a tracked file: {offenders}"


def test_no_application_code_dumps_the_whole_environment() -> None:
    """A full environment dump leaks whatever the provider chain placed there."""
    source = [
        p for p in _tracked_files(".py") if _relative(p).startswith(("packages/", "scripts/"))
    ]
    offenders = _scan(ENVIRONMENT_DUMP, source)
    assert not offenders, f"application code dumps the environment: {offenders}"


def test_credential_field_names_are_centrally_redacted() -> None:
    """Redaction lives in one place so a new logger cannot forget it."""
    from packages.observability.logging import REDACTED_FIELDS

    for name in (
        "aws_access_key_id",
        "aws_secret_access_key",
        "aws_session_token",
        "access_key_id",
        "secret_access_key",
        "session_token",
        "authorization",
        "x_amz_security_token",
        "signature",
        "credentials",
        "secret_value",
    ):
        assert name in REDACTED_FIELDS, f"{name} is not centrally redacted"


def test_the_mock_provider_needs_no_aws_identity() -> None:
    """Sprint 4 must not require AWS authentication, and the default suite never does."""
    from packages.llm_gateway.providers.mock import MockProvider

    source = (REPO_ROOT / "packages" / "llm_gateway" / "providers" / "mock.py").read_text(
        encoding="utf-8"
    )
    assert "boto3" not in source and "botocore" not in source
    assert MockProvider is not None
