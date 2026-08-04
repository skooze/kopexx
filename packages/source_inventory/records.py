"""The records the mechanical source inventory produces.

WHAT THESE RECORDS ARE ALLOWED TO SAY. Where something is in the preserved bytes, how big it is,
what shape its markup has, whether the same bytes occur elsewhere, and whether the source's own
markup hides it. Every one of those is a TRANSPORT fact — offset, length, hash, element name,
row count, span count, image dimensions — and rules.md invariant 14 permits exactly those.

WHAT THEY ARE FORBIDDEN TO SAY. Whether a span is a risk factor, a footnote, MD&A, a signature
block or boilerplate. Whether a table is a financial statement, a layout device or navigation.
Whether an image is a chart or a logo. Those are semantic judgements, and in this repository they
belong to the selected parsing model or to a human reviewer — never to backend code.

    THE DISTINCTION IS NOT ACADEMIC. `packages/filing_acquisition/inventory.py` was deleted for
    crossing it: it classified filed documents into a Regulation S-K role taxonomy and, on that
    judgement, ruled that a courtesy PDF duplicated the primary document and suppressed a filed
    source range. ADR-0017. This package inventories; it does not adjudicate.

WHY AN INVENTORY EXISTS AT ALL, GIVEN THAT. It is the DENOMINATOR. Phase 2.1 could report that 352
of 364 model-emitted references resolved and could not report what fraction of the filing that was,
because a region the model never cited never entered the count. A mechanical inventory of every
visible span, every table element and every image is a denominator that does not depend on what any
model chose to mention.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class HiddenReason(StrEnum):
    """Why the source's own markup renders a span invisible. A transport fact, not a judgement."""

    #: Not hidden.
    VISIBLE = "VISIBLE"
    #: Inside <script> or <style>: the browser never renders it as prose.
    NON_RENDERED_ELEMENT = "NON_RENDERED_ELEMENT"
    #: Inside <head>.
    DOCUMENT_HEAD = "DOCUMENT_HEAD"
    #: Inside an inline-XBRL <ix:hidden> block, which exists precisely to carry facts that are
    #: tagged but not displayed.
    IX_HIDDEN = "IX_HIDDEN"
    #: An ancestor carries an inline style that suppresses display.
    STYLE_SUPPRESSED = "STYLE_SUPPRESSED"


#: Hidden reasons whose spans are NOT part of the human-readable rendering of the document.
#: They stay in the inventory with their reason recorded; they are simply not counted as visible.
#:
#: THERE IS NO `COMMENT` MEMBER, DELIBERATELY. An HTML comment is markup, not character data, and
#: never becomes a span in the first place. An enum value that exists is an enum value something
#: eventually sets, which is how a state nobody can reach starts appearing in reports.
NOT_VISIBLE: frozenset[HiddenReason] = frozenset(
    {
        HiddenReason.NON_RENDERED_ELEMENT,
        HiddenReason.DOCUMENT_HEAD,
        HiddenReason.IX_HIDDEN,
        HiddenReason.STYLE_SUPPRESSED,
    }
)


@dataclass(frozen=True)
class TextSpan:
    """One maximal run of character data between two BLOCK-level markup boundaries.

    THE BOUNDARY RULE IS HTML'S, NOT THIS PROJECT'S. A span ends where a block-level element begins
    or ends, and inline elements do not break one. That matters for inline XBRL, where a single
    rendered sentence is shredded across `span` and `ix:nonFraction` elements: treating every
    element as a boundary would turn one sentence into forty fragments and make the denominator
    meaningless.

    `start` and `end` are character offsets into the DECODED text of the member, which is the same
    coordinate system `packages/coverage_validation` reports a resolved reference in. One coordinate
    system, or a review UI highlights a plausible and wrong range.
    """

    span_id: str
    member: str
    start: int
    end: int
    original_text: str
    normalized_text: str
    hidden_reason: HiddenReason
    element_path: str
    parent_element: str
    table_id: str
    duplicate_of: str

    @property
    def visible(self) -> bool:
        return self.hidden_reason not in NOT_VISIBLE

    @property
    def character_count(self) -> int:
        return self.end - self.start

    @property
    def mechanically_duplicate(self) -> bool:
        return bool(self.duplicate_of)

    def to_mapping(self) -> dict[str, Any]:
        return {
            "span_id": self.span_id,
            "member": self.member,
            "start": self.start,
            "end": self.end,
            "character_count": self.character_count,
            # Truncated for the manifest only. The preserved member is authoritative and the
            # offsets above locate the full text in it.
            "normalized_text": self.normalized_text[:400],
            "visible": self.visible,
            "hidden_reason": self.hidden_reason.value,
            "element_path": self.element_path,
            "parent_element": self.parent_element,
            "table_id": self.table_id,
            "duplicate_of": self.duplicate_of,
            "offset_coordinate_system": "characters into the decoded preserved member",
        }


@dataclass(frozen=True)
class TableCell:
    """One `td` or `th`, with the grid position its spans place it at.

    `row_index` and `column_index` are the position after row and column spans from earlier cells
    have been applied, so a reviewer comparing a model's table to this one is comparing the same
    grid. `is_header` records that the element was `th`; it does not assert that the cell means a
    header, and a filing that uses `td` for its headers is reported as it was filed.
    """

    row_index: int
    column_index: int
    row_span: int
    column_span: int
    is_header: bool
    text: str
    start: int
    end: int

    def to_mapping(self) -> dict[str, Any]:
        return {
            "row_index": self.row_index,
            "column_index": self.column_index,
            "row_span": self.row_span,
            "column_span": self.column_span,
            "is_header_element": self.is_header,
            "text": self.text[:200],
            "start": self.start,
            "end": self.end,
        }


@dataclass(frozen=True)
class TableElement:
    """One `table` element of one member, inventoried mechanically.

    NOTHING HERE DECIDES WHAT THE TABLE IS FOR. Financial statement, layout scaffold, navigation
    strip, page-header rule, duplicate rendering — this record cannot tell them apart and must not
    try. It says: here is a table element, here are its bytes, here is its grid. The model
    classifies it with source evidence; a human reviewer may overrule that. Both judgements live
    elsewhere.

    `sha256` is over the exact source slice, so two renderings of the same table in two members are
    recognisable as byte-identical without anyone deciding they mean the same thing.
    """

    table_id: str
    member: str
    start: int
    end: int
    element_path: str
    parent_table_id: str
    nesting_depth: int
    row_count: int
    max_columns: int
    cell_count: int
    sha256: str
    cells: tuple[TableCell, ...]
    duplicate_of: str = ""

    @property
    def byte_length(self) -> int:
        return self.end - self.start

    @property
    def is_empty(self) -> bool:
        """No cell carries any non-whitespace text. A transport observation, not a verdict."""
        return not any(cell.text.strip() for cell in self.cells)

    def to_mapping(self) -> dict[str, Any]:
        return {
            "table_id": self.table_id,
            "member": self.member,
            "start": self.start,
            "end": self.end,
            "character_length": self.byte_length,
            "element_path": self.element_path,
            "parent_table_id": self.parent_table_id,
            "nesting_depth": self.nesting_depth,
            "row_count": self.row_count,
            "max_columns": self.max_columns,
            "cell_count": self.cell_count,
            "sha256": self.sha256,
            "empty_of_text": self.is_empty,
            "duplicate_of": self.duplicate_of,
            "cells": [c.to_mapping() for c in self.cells],
        }


@dataclass(frozen=True)
class ImageRecord:
    """One filed image, with what its own header bytes say about it.

    `width` and `height` are None when the format's header could not supply them. That is an honest
    "not mechanically obtainable" and is never filled with a plausible default: a fabricated
    dimension would be indistinguishable from a measured one in every report that consumes this.
    """

    filename: str
    member: str
    media_type: str
    byte_count: int
    sha256: str
    width: int | None
    height: int | None
    referenced_at: tuple[tuple[str, int], ...] = ()

    def to_mapping(self) -> dict[str, Any]:
        return {
            "filename": self.filename,
            "member": self.member,
            "media_type": self.media_type,
            "byte_count": self.byte_count,
            "sha256": self.sha256,
            "width": self.width,
            "height": self.height,
            "dimensions_available": self.width is not None and self.height is not None,
            "referenced_at": [
                {"member": member, "offset": offset} for member, offset in self.referenced_at
            ],
        }


@dataclass(frozen=True)
class MemberRecord:
    """One package member, as transport describes it and as this inventory measured it.

    `transport_role` carries the disposition `packages/source_transport` assigned from byte
    evidence. `declared_type` is what the FILER wrote in EDGAR's envelope. They are kept apart
    deliberately: one is a measurement, the other is a claim, and collapsing them is how a declared
    label starts being treated as a verified fact.
    """

    filename: str
    member: str
    declared_type: str
    description: str
    media_type: str
    byte_count: int
    sha256: str
    transport_role: str
    human_readable: bool
    image: bool
    character_count: int
    duplicate_of: str
    span_count: int
    table_count: int

    def to_mapping(self) -> dict[str, Any]:
        return {
            "filename": self.filename,
            "member": self.member,
            "sec_declared_type": self.declared_type,
            "sec_declared_description": self.description,
            "media_type": self.media_type,
            "byte_count": self.byte_count,
            "sha256": self.sha256,
            "transport_role": self.transport_role,
            "human_readable": self.human_readable,
            "image": self.image,
            "character_count": self.character_count,
            "duplicate_of": self.duplicate_of,
            "span_count": self.span_count,
            "table_count": self.table_count,
        }


@dataclass(frozen=True)
class FilingInventory:
    """Every mechanically observable unit of one filing's preserved bytes.

    THIS IS FOR VALIDATION AND IT IS NOT AN INPUT FILTER. The selected parsing model still receives
    the complete compatible source set intact, in filed order, hash-verified, on every invocation.
    Nothing here narrows, projects or slices what is sent — rules.md section 21 rules 6 and 7.
    """

    cik: str
    accession: str
    form_as_filed: str
    filing_date: str
    report_period: str | None
    source_set_sha256: str
    members: tuple[MemberRecord, ...]
    spans: tuple[TextSpan, ...]
    tables: tuple[TableElement, ...]
    images: tuple[ImageRecord, ...]
    findings: tuple[str, ...] = field(default_factory=tuple)

    @property
    def human_readable_members(self) -> tuple[MemberRecord, ...]:
        return tuple(m for m in self.members if m.human_readable)

    @property
    def visible_spans(self) -> tuple[TextSpan, ...]:
        return tuple(s for s in self.spans if s.visible)

    @property
    def visible_character_count(self) -> int:
        return sum(s.character_count for s in self.visible_spans)

    def spans_for(self, member: str) -> tuple[TextSpan, ...]:
        return tuple(s for s in self.spans if s.member == member)

    def tables_for(self, member: str) -> tuple[TableElement, ...]:
        return tuple(t for t in self.tables if t.member == member)

    def table(self, table_id: str) -> TableElement | None:
        for candidate in self.tables:
            if candidate.table_id == table_id:
                return candidate
        return None

    def span(self, span_id: str) -> TextSpan | None:
        for candidate in self.spans:
            if candidate.span_id == span_id:
                return candidate
        return None

    def to_mapping(self) -> dict[str, Any]:
        return {
            "schema_version": "source-inventory-v1",
            "cik": self.cik,
            "accession": self.accession,
            "form_as_filed": self.form_as_filed,
            "filing_date": self.filing_date,
            "report_period": self.report_period,
            "source_set_sha256": self.source_set_sha256,
            "member_count": len(self.members),
            "human_readable_member_count": len(self.human_readable_members),
            "span_count": len(self.spans),
            "visible_span_count": len(self.visible_spans),
            "visible_character_count": self.visible_character_count,
            "table_count": len(self.tables),
            "image_count": len(self.images),
            "members": [m.to_mapping() for m in self.members],
            "spans": [s.to_mapping() for s in self.spans],
            "tables": [t.to_mapping() for t in self.tables],
            "images": [i.to_mapping() for i in self.images],
            "findings": list(self.findings),
            "semantic_note": (
                "Every value here is a transport measurement: offsets, lengths, hashes, element "
                "names, grid positions and image header fields. Nothing in this document says what "
                "any span, table or image MEANS. That judgement belongs to the selected parsing "
                "model and to a human reviewer."
            ),
        }
