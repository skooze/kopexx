"""Sprint 4 is deterministic, enforced.

Canonicalization must reach the same answer every time from the same bytes. A model in this path
would make the note count non-reproducible, make the 13-not-58 result unverifiable, and spend
budget during a test run.

These checks are structural: they read imports rather than running code, so a violation is caught
in a module the suite never imports.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
PACKAGES = REPO_ROOT / "packages"

# The three packages Sprint 4 created. Every one must reach its answer without a model, a network
# call, or an AWS identity.
DETERMINISTIC_PACKAGES = ("footnote_extractor", "footnote_canonicalizer", "table_parser")

FORBIDDEN_IMPORTS = (
    "llm_gateway",
    "boto3",
    "botocore",
    "openai",
    "anthropic",
    "httpx",
    "requests",
    "urllib.request",
    "aiohttp",
)

# `packages.llm_gateway.parse_yaml` is the project's SAFE YAML reader and is not a model call. It
# is the same parser the content boundary uses, and reading a definition file with it is the
# correct choice: `yaml.load` would open an arbitrary code path. Only this symbol is permitted,
# and only for that purpose.
PERMITTED_LLM_GATEWAY_SYMBOLS = frozenset({"parse_yaml"})

pytestmark = pytest.mark.architecture


def _modules(package: str) -> list[Path]:
    return sorted(p for p in (PACKAGES / package).rglob("*.py") if "__pycache__" not in p.parts)


def _imports(path: Path) -> list[tuple[int, str, tuple[str, ...]]]:
    """Every import in a module as (line, module, imported names)."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                found.append((node.lineno, alias.name, ()))
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.append((node.lineno, node.module, tuple(a.name for a in node.names)))
    return found


def test_the_packages_exist_and_have_modules() -> None:
    """Anti-vacuity. A guard scanning an absent package enforces nothing."""
    for package in DETERMINISTIC_PACKAGES:
        assert (PACKAGES / package).is_dir(), f"{package} does not exist"
        assert len(_modules(package)) >= 2, f"{package} has too few modules to be substantive"


@pytest.mark.parametrize("package", DETERMINISTIC_PACKAGES)
def test_no_model_or_network_import(package: str) -> None:
    """No model SDK, no HTTP client, no AWS SDK anywhere in the deterministic path."""
    offenders = []
    for path in _modules(package):
        for line, module, names in _imports(path):
            for forbidden in FORBIDDEN_IMPORTS:
                if module == forbidden or module.startswith(f"{forbidden}."):
                    # One narrow exception, by symbol, for the safe YAML reader.
                    if forbidden == "llm_gateway" and set(names) <= PERMITTED_LLM_GATEWAY_SYMBOLS:
                        continue
                    offenders.append(f"{path.name}:{line}: {module} {list(names)}")
                if module.endswith(f".{forbidden}"):
                    if forbidden == "llm_gateway" and set(names) <= PERMITTED_LLM_GATEWAY_SYMBOLS:
                        continue
                    offenders.append(f"{path.name}:{line}: {module} {list(names)}")
    assert not offenders, f"{package} imports a model, network, or AWS dependency: {offenders}"


@pytest.mark.parametrize("package", DETERMINISTIC_PACKAGES)
def test_no_model_invocation_call(package: str) -> None:
    """No call that would reach a provider, even through an indirect name."""
    pattern = re.compile(
        r"\b(invoke_model|converse|bedrock|complete\(|chat\.completions|messages\.create)\b"
    )
    offenders = []
    for path in _modules(package):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                target = ast.unparse(node.func)
                if pattern.search(target):
                    offenders.append(f"{path.name}:{node.lineno}: {target}")
    assert not offenders, f"{package} calls a model: {offenders}"


@pytest.mark.parametrize("package", DETERMINISTIC_PACKAGES)
def test_no_http_url_literal(package: str) -> None:
    """No endpoint literal. Input is preserved bytes on disk, never a fetch.

    Role URIs in test data look like URLs but are identifiers, never dereferenced — so only
    literals that would plausibly be called are flagged, by looking for an API-shaped host.
    """
    pattern = re.compile(r"https?://[^\s\"']*(api|endpoint|amazonaws|openai|anthropic)", re.I)
    offenders = []
    for path in _modules(package):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and pattern.search(node.value)
            ):
                offenders.append(f"{path.name}:{node.lineno}: {node.value[:60]}")
    assert not offenders, f"{package} carries an endpoint literal: {offenders}"


@pytest.mark.parametrize("package", DETERMINISTIC_PACKAGES)
def test_no_aws_credential_reference(package: str) -> None:
    """AWS-IDENTITY-AND-SECRETS-INVARIANT applies here too."""
    pattern = re.compile(r"AWS_ACCESS_KEY_ID|AWS_SECRET_ACCESS_KEY|AWS_SESSION_TOKEN")
    offenders = [
        f"{path.name}"
        for path in _modules(package)
        if pattern.search(path.read_text(encoding="utf-8"))
    ]
    assert not offenders, f"{package} references AWS credentials: {offenders}"


def test_the_canonicalizer_does_not_parse_html_tables() -> None:
    """OWNERSHIP BOUNDARY. Table parsing belongs to `table_parser`.

    The canonicalizer importing a table parser would put two owners on one concern, and the next
    change would land in whichever file the author opened first.
    """
    offenders = []
    for path in _modules("footnote_canonicalizer"):
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                target = ast.unparse(node.func)
                if target in ("parse_table", "parse_tables"):
                    offenders.append(f"{path.name}:{node.lineno}")
    assert not offenders, f"the canonicalizer parses tables itself: {offenders}"


def test_the_extractor_does_not_import_grouping_policy() -> None:
    """OWNERSHIP BOUNDARY. The extractor reports what a filing contains; it decides nothing."""
    offenders = []
    for path in _modules("footnote_extractor"):
        for line, module, _ in _imports(path):
            if "footnote_canonicalizer" in module:
                offenders.append(f"{path.name}:{line}")
    assert not offenders, f"the extractor depends on grouping policy: {offenders}"


def test_the_table_parser_computes_no_financial_meaning() -> None:
    """No float conversion of a cell, and no arithmetic on filed values.

    FINANCIAL-INVARIANT: a filed number is preserved as the text it was filed as. `float("1,234")`
    or a Decimal conversion here would bake an interpretation into the extraction layer.
    """
    offenders = []
    for path in _modules("table_parser"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                target = ast.unparse(node.func)
                if target in ("float", "Decimal", "int") and "text" in ast.unparse(node):
                    offenders.append(f"{path.name}:{node.lineno}: {ast.unparse(node)[:60]}")
    assert not offenders, f"the table parser converts filed text to a number: {offenders}"


def test_stages_six_through_eleven_are_not_implemented() -> None:
    """Only stages 1 to 5 are in scope.

    A fallback that never runs against the available fixtures would be untested code carrying the
    authority of tested code. The grouping methods for later stages exist in the schema vocabulary
    but must not be produced by this sprint's code.
    """
    source = "\n".join(
        path.read_text(encoding="utf-8") for path in _modules("footnote_canonicalizer")
    )
    tree = ast.parse(source)
    produced = {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }
    for later_stage in (
        "presentation_hierarchy",
        "concept_overlap",
        "title_similarity",
        "filing_order",
        "model_adjudication",
    ):
        assert later_stage not in produced, (
            f"{later_stage} is a stage 6-11 grouping method and is out of scope for Sprint 4"
        )
