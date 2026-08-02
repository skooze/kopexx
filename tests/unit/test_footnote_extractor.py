"""Extraction of the report inventory and note headings.

Runs against the committed `filing-summary.xml` fixtures, which are the real bytes SEC filed.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from packages.footnote_extractor import (
    NoteHeading,
    ReportInventoryError,
    document_lines,
    headings_are_contiguous,
    normalize_title,
    parse_headings,
    read_inventory,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "filings"
TEN_K = FIXTURES / "0000320193-25-000079" / "filing-summary.xml"


@pytest.fixture
def inventory():
    return read_inventory(TEN_K)


# --- the inventory --------------------------------------------------------------------------


def test_the_navigation_entry_is_not_a_report(inventory) -> None:
    """The 71st `<Report>` is `All Reports`, ReportType `Book` — the renderer's own contents page.

    It has no menu category, role, or file. Counting it puts every downstream total off by one,
    which is how a filing with 70 reports gets described as having 71.
    """
    assert len(inventory.reports) == 71
    assert len(inventory.real_reports) == 70
    assert len(inventory.navigation_reports) == 1
    assert inventory.navigation_reports[0].report_type == "Book"


def test_candidate_discovery_finds_the_notes_category(inventory) -> None:
    """Stage 1. Sixteen candidates, which is the count BEFORE item disclosures are removed."""
    assert len(inventory.candidates()) == 16
    assert all(r.menu_category == "Notes" for r in inventory.candidates())


def test_child_blocks_are_tables_details_and_policies(inventory) -> None:
    children = inventory.child_blocks()
    assert len(children) == 46
    assert {r.menu_category for r in children} == {"Tables", "Details", "Policies"}


def test_the_category_census_matches_the_filing(inventory) -> None:
    assert inventory.by_category() == {
        "Cover": 2,
        "Statements": 6,
        "Notes": 16,
        "Policies": 1,
        "Tables": 12,
        "Details": 33,
        "<none>": 1,
    }


def test_reports_are_ordered_by_filed_position(inventory) -> None:
    positions = [r.position for r in inventory.reports]
    assert positions == sorted(positions)


def test_external_ids_are_stable_and_unique(inventory) -> None:
    """`R9` matches the renderer's own file naming, so an operator can find the fragment."""
    ids = [r.external_id for r in inventory.real_reports]
    assert len(ids) == len(set(ids))
    assert all(i.startswith("R") for i in ids)


def test_an_unparseable_inventory_raises(tmp_path: Path) -> None:
    bad = tmp_path / "FilingSummary.xml"
    bad.write_text("<FilingSummary><MyReports>", encoding="utf-8")
    with pytest.raises(ReportInventoryError, match="not parseable"):
        read_inventory(bad)


def test_an_empty_inventory_raises_rather_than_returning_nothing(tmp_path: Path) -> None:
    """Zero reports and an unreadable file are indistinguishable downstream.

    Returning an empty inventory would produce a filing with no footnotes and no error.
    """
    empty = tmp_path / "FilingSummary.xml"
    empty.write_text("<FilingSummary><MyReports></MyReports></FilingSummary>", encoding="utf-8")
    with pytest.raises(ReportInventoryError, match="lists no reports"):
        read_inventory(empty)


def test_a_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(ReportInventoryError, match="cannot read"):
        read_inventory(tmp_path / "absent.xml")


# --- headings -------------------------------------------------------------------------------


def test_a_heading_split_across_two_elements_is_joined() -> None:
    """THE DEFECT THIS PREVENTS.

    Apple's FY2025 10-K renders `Note 1 –` and its title as separate elements. A pattern
    requiring both on one line finds ZERO headings in that filing — not a few, none — and stage 5
    silently confirms nothing while reporting success.
    """
    html = "<p>Note 1 –</p><p>Summary of Significant Accounting Policies</p><p>Body text.</p>"
    headings = parse_headings(html)
    assert len(headings) == 1
    assert headings[0].number == 1
    assert headings[0].title == "Summary of Significant Accounting Policies"
    assert headings[0].joined_from_next_line is True


def test_a_heading_on_one_line_is_parsed_directly() -> None:
    headings = parse_headings("<p>Note 2 — Revenue</p><p>Body.</p>")
    assert (headings[0].number, headings[0].title) == (2, "Revenue")
    assert headings[0].joined_from_next_line is False


@pytest.mark.parametrize(
    "raw",
    [
        "<p>Note 3 - Earnings Per Share</p>",
        "<p>Note 3 : Earnings Per Share</p>",
        "<p>NOTE 3. EARNINGS PER SHARE</p>",
        "<p>Note 3 — Earnings Per Share</p>",
    ],
)
def test_heading_separators_used_by_different_filing_agents(raw: str) -> None:
    headings = parse_headings(raw)
    assert len(headings) == 1 and headings[0].number == 3


def test_a_cross_reference_in_prose_is_not_a_second_heading() -> None:
    """`see Note 4` appears throughout a filing's body and is not a heading."""
    html = "<p>Note 4 –</p><p>Financial Instruments</p><p>As described in Note 4 - see above.</p>"
    assert len(parse_headings(html)) == 1


def test_prose_following_a_heading_marker_is_not_taken_as_a_title() -> None:
    """A long line after a bare marker is body text, not a title."""
    html = f"<p>Note 5 –</p><p>{'x' * 200}</p>"
    assert parse_headings(html) == ()


def test_headings_before_the_notes_section_are_ignored() -> None:
    html = (
        "<p>Note 9 - a reference in the statements</p>"
        "<p>Notes to Consolidated Financial Statements</p>"
        "<p>Note 1 –</p><p>Real Note</p>"
    )
    headings = parse_headings(html)
    assert [h.number for h in headings] == [1]


def test_contiguity_detects_a_missing_heading() -> None:
    """A gap means a heading was missed or a false one matched; the count cannot confirm anything."""
    good = (NoteHeading(1, "a", 0, False), NoteHeading(2, "b", 1, False))
    gapped = (NoteHeading(1, "a", 0, False), NoteHeading(3, "c", 1, False))
    assert headings_are_contiguous(good) is True
    assert headings_are_contiguous(gapped) is False
    assert headings_are_contiguous(()) is False


def test_an_empty_document_raises() -> None:
    from packages.footnote_extractor import PrimaryDocumentError

    with pytest.raises(PrimaryDocumentError):
        parse_headings("")


def test_script_and_style_content_is_not_text() -> None:
    html = "<script>var Note = 1;</script><p>Note 1 – Real</p>"
    assert [h.number for h in parse_headings(html)] == [1]


def test_document_lines_preserve_element_boundaries() -> None:
    """Each element becomes its own line, which is what makes the split heading detectable."""
    assert document_lines("<p>a</p><p>b</p>") == ["a", "b"]


# --- title normalization ---------------------------------------------------------------------


def test_typographic_apostrophes_normalize_to_one_form() -> None:
    """The renderer inventory and the document body spell the same title differently.

    `Shareholders’ Equity` against `Shareholders' Equity` is one note, and a raw comparison
    reports a mismatch that does not exist.
    """
    assert normalize_title("Shareholders’ Equity") == normalize_title("Shareholders' Equity")


def test_normalization_collapses_punctuation_and_case() -> None:
    assert normalize_title("Commitments, Contingencies and Supply") == (
        "commitments contingencies and supply"
    )


def test_normalization_is_for_comparison_not_replacement() -> None:
    """The displayed title is preserved separately; normalization never overwrites it."""
    heading = NoteHeading(10, "Shareholders’ Equity", 0, False)
    assert heading.title == "Shareholders’ Equity"
    assert heading.normalized_title == "shareholders' equity"
