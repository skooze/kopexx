"""Table structure, cell provenance, and exact numeric text.

Every fixture here is a shape that appears in the four Apple filings. Cases the fixtures do not
contain are not invented: a parser for structure nobody has is untested code with the authority of
tested code.
"""

from __future__ import annotations

import pytest

from packages.table_parser import (
    PARSED,
    PARSED_WITH_WARNINGS,
    UNSUPPORTED,
    cell_text,
    parse_table,
    parse_tables,
)

SIMPLE = """
<table>
  <tr><th>Year</th><th>Revenue</th></tr>
  <tr><td>2025</td><td>416,161</td></tr>
  <tr><td>2024</td><td>391,035</td></tr>
</table>
"""

MULTIROW_HEADER = """
<table>
  <tr><th rowspan="2">Segment</th><th colspan="2">Net sales</th></tr>
  <tr><th>2025</th><th>2024</th></tr>
  <tr><td>Americas</td><td>167,045</td><td>167,045</td></tr>
</table>
"""

NUMERIC_SHAPES = """
<table>
  <tr><td>Currency</td><td>$</td><td>1,234</td></tr>
  <tr><td>Negative</td><td>(4,567)</td><td></td></tr>
  <tr><td>Marker</td><td>1,234 (1)</td><td>&nbsp;</td></tr>
  <tr><td>Scale</td><td>in millions</td><td>%</td></tr>
</table>
"""


def parse_one(html: str):
    return parse_table(html, 1)


# --- structure -------------------------------------------------------------------------------


def test_a_simple_table_parses_to_a_grid() -> None:
    table = parse_one(SIMPLE)
    assert table.parse_state == PARSED
    assert table.row_count == 3
    assert table.column_count == 2
    assert table.header_row_count == 1
    assert table.column_headers() == [["Year", "Revenue"]]
    assert table.row_labels() == ["2025", "2024"]


def test_colspan_is_expanded_not_flattened() -> None:
    """A colspan collapsed to one cell misaligns every value under it.

    All 62 tables in Apple's FY2025 10-K use colspan, so this is the common case, not an edge one.
    """
    table = parse_one(MULTIROW_HEADER)
    assert table.rows[0][1].text == "Net sales"
    assert table.rows[0][2].text == "Net sales"
    assert table.rows[0][2].is_span_fill is True
    assert table.rows[0][1].is_span_fill is False


def test_rowspan_carries_a_cell_into_the_following_row() -> None:
    table = parse_one(MULTIROW_HEADER)
    assert table.rows[0][0].text == "Segment"
    assert table.rows[1][0].text == "Segment"
    assert table.rows[1][0].is_span_fill is True


def test_a_carried_down_cell_records_the_row_it_appears_in() -> None:
    """THE DEFECT THIS PREVENTS.

    A closure over the loop variable stamped every carried-down cell with the LAST row index,
    destroying the provenance this parser exists to preserve. The value is bound explicitly.
    """
    table = parse_one(MULTIROW_HEADER)
    carried = table.rows[1][0]
    assert carried.is_span_fill and carried.row == 1


def test_a_multirow_header_hierarchy_is_preserved() -> None:
    table = parse_one(MULTIROW_HEADER)
    assert table.header_row_count == 2
    assert len(table.column_headers()) == 2


def test_every_cell_records_its_own_coordinates() -> None:
    table = parse_one(SIMPLE)
    for row_index, row in enumerate(table.rows):
        for column_index, cell in enumerate(row):
            assert cell.row == row_index
            assert cell.column == column_index


# --- numeric text, preserved exactly ------------------------------------------------------------


def test_a_parenthetical_negative_is_preserved_verbatim() -> None:
    """FINANCIAL-INVARIANT. `(4,567)` is not converted to -4567.

    Parsing it here would bake an interpretation into the extraction layer and lose the filed form
    every citation has to quote. Interpretation is Sprint 6.
    """
    table = parse_one(NUMERIC_SHAPES)
    assert table.rows[1][1].text == "(4,567)"


def test_a_currency_symbol_survives_as_its_own_cell() -> None:
    assert parse_one(NUMERIC_SHAPES).rows[0][1].text == "$"


def test_thousands_separators_are_not_stripped() -> None:
    assert parse_one(NUMERIC_SHAPES).rows[0][2].text == "1,234"


def test_a_footnote_marker_stays_attached_to_its_value() -> None:
    assert parse_one(NUMERIC_SHAPES).rows[2][1].text == "1,234 (1)"


def test_a_scale_label_is_text_not_a_number() -> None:
    assert parse_one(NUMERIC_SHAPES).rows[3][1].text == "in millions"


def test_an_empty_cell_stays_empty_rather_than_disappearing() -> None:
    """A dropped empty cell shifts every value to its right into the wrong column."""
    table = parse_one(NUMERIC_SHAPES)
    assert table.rows[1][2].text == ""
    assert table.rows[1][2].is_empty
    assert len(table.rows[1]) == 3


def test_a_non_breaking_space_cell_is_empty_not_whitespace() -> None:
    assert parse_one(NUMERIC_SHAPES).rows[2][2].is_empty


def test_no_float_conversion_occurs_anywhere() -> None:
    for row in parse_one(NUMERIC_SHAPES).rows:
        for cell in row:
            assert isinstance(cell.text, str)


# --- text extraction ---------------------------------------------------------------------------


def test_cell_text_resolves_entities_and_collapses_whitespace() -> None:
    assert cell_text("<b>Net&nbsp;sales</b>\n  and   more") == "Net sales and more"


def test_cell_text_preserves_punctuation_that_carries_meaning() -> None:
    assert cell_text("<span>$ (1,234)</span>") == "$ (1,234)"


# --- parse state, declared honestly ----------------------------------------------------------


def test_a_table_with_no_rows_is_unsupported_not_empty() -> None:
    """A silently truncated table looks identical to a small one. The raw source is preserved."""
    table = parse_table("<table><p>not a row</p></table>", 1)
    assert table.parse_state == UNSUPPORTED
    assert table.raw_html
    assert table.warnings


def test_a_ragged_grid_is_reported_not_padded() -> None:
    ragged = "<table><tr><td>a</td><td>b</td></tr><tr><td>c</td></tr></table>"
    table = parse_table(ragged, 1)
    assert table.parse_state == PARSED_WITH_WARNINGS
    assert "ragged" in table.warnings[0]
    # Nothing invented: the short row stays short.
    assert len(table.rows[1]) == 1


def test_a_spacing_row_does_not_count_as_ragged() -> None:
    """Filers use `<tr></tr>` for vertical spacing.

    Counting those as ragged flagged 46 of Apple's 62 tables as malformed when none was.
    """
    spaced = "<table><tr></tr><tr><td>a</td><td>b</td></tr><tr></tr></table>"
    assert parse_table(spaced, 1).parse_state == PARSED


def test_a_leading_spacing_row_does_not_defeat_header_detection() -> None:
    spaced = "<table><tr></tr><tr><th>Year</th><th>Value</th></tr><tr><td>2025</td><td>1</td></tr></table>"
    assert parse_table(spaced, 1).header_row_count >= 1


def test_an_absurd_span_is_ignored_rather_than_expanded() -> None:
    """A colspan of 9999 is a rendering artifact; expanding it yields thousands of phantom cells."""
    table = parse_table('<table><tr><td colspan="9999">x</td></tr></table>', 1)
    assert len(table.rows[0]) == 1


# --- provenance and identity ---------------------------------------------------------------------


def test_tables_are_numbered_in_document_order() -> None:
    tables = parse_tables(SIMPLE + NUMERIC_SHAPES)
    assert [t.external_id for t in tables] == ["T1", "T2"]
    assert tables[0].source_offset < tables[1].source_offset


def test_each_table_records_where_it_came_from() -> None:
    table = parse_tables(SIMPLE)[0]
    assert table.source_offset is not None
    assert table.raw_html.startswith("<table")


def test_a_caption_is_captured_when_present() -> None:
    table = parse_one("<table><caption>Maturities</caption><tr><td>a</td></tr></table>")
    assert table.caption == "Maturities"


def test_the_record_carries_the_parser_version() -> None:
    """Two runs of different parser versions must be distinguishable in the database."""
    record = parse_one(SIMPLE).as_record()
    assert record["parser_version"]
    assert record["parse_state"] == PARSED


def test_the_cell_grid_serializes_with_full_provenance() -> None:
    grid = parse_one(MULTIROW_HEADER).cells_as_grid()
    first = grid[0][0]
    assert set(first) >= {
        "row",
        "column",
        "text",
        "is_header",
        "colspan",
        "rowspan",
        "is_span_fill",
    }


@pytest.mark.parametrize("html", ["", "<p>no tables here</p>"])
def test_a_fragment_with_no_tables_yields_none(html: str) -> None:
    assert parse_tables(html) == []
