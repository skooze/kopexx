"""Structural invariants from rules.md, enforced as tests.

These fail the build when the repository drifts toward a monolith or when a boundary rule is
bypassed. They read source text rather than importing, so a violation is caught even in a module
that is never imported by the test suite.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
PACKAGES = REPO_ROOT / "packages"
PROMPTS = REPO_ROOT / "prompts"


def _python_files(root: Path) -> list[Path]:
    return [p for p in root.rglob("*.py") if "__pycache__" not in p.parts]


def _real_packages() -> list[Path]:
    """Package directories that contain a module beyond __init__.py."""
    found = []
    for path in PACKAGES.iterdir():
        if not path.is_dir() or path.name == "__pycache__":
            continue
        if any(p.name != "__init__.py" for p in _python_files(path)):
            found.append(path)
    return found


pytestmark = pytest.mark.architecture


def test_architecture_suite_has_something_to_check() -> None:
    """Anti-vacuity guard.

    Sprint 1 created eighteen packages holding only a docstring. Several architecture tests
    scanned those empty directories and passed while enforcing nothing. This test fails if the
    scanned surface ever collapses again, so a green architecture suite cannot mean 'no code'.
    """
    packages = _real_packages()
    assert len(packages) >= 5, (
        f"architecture tests scan only {len(packages)} substantive package(s); "
        "the suite is not meaningfully enforcing anything"
    )
    assert len(_python_files(PACKAGES)) >= 20, "too few modules scanned for the suite to be live"


def test_no_package_is_an_empty_stub() -> None:
    """A directory holding only __init__.py reserves a name and enforces nothing.

    Create a package when its code arrives, not twenty sprints ahead of it. Reserved names
    belong in techspecs.md section 2, which carries a status column.
    """
    stubs = [
        str(path.relative_to(REPO_ROOT))
        for path in PACKAGES.iterdir()
        if path.is_dir()
        and path.name != "__pycache__"
        and all(p.name == "__init__.py" for p in _python_files(path))
    ]
    assert not stubs, (
        "empty package stubs create vacuous architecture tests and inflate the apparent "
        f"surface of the project: {stubs}"
    )


def test_bedrock_client_not_imported_outside_provider() -> None:
    """SECURITY-INVARIANT: only the provider adapter may construct a provider SDK client."""
    allowed = PACKAGES / "llm_gateway" / "providers"
    assert allowed.is_dir(), "the provider package must exist for this guard to be live"
    offenders: list[str] = []
    pattern = re.compile(r"^\s*(import\s+boto3|from\s+boto3|import\s+botocore|from\s+botocore)")
    for path in _python_files(PACKAGES):
        if allowed in path.parents:
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if pattern.match(line):
                offenders.append(f"{path.relative_to(REPO_ROOT)}:{number}")
    assert not offenders, (
        "provider SDK imported outside packages/llm_gateway/providers: " + ", ".join(offenders)
    )


def test_no_runtime_package_hardcodes_a_filing_form_allowlist() -> None:
    """PRODUCT-DIRECTION-INVARIANT: qualifying-family logic is supplied, never guessed in code.

    `packages/filing_discovery` shipped `ANNUAL_FORMS = ("10-K", "10-K405", "10-KSB")` and
    `QUARTERLY_FORMS = ("10-Q", "10-QSB")` for four sprints, matching on the part before `/A`.
    EDGAR's real submission types are UNHYPHENATED — `10KSB`, `10QSB`, `10KSB40`, `10KT405` — so
    that filter matched none of the small-business family and none of the transition family, while
    a committed contract adjudicating all 41 observed strings sat beside it in the repository. The
    reconciliation that existed to catch a discovery gap applied the same filter to the master
    index, so both sides agreed perfectly and reported a complete history that was missing roughly
    190,000 filings' worth of form coverage.

    The qualifying set is now a REQUIRED argument with no default. This guard fails if a literal
    form string is written back into runtime source.
    """
    # Parsed rather than grepped, so only STRING LITERALS THE CODE EVALUATES are inspected.
    # A comment or a docstring naming a form is fine and is how the history above stays readable;
    # a tuple or set of them the interpreter can match against is the defect. A line-based scan
    # cannot tell those apart and would fail on this test's own explanation.
    form_literal = re.compile(r"^(10-?K|10-?Q)(SB|T|405|SB40|T405)?(/A)?$", re.IGNORECASE)
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
                and form_literal.match(node.value.strip())
            ):
                offenders.append(f"{path.relative_to(REPO_ROOT)}:{node.lineno}: {node.value!r}")
    assert not offenders, (
        "a filing-form allowlist is hardcoded in runtime source. Qualifying forms are supplied by "
        f"the caller from the reviewed contract: {offenders}"
    )


def test_no_generic_utils_module() -> None:
    """rules.md prohibits a catch-all dumping ground."""
    offenders = [
        str(p.relative_to(REPO_ROOT))
        for p in PACKAGES.rglob("*.py")
        if p.stem in {"utils", "helpers", "misc", "common"}
    ]
    assert not offenders, f"generic dumping-ground modules are prohibited: {offenders}"


def test_sec_identity_logic_has_a_single_home() -> None:
    """No package other than sec_identity may reimplement CIK or accession normalization."""
    padding = re.compile(r"zfill\(10\)|:010d|rjust\(10")
    offenders: list[str] = []
    for path in _python_files(PACKAGES):
        if path.parts[-2] == "sec_identity":
            continue
        text = path.read_text(encoding="utf-8")
        for number, line in enumerate(text.splitlines(), 1):
            if line.strip().startswith("#"):
                continue
            if padding.search(line):
                offenders.append(f"{path.relative_to(REPO_ROOT)}:{number}")
    assert not offenders, "CIK padding reimplemented outside packages/sec_identity: " + ", ".join(
        offenders
    )


# Packages that are pure logic and must stay free of infrastructure, per the dependency
# direction in rules.md section 4. Add to this set as each lower-layer package is created;
# the test below fails if a listed package is missing, so the list cannot silently go stale.
PURE_LOGIC_PACKAGES = ("sec_identity",)


def test_pure_logic_packages_have_no_infrastructure_imports() -> None:
    """Dependency direction: lower layers must not import frameworks or SDKs.

    This replaces an earlier test that scanned packages/domain. That directory held only a
    docstring, so the test passed without reading a single import. It now scans packages that
    actually contain logic, and fails if a named package does not exist.
    """
    forbidden = re.compile(r"^\s*(import|from)\s+(fastapi|sqlalchemy|boto3|redis|httpx)\b")
    offenders: list[str] = []
    for name in PURE_LOGIC_PACKAGES:
        package = PACKAGES / name
        assert package.is_dir(), (
            f"{name} is listed as pure logic but does not exist; "
            "update PURE_LOGIC_PACKAGES rather than letting this guard go vacuous"
        )
        modules = _python_files(package)
        assert modules, f"{name} contains no modules, so this guard would enforce nothing"
        for path in modules:
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if forbidden.match(line):
                    offenders.append(f"{path.relative_to(REPO_ROOT)}:{number}")
    assert not offenders, f"pure-logic package imported infrastructure: {offenders}"


def test_no_prompt_strings_embedded_in_packages() -> None:
    """Prompts live in prompts/, versioned, never inline in application code."""
    marker = re.compile(r"(You are an? (expert|assistant|analyst)|system_prompt\s*=\s*[\"'])")
    allowed_files = {"mock.py"}  # the mock provider carries a canned response, not a prompt
    offenders: list[str] = []
    for path in _python_files(PACKAGES):
        if path.name in allowed_files:
            continue
        text = path.read_text(encoding="utf-8")
        if marker.search(text):
            offenders.append(str(path.relative_to(REPO_ROOT)))
    assert not offenders, f"prompt text embedded in application code: {offenders}"


def test_prompt_directory_contains_no_markdown() -> None:
    """LLM-SERIALIZATION-INVARIANT: model-visible prompts must not be Markdown."""
    assert PROMPTS.is_dir(), "prompts/ must exist; a skip here would hide a boundary regression"
    markdown = [str(p.relative_to(REPO_ROOT)) for p in PROMPTS.rglob("*.md")]
    assert not markdown, (
        "model-visible prompt files must be .txt or .yaml, never .md: " + ", ".join(markdown)
    )


def test_prompts_do_not_request_prohibited_output_formats() -> None:
    """A prompt must never instruct a model to emit JSON, XML, or Markdown."""
    assert PROMPTS.is_dir(), "prompts/ must exist; a skip here would hide a boundary regression"
    prohibited = re.compile(
        r"(return\s+json|respond\s+in\s+json|json\s+schema|output_config\.format|"
        r"application/json|xml\s+output|markdown\s+table|```)",
        re.IGNORECASE,
    )
    offenders: list[str] = []
    for path in (
        list(PROMPTS.rglob("*.txt"))
        + list(PROMPTS.rglob("*.yaml"))
        + list(PROMPTS.rglob("*.jinja"))
    ):
        text = path.read_text(encoding="utf-8")
        if prohibited.search(text):
            offenders.append(str(path.relative_to(REPO_ROOT)))
    assert not offenders, f"prompt instructs a prohibited output format: {offenders}"


def test_every_package_exposes_a_public_interface() -> None:
    """Cross-package private imports are prohibited, so each package needs an __init__."""
    directories = [p for p in PACKAGES.iterdir() if p.is_dir() and p.name != "__pycache__"]
    assert directories, "no packages found; this guard would enforce nothing"
    missing = [
        str(p.relative_to(REPO_ROOT)) for p in directories if not (p / "__init__.py").exists()
    ]
    assert not missing, f"packages without a public interface: {missing}"


def test_model_visible_prompts_have_exactly_one_home() -> None:
    """A prompt copied into docs/ drifts from the one under prompts/ and nothing notices.

    rules.md section 10 puts prompts under prompts/. Sprint 1 also left a byte-identical copy
    of the Deep Analysis system prompt in docs/, where no architecture test scans it. Two homes
    for one model-visible artifact is a drift defect waiting to happen.
    """
    canonical = {
        path.read_text(encoding="utf-8").strip() for path in PROMPTS.rglob("*") if path.is_file()
    }
    duplicates = [
        str(path.relative_to(REPO_ROOT))
        for path in (REPO_ROOT / "docs").rglob("*")
        if path.is_file()
        and path.suffix in {".txt", ".jinja"}
        and path.read_text(encoding="utf-8").strip() in canonical
    ]
    assert not duplicates, (
        "model-visible prompt content duplicated outside prompts/; "
        f"delete the copy and reference the canonical file instead: {duplicates}"
    )
