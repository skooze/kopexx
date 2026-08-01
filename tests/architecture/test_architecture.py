"""Structural invariants from rules.md, enforced as tests.

These fail the build when the repository drifts toward a monolith or when a boundary rule is
bypassed. They read source text rather than importing, so a violation is caught even in a module
that is never imported by the test suite.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
PACKAGES = REPO_ROOT / "packages"
PROMPTS = REPO_ROOT / "prompts"


def _python_files(root: Path) -> list[Path]:
    return [p for p in root.rglob("*.py") if "__pycache__" not in p.parts]


pytestmark = pytest.mark.architecture


def test_bedrock_client_not_imported_outside_provider() -> None:
    """SECURITY-INVARIANT: only the provider adapter may construct a provider SDK client."""
    allowed = PACKAGES / "llm_gateway" / "providers"
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


def test_domain_layer_has_no_infrastructure_imports() -> None:
    """Dependency direction: the domain must not import frameworks or SDKs."""
    forbidden = re.compile(r"^\s*(import|from)\s+(fastapi|sqlalchemy|boto3|redis|httpx)\b")
    domain = PACKAGES / "domain"
    offenders: list[str] = []
    for path in _python_files(domain):
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if forbidden.match(line):
                offenders.append(f"{path.relative_to(REPO_ROOT)}:{number}")
    assert not offenders, f"domain layer imported infrastructure: {offenders}"


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
    if not PROMPTS.exists():
        pytest.skip("prompts directory not yet populated")
    markdown = [str(p.relative_to(REPO_ROOT)) for p in PROMPTS.rglob("*.md")]
    assert not markdown, (
        "model-visible prompt files must be .txt or .yaml, never .md: " + ", ".join(markdown)
    )


def test_prompts_do_not_request_prohibited_output_formats() -> None:
    """A prompt must never instruct a model to emit JSON, XML, or Markdown."""
    if not PROMPTS.exists():
        pytest.skip("prompts directory not yet populated")
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
    missing = [
        str(p.relative_to(REPO_ROOT))
        for p in PACKAGES.iterdir()
        if p.is_dir() and p.name != "__pycache__" and not (p / "__init__.py").exists()
    ]
    assert not missing, f"packages without a public interface: {missing}"
