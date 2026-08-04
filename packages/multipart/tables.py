"""Reading a STRUCTURED TABLE a model returned. Structure only, meaning never.

WHY THIS EXISTS AT ALL. `table_count` was ZERO in all seven Phase 2.1 proof runs. Not one candidate
emitted a structured table from a financial filing on either the 1996 10-K405 or the 2025 10-Q/A.
No prompt in that phase asked for one, so it measured unprompted behaviour rather than capability —
and it left the largest open question of the proof untouched, because a filing parser that cannot
preserve a table structure has not parsed a financial filing.

    NARRATIVE REPETITION OF A NUMBER IS NOT A TABLE. Phase 2.1's candidates carried tabular
    material as node content and as source quotes, and the numeric validator confirmed the numbers
    occurred in the preserved bytes. That proves a number appears in the filing. It does not
    preserve which row and which column and which period it belonged to, and those three facts are
    what a table IS.

WHAT THIS MODULE MAY REQUIRE. That a table names itself, that its cells declare a grid position,
that a span is a positive integer. Shape, and nothing else.

WHAT IT IS FORBIDDEN TO REQUIRE, AND IT WOULD BE VERY EASY TO. A vocabulary of table types. A fixed
set of unit strings. A required period-label format. A rule that a financial statement has a header
row. `rules.md` section 21 rule 2 forbids a universal filing taxonomy without explicit user
approval, and a table schema is the most tempting place in this entire system to build one: every
financial filing does have income statements, and the moment `type` is validated against a list,
the backend has decided what a filing contains.

    `type_label`, `unit`, `period_label`, `title` AND EVERY ROW ROLE ARE THE MODEL'S OWN WORDS.
    They are carried verbatim, displayed, and never checked against anything.

EVERY UNKNOWN KEY SURVIVES in `extra`, for the same reason it does in `envelopes.py`: the point of
running several candidates through a new contract is to find out what they actually emit.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Final

from .identity import require_part_identifier, storage_token

#: The provisional minimum envelope of one structured table. Its ABSENCE is a FINDING, never a
#: refusal — a table missing its source anchors is still a table, and discarding it would destroy
#: the measurement this contract exists to make.
TABLE_ENVELOPE_KEYS: Final[tuple[str, ...]] = ("table_id", "source_member", "rows")

_KNOWN_TABLE_KEYS = frozenset(
    {
        "table_id",
        "title",
        "type",
        "source_member",
        "source_table_id",
        "source_anchor_start",
        "source_anchor_end",
        "header_rows",
        "rows",
        "footer_rows",
        "continues_table_id",
        "continued_by_table_id",
        "image_dependency",
        "unresolved_cells",
        "classification",
        "classification_evidence",
        "metadata",
    }
)
_KNOWN_CELL_KEYS = frozenset(
    {
        "row",
        "column",
        "row_span",
        "column_span",
        "text",
        "value",
        "unit",
        "period_label",
        "is_header",
        "unresolved",
    }
)


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _rows(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _positive(value: Any, default: int = 1) -> int:
    return (
        value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else default
    )


def _index(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


@dataclass(frozen=True)
class TableCell:
    """One cell of a model-returned table.

    `text` is what the model says the source cell reads. `value` is an OPTIONAL normalisation the
    model may offer. They are kept apart deliberately and validated differently: `text` is checked
    against the preserved bytes, and `value` is never checked against anything, because a
    normalised number is an interpretation and `rules.md` invariant 14 keeps backend code out of
    those.
    """

    row: int
    column: int
    row_span: int
    column_span: int
    text: str
    value: str
    unit: str
    period_label: str
    is_header: bool
    unresolved: bool
    extra: dict[str, Any] = field(default_factory=dict)

    def to_mapping(self) -> dict[str, Any]:
        return {
            "row": self.row,
            "column": self.column,
            "row_span": self.row_span,
            "column_span": self.column_span,
            "text": self.text,
            "value": self.value,
            "unit": self.unit,
            "period_label": self.period_label,
            "is_header": self.is_header,
            "unresolved": self.unresolved,
            "model_supplied_extra": self.extra,
        }


@dataclass(frozen=True)
class StructuredTable:
    """One table a model returned as structure rather than as prose.

    `source_table_id` is the mechanical inventory's identifier for the `table` element this table
    claims to represent. It is the model's claim; `packages/completeness` checks whether the
    element exists and whether the cells it names occur in that element's bytes.
    """

    table_id: str
    storage_token: str
    title: str
    type_label: str
    source_member: str
    source_table_id: str
    source_anchor_start: str
    source_anchor_end: str
    cells: tuple[TableCell, ...]
    continues_table_id: str
    continued_by_table_id: str
    image_dependency: bool
    unresolved_cells: tuple[dict[str, Any], ...]
    classification: str
    classification_evidence: str
    metadata: dict[str, Any]
    missing_envelope_keys: tuple[str, ...]
    extra: dict[str, Any]
    raw: dict[str, Any]

    @property
    def row_count(self) -> int:
        return max((c.row for c in self.cells), default=-1) + 1

    @property
    def column_count(self) -> int:
        return max((c.column + c.column_span for c in self.cells), default=0)

    @property
    def header_cell_count(self) -> int:
        return sum(1 for c in self.cells if c.is_header)

    @property
    def unresolved_cell_count(self) -> int:
        return sum(1 for c in self.cells if c.unresolved) + len(self.unresolved_cells)

    def to_mapping(self) -> dict[str, Any]:
        return {
            "table_id": self.table_id,
            "storage_token": self.storage_token,
            "title": self.title,
            "type": self.type_label,
            "source_member": self.source_member,
            "source_table_id": self.source_table_id,
            "source_anchor_start": self.source_anchor_start[:200],
            "source_anchor_end": self.source_anchor_end[:200],
            "row_count": self.row_count,
            "column_count": self.column_count,
            "cell_count": len(self.cells),
            "header_cell_count": self.header_cell_count,
            "unresolved_cell_count": self.unresolved_cell_count,
            "continues_table_id": self.continues_table_id,
            "continued_by_table_id": self.continued_by_table_id,
            "image_dependency": self.image_dependency,
            "classification": self.classification,
            "classification_evidence": self.classification_evidence,
            "missing_envelope_keys": list(self.missing_envelope_keys),
            "metadata": self.metadata,
            "model_supplied_extra": self.extra,
            "cells": [c.to_mapping() for c in self.cells],
            "classification_note": (
                "classification and type are the MODEL's words. Nothing in this repository checks "
                "either against a vocabulary, and a human reviewer may overrule both."
            ),
        }


def _read_cells(raw_rows: Any, *, header: bool, row_offset: int) -> tuple[list[TableCell], int]:
    """Read one block of rows. Returns the cells and the next free row index.

    TWO SHAPES ARE ACCEPTED AND BOTH ARE THE MODEL'S CHOICE. A row may be a LIST of cells, in which
    case position is implied by order, or a cell may carry explicit `row` and `column` integers. A
    contract that accepted only one would measure which shape the prompt happened to suggest.
    """
    cells: list[TableCell] = []
    next_row = row_offset
    for row_index, raw_row in enumerate(_rows(raw_rows)):
        implied_row = row_offset + row_index
        column_cursor = 0
        for raw_cell in _rows(raw_row) if isinstance(raw_row, list) else [raw_row]:
            mapping = _mapping(raw_cell)
            if not mapping:
                # A bare scalar in a row is a cell whose text is that scalar. Filings' simplest
                # tables come back this way and refusing them would lose real structure.
                mapping = {"text": "" if raw_cell is None else str(raw_cell)}
            declared_row = _index(mapping.get("row"))
            declared_column = _index(mapping.get("column"))
            row = implied_row if declared_row is None else declared_row
            column = column_cursor if declared_column is None else declared_column
            span = _positive(mapping.get("column_span"))
            cells.append(
                TableCell(
                    row=row,
                    column=column,
                    row_span=_positive(mapping.get("row_span")),
                    column_span=span,
                    text=str(mapping.get("text") or ""),
                    value="" if mapping.get("value") is None else str(mapping.get("value")),
                    unit=str(mapping.get("unit") or ""),
                    period_label=str(mapping.get("period_label") or ""),
                    is_header=bool(mapping.get("is_header")) or header,
                    unresolved=bool(mapping.get("unresolved")),
                    extra={k: v for k, v in mapping.items() if k not in _KNOWN_CELL_KEYS},
                )
            )
            column_cursor = column + span
            next_row = max(next_row, row + 1)
    return cells, next_row


def read_table(raw: Any) -> StructuredTable | None:
    """Read one structured table from a part response. Returns None when it names no identifier.

    A table with no identifier cannot be cited, compared, reviewed or linked to a source element.
    It is DROPPED here and REPORTED by validation, which reads the raw list — rather than raising,
    which would throw away a part whose other tables are fine. The same discipline `read_plan` uses
    for a part with no identifier.
    """
    mapping = _mapping(raw)
    identifier = str(mapping.get("table_id") or "").strip()
    if not identifier:
        return None
    require_part_identifier(identifier)

    header_cells, cursor = _read_cells(mapping.get("header_rows"), header=True, row_offset=0)
    body_cells, cursor = _read_cells(mapping.get("rows"), header=False, row_offset=cursor)
    footer_cells, _ = _read_cells(mapping.get("footer_rows"), header=False, row_offset=cursor)

    return StructuredTable(
        table_id=identifier,
        storage_token=storage_token(identifier),
        title=str(mapping.get("title") or ""),
        type_label=str(mapping.get("type") or ""),
        source_member=str(mapping.get("source_member") or ""),
        source_table_id=str(mapping.get("source_table_id") or ""),
        source_anchor_start=str(mapping.get("source_anchor_start") or ""),
        source_anchor_end=str(mapping.get("source_anchor_end") or ""),
        cells=tuple(header_cells + body_cells + footer_cells),
        continues_table_id=str(mapping.get("continues_table_id") or ""),
        continued_by_table_id=str(mapping.get("continued_by_table_id") or ""),
        image_dependency=bool(mapping.get("image_dependency")),
        unresolved_cells=tuple(
            item for item in _rows(mapping.get("unresolved_cells")) if isinstance(item, dict)
        ),
        classification=str(mapping.get("classification") or ""),
        classification_evidence=str(mapping.get("classification_evidence") or ""),
        metadata=_mapping(mapping.get("metadata")),
        missing_envelope_keys=tuple(k for k in TABLE_ENVELOPE_KEYS if k not in mapping),
        extra={k: v for k, v in mapping.items() if k not in _KNOWN_TABLE_KEYS},
        raw=mapping,
    )


def read_tables(raw_tables: Any) -> tuple[StructuredTable, ...]:
    """Every readable structured table in one part response, in the order the model returned them."""
    found: list[StructuredTable] = []
    for raw in _rows(raw_tables):
        table = read_table(raw)
        if table is not None:
            found.append(table)
    return tuple(found)
