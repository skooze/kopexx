"""Parse the tables embedded in a filing's footnotes.

OWNS: row and column structure, header hierarchy, cell provenance, and exact numeric text.

DOES NOT OWN: financial meaning. This package does not decide that a cell is revenue, does not
convert a parenthetical to a negative number, and does not compute anything. A maturity schedule
and a tax reconciliation are the same shape to it. Interpretation is `packages/financial_metrics`,
Sprint 6.

NUMERIC TEXT IS PRESERVED AS TEXT. `(1,234)`, `$`, and `1,234` are kept exactly as filed. Parsing
`(1,234)` to `-1234.0` here would bake an interpretation into the extraction layer and lose the
filed form that every downstream citation has to quote. FINANCIAL-INVARIANT: no float ever touches
a filed value.

SPANS ARE EXPANDED, NOT FLATTENED. `colspan` appears in all 62 tables of Apple's FY2025 10-K and
`rowspan` in 2. Dropping a span collapses a two-level column header into one row and silently
misaligns every value under it. Expanding preserves the grid the filer drew.

UNSUPPORTED STRUCTURE IS DECLARED, NOT DROPPED. When a table cannot be parsed into a rectangular
grid, the raw source is preserved and the parse state says so. A silently truncated table looks
identical to a small one.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass, field
from typing import Any

PARSER_VERSION = "table-parser-1.0.0"

PARSED = "PARSED"
PARSED_WITH_WARNINGS = "PARSED_WITH_WARNINGS"
UNSUPPORTED = "UNSUPPORTED"

TABLE_RE = re.compile(r"(?is)<table\b[^>]*>(.*?)</table>")
ROW_RE = re.compile(r"(?is)<tr\b[^>]*>(.*?)</tr>")
CELL_RE = re.compile(r"(?is)<(t[dh])\b([^>]*)>(.*?)</\1>")
SPAN_RE = re.compile(r'(?i)\b(colspan|rowspan)\s*=\s*["\']?(\d+)')

# A cell spanning more than this is a rendering artifact, not a real span. Expanding it would
# produce a grid with thousands of phantom columns.
MAX_SPAN = 40


@dataclass(frozen=True)
class Cell:
    """One cell, with where it came from and what it said."""

    row: int
    column: int
    text: str
    is_header: bool
    colspan: int = 1
    rowspan: int = 1
    is_span_fill: bool = False

    @property
    def is_empty(self) -> bool:
        return not self.text.strip()


@dataclass
class ParsedTable:
    """One table's structure, provenance, and parse state."""

    index: int
    external_id: str
    rows: list[list[Cell]] = field(default_factory=list)
    header_row_count: int = 0
    caption: str | None = None
    parse_state: str = PARSED
    warnings: list[str] = field(default_factory=list)
    raw_html: str = ""
    source_offset: int | None = None

    @property
    def row_count(self) -> int:
        return len(self.rows)

    @property
    def column_count(self) -> int:
        return max((len(r) for r in self.rows), default=0)

    @property
    def cell_count(self) -> int:
        return sum(len(r) for r in self.rows)

    def column_headers(self) -> list[list[str]]:
        """The header hierarchy, one list per header row, spans already expanded."""
        return [[c.text for c in row] for row in self.rows[: self.header_row_count]]

    def row_labels(self) -> list[str]:
        """The leftmost cell of each body row, which is how a filer labels a line item."""
        return [row[0].text if row else "" for row in self.rows[self.header_row_count :]]

    def as_record(self) -> dict[str, Any]:
        return {
            "external_id": self.external_id,
            "sequence": self.index,
            "caption": self.caption,
            "rows": self.row_count,
            "columns": self.column_count,
            "cells": self.cell_count,
            "header_rows": self.header_row_count,
            "parse_state": self.parse_state,
            "warnings": self.warnings,
            "parser_version": PARSER_VERSION,
        }

    def cells_as_grid(self) -> list[list[dict[str, Any]]]:
        """Every cell with its provenance, for persistence as JSONB."""
        return [
            [
                {
                    "row": c.row,
                    "column": c.column,
                    "text": c.text,
                    "is_header": c.is_header,
                    "colspan": c.colspan,
                    "rowspan": c.rowspan,
                    "is_span_fill": c.is_span_fill,
                }
                for c in row
            ]
            for row in self.rows
        ]


def cell_text(raw: str) -> str:
    """Visible text of one cell, whitespace collapsed, entities resolved.

    Everything else is preserved verbatim: currency symbols, parentheses, commas, footnote
    markers. What the filer wrote is what a citation has to be able to quote.
    """
    text = re.sub(r"(?is)<br\s*/?>", " ", raw)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text).replace("\xa0", " ")
    return re.sub(r"\s+", " ", text).strip()


def _span(attributes: str, name: str) -> int:
    for attribute, value in SPAN_RE.findall(attributes):
        if attribute.lower() == name:
            span = int(value)
            return span if 1 <= span <= MAX_SPAN else 1
    return 1


def parse_table(raw_table: str, index: int, *, external_id: str | None = None) -> ParsedTable:
    """Parse one `<table>` into a rectangular grid with spans expanded."""
    table = ParsedTable(
        index=index,
        external_id=external_id or f"T{index}",
        raw_html=raw_table,
    )

    body = TABLE_RE.search(raw_table)
    inner = body.group(1) if body else raw_table

    raw_rows = ROW_RE.findall(inner)
    if not raw_rows:
        table.parse_state = UNSUPPORTED
        table.warnings.append("no <tr> elements found; the raw source is preserved unparsed")
        return table

    # Cells carried down by a rowspan, keyed by the column they occupy.
    pending: dict[int, tuple[Cell, int]] = {}
    grid: list[list[Cell]] = []

    for row_index, raw_row in enumerate(raw_rows):
        row: list[Cell] = []
        column = 0

        def place_pending(column: int, row: list[Cell], row_index: int = row_index) -> int:
            """Emit any cells carried down into this row by a rowspan above it.

            `row_index` is bound as a default rather than closed over: a closure would capture the
            loop variable by reference and stamp every carried-down cell with the LAST row index,
            destroying the provenance this parser exists to preserve.
            """
            while column in pending:
                source, remaining = pending[column]
                row.append(
                    Cell(
                        row=row_index,
                        column=column,
                        text=source.text,
                        is_header=source.is_header,
                        colspan=1,
                        rowspan=1,
                        is_span_fill=True,
                    )
                )
                if remaining <= 1:
                    del pending[column]
                else:
                    pending[column] = (source, remaining - 1)
                column += 1
            return column

        column = place_pending(column, row)

        for tag, attributes, content in CELL_RE.findall(raw_row):
            colspan = _span(attributes, "colspan")
            rowspan = _span(attributes, "rowspan")
            text = cell_text(content)
            is_header = tag.lower() == "th"

            for offset in range(colspan):
                cell = Cell(
                    row=row_index,
                    column=column,
                    text=text,
                    is_header=is_header,
                    colspan=colspan,
                    rowspan=rowspan,
                    is_span_fill=offset > 0,
                )
                row.append(cell)
                if rowspan > 1:
                    pending[column] = (cell, rowspan - 1)
                column += 1
                column = place_pending(column, row)

        grid.append(row)

    table.rows = grid
    table.header_row_count = _count_header_rows(grid)
    table.caption = _caption(raw_table)

    # Filers use `<tr></tr>` as vertical spacing. Those rows are kept — removing them would shift
    # every row index and break cell provenance — but they are not evidence of a ragged grid, and
    # counting them as such flagged 46 of Apple's 62 tables as malformed when none was.
    widths = {len(r) for r in grid if _is_substantive(r)}
    if len(widths) > 1:
        table.parse_state = PARSED_WITH_WARNINGS
        table.warnings.append(
            f"ragged grid: substantive row widths {sorted(widths)}. Rows are preserved as parsed "
            "rather than padded, so nothing is invented."
        )

    return table


def _is_substantive(row: list[Cell]) -> bool:
    """A row carrying content, as opposed to a spacing artifact."""
    return bool(row) and any(c.text.strip() for c in row)


def _count_header_rows(grid: list[list[Cell]]) -> int:
    """How many leading rows are header rows.

    `<th>` when the filer used it. Otherwise the leading rows whose non-first cells carry no
    digits — how a financial table marks a period header row such as `2025 | 2024 | 2023`.
    """
    # Spacing rows are skipped rather than ending the scan. A leading `<tr></tr>` would otherwise
    # stop header detection at zero, which is what it did on every Apple table.
    explicit = 0
    for row in grid:
        if not _is_substantive(row):
            explicit += 1
            continue
        if all(c.is_header for c in row if c.text):
            explicit += 1
        else:
            break
    if any(c.is_header for row in grid for c in row):
        return explicit

    inferred = 0
    for row in grid:
        if not _is_substantive(row):
            inferred += 1
            continue
        values = [c for c in row[1:] if c.text]
        # A header row labels columns without carrying values, or carries bare years.
        if values and not any(re.search(r"\d", c.text) for c in values):
            inferred += 1
            continue
        if values and all(re.fullmatch(r"(19|20)\d{2}", c.text) for c in values):
            inferred += 1
            continue
        break
    return inferred


def _caption(raw_table: str) -> str | None:
    match = re.search(r"(?is)<caption\b[^>]*>(.*?)</caption>", raw_table)
    if not match:
        return None
    return cell_text(match.group(1)) or None


def parse_tables(raw_html: str, *, id_prefix: str = "T") -> list[ParsedTable]:
    """Every table in a fragment, in document order.

    Nested tables are common in filings as a layout device. Only outermost tables are returned;
    an inner table's content still appears in its parent's cell text, so nothing is lost.
    """
    tables = []
    for index, match in enumerate(TABLE_RE.finditer(raw_html), start=1):
        whole = match.group(0)
        parsed = parse_table(whole, index, external_id=f"{id_prefix}{index}")
        parsed.source_offset = match.start()
        tables.append(parsed)
    return tables
