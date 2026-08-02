"""Note headings parsed from the primary document.

This is the input to canonicalization stage 5, which independently confirms the count the renderer
inventory produced and supplies the number and title as the filing displays them.

THE HEADING IS NOT ONE STRING. Apple's FY2025 10-K renders `Note 1 –` and
`Summary of Significant Accounting Policies` as two separate elements. A pattern requiring the
number and title on one line finds ZERO headings in that filing — not a few, none — and stage 5
would silently confirm nothing while reporting success. So a number-only heading is joined with
the text that follows it, and the joined form is what the tests assert.

WHY NOT A REAL HTML PARSER. The document is one large inline-XBRL file whose note boundaries are
presentational, not structural: there is no element that contains exactly one note. Tag-stripping
to a line sequence and matching heading shapes is what the structure actually supports. The raw
offsets are preserved so any parse can be checked against the bytes.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from pathlib import Path

from .errors import PrimaryDocumentError

# The heading shapes observed across filing agents. Each captures a number and, where the agent
# puts it on the same line, a title.
#
# `Note 1 –` (en dash), `NOTE 1.`, `Note 1 —` (em dash), `Note 1:` and bare `Note 1`.
HEADING_PATTERNS = (
    re.compile(r"^Note\s+(?P<number>\d{1,2})\s*[–—:.-]\s*(?P<title>.*)$", re.IGNORECASE),
    re.compile(r"^NOTE\s+(?P<number>\d{1,2})\s*[–—:.-]?\s*(?P<title>.*)$"),
)

# Where the notes section begins. Used to ignore heading-shaped text in the statements above it.
NOTES_SECTION_MARKERS = (
    "notes to consolidated financial statements",
    "notes to condensed consolidated financial statements",
    "notes to the consolidated financial statements",
    "notes to financial statements",
)

# A title longer than this is prose that happened to follow a heading, not a title.
MAX_TITLE_CHARS = 120


@dataclass(frozen=True)
class NoteHeading:
    """One `Note N — Title` heading as the filing displays it."""

    number: int
    title: str
    line_index: int
    joined_from_next_line: bool

    @property
    def normalized_title(self) -> str:
        """Lowercased, punctuation-collapsed, for comparison only.

        The displayed form is preserved separately and is what a reader sees. Normalization exists
        to compare two spellings of one title, never to replace the filed one.
        """
        return normalize_title(self.title)


def normalize_title(title: str) -> str:
    """Collapse a title to a comparable form.

    Typographic apostrophes and dashes differ between the renderer inventory and the document body
    for the same note — `Shareholders’ Equity` against `Shareholders' Equity` — so a comparison on
    raw text reports a mismatch that does not exist.
    """
    text = html.unescape(title)
    text = text.replace("’", "'").replace("‘", "'")
    text = text.replace("“", '"').replace("”", '"')
    text = re.sub(r"[‐-―]", "-", text)
    text = re.sub(r"[^\w\s'-]", " ", text)
    return re.sub(r"\s+", " ", text).strip().lower()


def document_lines(raw: str) -> list[str]:
    """Reduce an inline-XBRL document to an ordered sequence of visible text lines.

    Each tag becomes a line break, so text the renderer displayed as a separate block stays a
    separate line. That is what makes the split-heading case detectable.
    """
    text = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", raw)
    text = re.sub(r"<[^>]+>", "\n", text)
    text = html.unescape(text)
    text = text.replace("\xa0", " ")
    return [line.strip() for line in text.split("\n") if line.strip()]


def _notes_section_start(lines: list[str]) -> int:
    """Index of the first line of the notes section, or 0 when no marker is present.

    Returning 0 rather than failing is deliberate: a filing without the marker still has headings,
    and refusing to look would lose them. The cost is that heading-shaped text earlier in the
    document is considered, which the number-sequence check below then rejects.
    """
    for index, line in enumerate(lines):
        if line.strip().lower().rstrip(":") in NOTES_SECTION_MARKERS:
            return index
    return 0


def parse_headings(raw: str) -> tuple[NoteHeading, ...]:
    """Every note heading in the document, in filed order.

    A heading whose title is empty on its own line is joined with the following line, which is how
    the renderer splits `Note 1 –` from its title.
    """
    lines = document_lines(raw)
    if not lines:
        raise PrimaryDocumentError("the primary document yielded no text lines")

    start = _notes_section_start(lines)
    found: list[NoteHeading] = []
    seen_numbers: set[int] = set()

    for index in range(start, len(lines)):
        line = lines[index]
        for pattern in HEADING_PATTERNS:
            match = pattern.match(line)
            if not match:
                continue

            number = int(match.group("number"))
            title = match.group("title").strip()
            joined = False

            if not title and index + 1 < len(lines):
                candidate = lines[index + 1].strip()
                if candidate and len(candidate) <= MAX_TITLE_CHARS:
                    title, joined = candidate, True

            if not title or len(title) > MAX_TITLE_CHARS:
                break

            # One heading per number. A note number repeated later is a cross-reference in prose
            # ("see Note 4"), not a second heading, and the first occurrence is the real one.
            if number in seen_numbers:
                break

            seen_numbers.add(number)
            found.append(
                NoteHeading(
                    number=number, title=title, line_index=index, joined_from_next_line=joined
                )
            )
            break

    return tuple(found)


def read_headings(path: Path) -> tuple[NoteHeading, ...]:
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except OSError as error:
        raise PrimaryDocumentError(f"cannot read {path}: {error}") from error
    return parse_headings(raw)


def headings_are_contiguous(headings: tuple[NoteHeading, ...]) -> bool:
    """True when the numbers run 1..N with no gap.

    A gap means a heading was missed or a false one was matched, and either way the count cannot
    be used to confirm the renderer's.
    """
    numbers = [h.number for h in headings]
    return bool(numbers) and numbers == list(range(1, len(numbers) + 1))
