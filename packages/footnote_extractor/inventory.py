"""The renderer's report inventory, read from `FilingSummary.xml`.

SEC's renderer produces one `<Report>` per rendered fragment and categorises each with a menu
category. That inventory is the deterministic input to canonicalization: it names every candidate
footnote and every child disclosure block, with the role URI that connects them.

WHY NOT PARSE THE DOCUMENT FOR THIS. The primary document is one HTML file with no machine-readable
boundary between notes. The inventory is structured, published by SEC itself, and carries the role
URIs that make grouping deterministic rather than heuristic. Reading it is the difference between
an algorithm and a guess.

COUNTING INVARIANT. One `<Report>` in Apple's FY2025 10-K is `All Reports`, `ReportType: Book` —
the renderer's own table of contents, with no menu category, role, or file. It is a navigation
entry, not a report. Counting it puts every downstream total off by one, so it is excluded here and
the exclusion is asserted by a test.
"""

from __future__ import annotations

import xml.etree.ElementTree as ElementTree
from dataclasses import dataclass
from pathlib import Path

from .errors import ReportInventoryError

# Menu categories the renderer assigns. `Notes` supplies footnote candidates; the three child
# categories supply the disclosure blocks that attach to them.
NOTES_CATEGORY = "Notes"
CHILD_CATEGORIES = ("Tables", "Details", "Policies")
STATEMENT_CATEGORIES = ("Cover", "Statements")

# The navigation entry, identified by what it lacks rather than by its name, so a filing that
# titles it differently is still recognised.
NAVIGATION_REPORT_TYPE = "Book"


@dataclass(frozen=True)
class RendererReport:
    """One `<Report>` element, reduced to the fields canonicalization uses."""

    position: int
    menu_category: str | None
    short_name: str | None
    long_name: str | None
    role: str | None
    html_file_name: str | None
    xml_file_name: str | None
    report_type: str | None

    @property
    def external_id(self) -> str:
        """A stable identifier for this report within its filing.

        The renderer's position is stable for a given filed document, and the document is
        immutable once filed. `R9` matches the renderer's own file naming, so an operator can find
        the fragment this block came from.
        """
        return f"R{self.position}"

    @property
    def is_navigation(self) -> bool:
        return self.report_type == NAVIGATION_REPORT_TYPE or (
            self.menu_category is None and self.role is None
        )

    @property
    def is_candidate_note(self) -> bool:
        return self.menu_category == NOTES_CATEGORY

    @property
    def is_child_block(self) -> bool:
        return self.menu_category in CHILD_CATEGORIES


def _text(element: ElementTree.Element, tag: str) -> str | None:
    found = element.findtext(tag)
    if found is None:
        return None
    stripped = found.strip()
    return stripped or None


@dataclass(frozen=True)
class ReportInventory:
    """Every report in one filing, in filed order."""

    reports: tuple[RendererReport, ...]
    source_sha256: str
    source_path: str

    @property
    def real_reports(self) -> tuple[RendererReport, ...]:
        """Reports excluding the renderer's navigation entry."""
        return tuple(r for r in self.reports if not r.is_navigation)

    @property
    def navigation_reports(self) -> tuple[RendererReport, ...]:
        return tuple(r for r in self.reports if r.is_navigation)

    def candidates(self) -> tuple[RendererReport, ...]:
        """Stage 1 output: every report the renderer filed under `Notes`."""
        return tuple(r for r in self.real_reports if r.is_candidate_note)

    def child_blocks(self) -> tuple[RendererReport, ...]:
        return tuple(r for r in self.real_reports if r.is_child_block)

    def by_category(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for report in self.reports:
            key = report.menu_category or "<none>"
            counts[key] = counts.get(key, 0) + 1
        return counts


def read_inventory(path: Path) -> ReportInventory:
    """Parse `FilingSummary.xml` into an ordered report inventory.

    Fails closed on an unreadable or empty inventory. A filing whose inventory yields no reports
    would otherwise produce a filing with no footnotes and no error, which is indistinguishable
    from a filing that genuinely has none.
    """
    from packages.storage import sha256_file

    try:
        raw = path.read_bytes()
    except OSError as error:
        raise ReportInventoryError(f"cannot read {path}: {error}") from error

    try:
        root = ElementTree.fromstring(raw)
    except ElementTree.ParseError as error:
        raise ReportInventoryError(f"{path.name} is not parseable XML: {error}") from error

    container = root.find("MyReports")
    if container is None:
        raise ReportInventoryError(f"{path.name} has no MyReports element")

    reports = []
    for index, element in enumerate(container.findall("Report"), start=1):
        position_text = _text(element, "Position")
        reports.append(
            RendererReport(
                # Position is authoritative when present; the element order is the fallback, so a
                # filing agent that omits it still yields a stable, ordered inventory.
                position=int(position_text) if position_text and position_text.isdigit() else index,
                menu_category=_text(element, "MenuCategory"),
                short_name=_text(element, "ShortName"),
                long_name=_text(element, "LongName"),
                role=_text(element, "Role"),
                html_file_name=_text(element, "HtmlFileName"),
                xml_file_name=_text(element, "XmlFileName"),
                report_type=_text(element, "ReportType"),
            )
        )

    if not reports:
        raise ReportInventoryError(
            f"{path.name} lists no reports. An empty inventory is refused rather than returned: "
            "it is indistinguishable from a filing with no footnotes."
        )

    return ReportInventory(
        reports=tuple(sorted(reports, key=lambda r: r.position)),
        source_sha256=sha256_file(path),
        source_path=str(path),
    )
