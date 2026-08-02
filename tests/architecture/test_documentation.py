"""Structural checks on the repository's Markdown.

A broken fence is not a typo. An unclosed code block swallows every heading, link, and paragraph
after it, so a document can look fine in an editor and render on GitHub as one grey slab. Nothing
in the toolchain notices, because Markdown has no parse errors — it just renders the wrong thing.

These checks are deterministic and need no network, no renderer, and no linter binary.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

# Fallback only. The real answer comes from git; see _markdown_files.
SKIP_DIRS = {".venv", ".git", "node_modules", "var", "artifacts", ".pytest_cache"}

FENCE = re.compile(r"^\s{0,3}(```|~~~)")
HEADING = re.compile(r"^#{1,6} ")
LINK = re.compile(r"\[([^\]]*)\]\(([^)]+)\)")

pytestmark = pytest.mark.architecture


def _markdown_files() -> list[Path]:
    """Markdown the REPOSITORY owns: tracked files plus new ones that are not ignored.

    Asks git rather than walking the tree. A name-based skip list is a guess about what is not
    ours, and it was wrong: renaming `.venv` to `.venv-hidden` to reproduce the CI environment put
    a third-party package's README into the scan, and this check failed on a broken link inside a
    dependency. Git already knows exactly which files are the project's, ignore rules included.
    """
    try:
        tracked = subprocess.run(
            ["git", "ls-files", "-z", "*.md"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
        ).stdout
        untracked = subprocess.run(
            ["git", "ls-files", "-z", "--others", "--exclude-standard", "*.md"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
        ).stdout
        names = [n for n in (tracked + untracked).split("\0") if n]
        return sorted({REPO_ROOT / n for n in names})
    except (OSError, subprocess.SubprocessError):
        # No git available. Fall back to a walk so the check still runs rather than skipping.
        return sorted(
            p
            for p in REPO_ROOT.rglob("*.md")
            if not SKIP_DIRS.intersection(p.relative_to(REPO_ROOT).parts)
        )


def _walk(lines: list[str]):
    """Yield (line_number, line, inside_fence, language) the way a renderer sees the file.

    `language` is the fence's info string — `bash`, `toml`, or empty. It matters because `#` opens
    a comment in most of the languages fenced here, so a `# heading`-shaped line inside a labelled
    block is ordinary code and not a swallowed heading.
    """
    inside = False
    language = ""
    for number, line in enumerate(lines, 1):
        match = FENCE.match(line)
        if match:
            yield number, line, inside, language  # the marker belongs to the old state
            if inside:
                inside, language = False, ""
            else:
                inside, language = True, line.strip().lstrip("`~").strip().lower()
            continue
        yield number, line, inside, language


def test_markdown_files_exist_to_check() -> None:
    """Anti-vacuity: these checks must be scanning something."""
    files = _markdown_files()
    assert len(files) >= 20, f"only {len(files)} Markdown files found; the guard is not live"
    assert (REPO_ROOT / "README.md") in files


def test_every_fenced_code_block_is_closed() -> None:
    """An odd number of fences means everything after the last one renders as code.

    This is the specific defect: a README whose `## Getting started` block is never closed renders
    Databases, Layout, Design constraints, Documentation, and Contributing as one code block.

    Checks every file in one test rather than parametrizing over them. Per-file parametrization
    turned three checks into 234 test IDs, which inflates the suite count without adding signal —
    the message below already names the file and the line.
    """
    offenders = []
    for path in _markdown_files():
        opened_at = None
        inside = False
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if FENCE.match(line):
                if inside:
                    inside, opened_at = False, None
                else:
                    inside, opened_at = True, number
        if inside:
            offenders.append(f"{path.relative_to(REPO_ROOT)}: fence opened at line {opened_at}")

    assert not offenders, (
        "unclosed code fence(s); everything after each one renders as code: " + "; ".join(offenders)
    )


def test_no_heading_is_swallowed_by_a_code_block() -> None:
    """A heading inside a fence is a heading that will not appear in the rendered document.

    Catches the case an even fence count hides: two unclosed blocks that happen to pair up with
    each other, leaving the prose between them rendered as code.
    """
    swallowed = []
    for path in _markdown_files():
        for number, line, inside, language in _walk(path.read_text(encoding="utf-8").splitlines()):
            # Only unlabelled fences. In a ```bash or ```toml block, `# something` is a comment in
            # that language, not a heading that failed to render — flagging those made the check
            # cry wolf on a runbook that was perfectly correct.
            if inside and not language and HEADING.match(line):
                swallowed.append(f"{path.relative_to(REPO_ROOT)}:{number}: {line.strip()[:50]}")

    assert not swallowed, f"heading(s) inside a code block, so they will not render: {swallowed}"


def test_relative_links_resolve() -> None:
    """A link to a file that does not exist is a broken link on GitHub."""
    broken = []
    for path in _markdown_files():
        for number, line, inside, _language in _walk(path.read_text(encoding="utf-8").splitlines()):
            if inside:
                continue
            for label, target in LINK.findall(line):
                if target.startswith(("http://", "https://", "mailto:", "#")):
                    continue
                if not (path.parent / target.split("#")[0]).resolve().exists():
                    broken.append(f"{path.relative_to(REPO_ROOT)}:{number}: [{label}]({target})")

    assert not broken, f"broken relative link(s): {broken}"


def test_the_readme_renders_the_sections_it_promises() -> None:
    """The sections a reader is told exist must actually be headings, outside any code block."""
    lines = (REPO_ROOT / "README.md").read_text(encoding="utf-8").splitlines()
    rendered = {
        line.strip()
        for _number, line, inside, _language in _walk(lines)
        if not inside and HEADING.match(line)
    }
    for required in (
        "# Kopexx",
        "## Status",
        "## Getting started",
        "## Databases",
        "## Layout",
        "## Design constraints",
        "## Documentation",
        "## Contributing",
    ):
        assert required in rendered, f"README is missing a rendered heading: {required}"


def test_the_readme_stays_within_its_length_budget() -> None:
    """700 to 1,200 words. Below it the document stops being useful; above it nobody reads it."""
    words = len((REPO_ROOT / "README.md").read_text(encoding="utf-8").split())
    assert 700 <= words <= 1200, f"README is {words} words; the budget is 700 to 1200"


def test_no_password_bearing_database_url_in_tracked_markdown() -> None:
    """CREDENTIAL POSTURE. A username:password URL is a reusable credential shape.

    It was a Docker Compose-style placeholder and never a real secret, but a literal that can be
    copied into a real configuration has no place in tracked prose. The history of why it was
    removed is kept; the literal is not.
    """
    pattern = re.compile(r"postgresql(\+\w+)?://[^\s`<>()\"']+:[^\s`<>()\"'/]+@")
    offenders = []
    for path in _markdown_files():
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            match = pattern.search(line)
            if match and "<password>" not in match.group(0):
                offenders.append(f"{path.relative_to(REPO_ROOT)}:{number}")
    assert not offenders, f"password-bearing database URL in tracked Markdown: {offenders}"
