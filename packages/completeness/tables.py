"""Validate a model's STRUCTURED TABLE against the table element it claims to represent.

WHAT IS CHECKED, AND EVERY CHECK IS AGAINST THE PRESERVED BYTES.

    the identifier is unique within the parse
    the source member it names was actually submitted
    the source table element it names actually exists in the mechanical inventory
    its source anchors resolve inside that element's byte range
    its grid is well formed: no two cells at one position, no negative or zero span
    every cell's ORIGINAL TEXT occurs in the source element's slice
    every numeric cell's text occurs in the source element's slice
    a continuation link names a table that exists

WHAT IS DELIBERATELY NOT CHECKED, AND IT IS THE LONGER LIST. Whether the title is right. Whether
the type is a real kind of financial table. Whether a unit is a real unit. Whether a period label
is well formed. Whether the header row is really a header. Whether the normalised `value` matches
the `text`. Every one of those is a judgement about what the table MEANS, and `rules.md` section 21
rules 1 and 2 put all of them outside backend code. A validator that checked `unit` against a list
of units would be the first brick of a universal filing taxonomy.

    THE `value` FIELD IS NEVER VALIDATED AGAINST ANYTHING. A model may offer `1,234` as `1234` or
    as `1234000000` after applying a scale the table declares. Deciding which is right requires
    reading the table's own scale note, which is interpretation. It is carried, displayed, and left
    to a reviewer.

AN UNRESOLVED CELL IS A PASS, NOT A FAILURE. `rules.md` section 21 rule 5: unknown content is
preserved or marked unresolved, never discarded, and uncertainty produces PARTIAL rather than a
false complete. A model that says "this cell is illegible in the source" has done the right thing,
and the gate counts it as exposed rather than as broken.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from packages.source_inventory import FilingInventory, normalize_text

from .intervals import Interval


@dataclass(frozen=True)
class TableValidation:
    """The verdict on one structured table, and every finding behind it."""

    table_id: str
    source_table_id: str
    source_resolved: bool
    cells_total: int
    cells_text_found: int
    cells_text_missing: int
    cells_unresolved: int
    numeric_cells: int
    numeric_cells_found: int
    grid_collisions: int
    findings: tuple[str, ...]

    @property
    def passes(self) -> bool:
        """Whether the table is usable as evidence.

        A table passes when it maps to a real source element, its grid is well formed, and every
        cell whose text is missing from the source was DECLARED unresolved. A missing cell that
        nobody declared is a fabricated cell, and that is the one thing this validator refuses.
        """
        return self.source_resolved and self.grid_collisions == 0 and self.cells_text_missing == 0

    def to_mapping(self) -> dict[str, Any]:
        return {
            "table_id": self.table_id,
            "source_table_id": self.source_table_id,
            "source_resolved": self.source_resolved,
            "passes": self.passes,
            "cells_total": self.cells_total,
            "cells_text_found": self.cells_text_found,
            "cells_text_missing": self.cells_text_missing,
            "cells_unresolved": self.cells_unresolved,
            "numeric_cells": self.numeric_cells,
            "numeric_cells_found": self.numeric_cells_found,
            "grid_collisions": self.grid_collisions,
            "findings": list(self.findings),
        }


def _is_numeric(text: str) -> bool:
    """Whether a cell's text carries a number, by character composition alone.

    NO CURRENCY LIST, NO LOCALE, NO FORMAT VOCABULARY. A cell is numeric when it contains at least
    one digit and nothing outside the set a filed figure uses. That is a character-class test, not
    a claim about what the number means.
    """
    if not any(character.isdigit() for character in text):
        return False
    return all(character in "0123456789.,()-–—%$  +" for character in text)


def validate_table(
    table: Any,
    *,
    inventory: FilingInventory,
    submitted_members: frozenset[str],
    known_table_ids: frozenset[str],
) -> TableValidation:
    """Check one structured table against the source element it names."""
    findings: list[str] = []
    source_id = str(getattr(table, "source_table_id", "") or "")
    member = str(getattr(table, "source_member", "") or "")
    element = inventory.table(source_id) if source_id else None

    if not source_id:
        findings.append(
            "the table names no source_table_id, so it cannot be mapped to a table element in the "
            "preserved bytes and cannot discharge that element's coverage"
        )
    elif element is None:
        findings.append(
            f"source_table_id {source_id!r} names no table element in the mechanical inventory"
        )
    if member and member not in submitted_members:
        findings.append(f"source_member {member!r} was not submitted to the model in this run")
    elif element is not None and member and element.member != member:
        findings.append(
            f"source_member {member!r} disagrees with the inventory, which places "
            f"{source_id} in {element.member!r}"
        )

    slice_text = ""
    if element is not None:
        cell_texts = {normalize_text(cell.text) for cell in element.cells if cell.text.strip()}
        # Joined on a newline, which `normalize_text` has already removed from every cell, so
        # no cell text can straddle the separator and appear to match across two cells.
        #
        # SUBSTRING MATCHING IS THE LENIENT DIRECTION AND IT IS CHOSEN DELIBERATELY. A model
        # that writes `124` where the source cell reads `124,300` is recorded as found. This
        # validator exists to catch a cell the model supplied from somewhere other than this
        # filing, and a false accusation of fabrication is worse than a missed truncation:
        # the cell's own text is displayed beside the source cell in the review UI, where a
        # person sees the difference immediately.
        slice_text = "\n".join(sorted(cell_texts))
        for anchor_name in ("source_anchor_start", "source_anchor_end"):
            anchor = normalize_text(str(getattr(table, anchor_name, "") or ""))
            if anchor and anchor not in slice_text:
                findings.append(
                    f"{anchor_name} does not occur among the cells of {source_id}; it is recorded "
                    "as a finding rather than a refusal, because an anchor may legitimately quote "
                    "a caption outside the table element"
                )

    positions: dict[tuple[int, int], int] = {}
    collisions = 0
    found = missing = unresolved = numeric = numeric_found = 0
    cells = tuple(getattr(table, "cells", ()) or ())
    for cell in cells:
        for row_offset in range(max(1, cell.row_span)):
            for column_offset in range(max(1, cell.column_span)):
                key = (cell.row + row_offset, cell.column + column_offset)
                positions[key] = positions.get(key, 0) + 1
                if positions[key] == 2:
                    collisions += 1
        if getattr(cell, "unresolved", False):
            unresolved += 1
            continue
        text = normalize_text(str(getattr(cell, "text", "") or ""))
        if not text:
            continue
        if _is_numeric(text):
            numeric += 1
        if element is not None and text in slice_text:
            found += 1
            if _is_numeric(text):
                numeric_found += 1
        elif element is not None:
            missing += 1

    if collisions:
        findings.append(
            f"{collisions} grid position(s) are claimed by more than one cell once row and column "
            "spans are applied"
        )
    if missing:
        findings.append(
            f"{missing} cell text(s) do not occur in the source element and were not declared "
            "unresolved. A cell that is neither in the source nor declared unresolved is a cell "
            "the model supplied from somewhere other than this filing"
        )

    continues = str(getattr(table, "continues_table_id", "") or "")
    if continues and continues not in known_table_ids:
        findings.append(f"continues_table_id {continues!r} names no table in this parse")

    return TableValidation(
        table_id=str(getattr(table, "table_id", "") or ""),
        source_table_id=source_id,
        source_resolved=element is not None,
        cells_total=len(cells),
        cells_text_found=found,
        cells_text_missing=missing,
        cells_unresolved=unresolved,
        numeric_cells=numeric,
        numeric_cells_found=numeric_found,
        grid_collisions=collisions,
        findings=tuple(findings),
    )


def validate_tables(
    tables: tuple[Any, ...],
    *,
    inventory: FilingInventory,
    submitted_members: frozenset[str],
) -> tuple[TableValidation, ...]:
    """Validate every structured table of one parse, including identifier uniqueness across them."""
    known = frozenset(str(getattr(t, "table_id", "") or "") for t in tables)
    results = [
        validate_table(
            table,
            inventory=inventory,
            submitted_members=submitted_members,
            known_table_ids=known,
        )
        for table in tables
    ]
    seen: dict[str, int] = {}
    for result in results:
        seen[result.table_id] = seen.get(result.table_id, 0) + 1
    duplicated = {identifier for identifier, count in seen.items() if count > 1}
    if not duplicated:
        return tuple(results)
    return tuple(
        TableValidation(
            table_id=result.table_id,
            source_table_id=result.source_table_id,
            source_resolved=result.source_resolved,
            cells_total=result.cells_total,
            cells_text_found=result.cells_text_found,
            cells_text_missing=result.cells_text_missing,
            cells_unresolved=result.cells_unresolved,
            numeric_cells=result.numeric_cells,
            numeric_cells_found=result.numeric_cells_found,
            # A duplicated identifier is a GRID-level failure of the parse, not of one table: two
            # tables answering to one name cannot both be cited, reviewed or superseded.
            grid_collisions=result.grid_collisions + 1,
            findings=result.findings
            + (f"table_id {result.table_id!r} is used by more than one table in this parse",),
        )
        if result.table_id in duplicated
        else result
        for result in results
    )


def table_source_interval(table_id: str, inventory: FilingInventory) -> Interval | None:
    """The source range of one mechanical table element, for interval accounting."""
    element = inventory.table(table_id)
    return Interval(element.start, element.end) if element is not None else None
