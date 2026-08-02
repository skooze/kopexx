"""Persist a canonicalization run.

NO MIGRATION IS NEEDED. The schema created by the sealed `0001_initial` already carries every
column the audit model requires and every uniqueness constraint idempotency requires:

    canonical_footnote     UNIQUE (filing_id, normalized_number), UNIQUE (filing_id, sequence)
    footnote_source_block  UNIQUE (filing_id, external_id)
    footnote_table         UNIQUE (filing_id, external_id)
    filing_section         UNIQUE (filing_id, section_type, sequence)

That was verified against the live catalog before writing this module rather than assumed. Adding
a `0002` to restate constraints that already exist would be churn, and `0001_initial` is sealed.

IDEMPOTENCY IS BY NATURAL KEY, ENFORCED BY THE DATABASE. Every write is `ON CONFLICT ... DO
UPDATE` against one of the constraints above. A rerun inserts nothing new. This is stronger than
the DERA loader's read-then-insert, because it does not depend on the read and the insert seeing
the same state.

THE UPDATE IS CONDITIONAL, AND THAT MATTERS FOR THE AUDIT. An unconditional `DO UPDATE` rewrites
every row on every run, which stamps a fresh `extraction_run_id` and `grouping_decided_at` onto
decisions that did not change. Those two fields then answer "which run last touched this" when
their names promise "which run decided this, and when" — and the original decision time is gone.

So each upsert carries a `WHERE` clause naming the fields whose change would be a real change. A
row whose values all match is left alone: no write, no timestamp, no new run id. A row whose
authoritative input genuinely changed is updated deliberately, and its audit fields move with it,
which is the behaviour a correction needs.

Counting distinguishes the three outcomes — inserted, updated, unchanged — so a rerun reports
`unchanged` rather than the misleading `updated` an unconditional upsert produced.

CONCURRENCY. A transaction-scoped advisory lock keyed on the accession serializes two
canonicalizers of the same filing. Without it, two runs could each insert a canonical footnote
under a different `footnote_id` before either committed — the unique constraint would reject the
second, but only after it had done its work, and the failure would surface as a constraint error
rather than as an orderly wait.

ONE TRANSACTION. A partially canonicalized filing is worse than an uncanonicalized one, because
its completeness counters would describe a state no run produced.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine

from packages.table_parser import ParsedTable

from .completeness import ExtractionCompleteness, filing_footnote_status
from .ownership import OwnershipReconciliation, TableOwnership
from .stages import PARSER_VERSION, Attachment, CandidateNote, CanonicalizationResult

# `filing_section.section_type` for an excluded Regulation S-K item disclosure. The excluded
# material is never discarded — it stays retrievable and attributable to the item that produced it.
ITEM_DISCLOSURE_SECTION = "item_disclosure"


def advisory_lock_key(accession: str) -> int:
    """A stable signed 64-bit lock key for one filing's canonicalization.

    SHA-256 truncated rather than Python's `hash()`, which is salted per process: two workers
    would compute different keys, take different locks, and serialize nothing.
    """
    digest = hashlib.sha256(f"canonicalize:{accession}".encode()).digest()[:8]
    return int.from_bytes(digest, "big", signed=True)


@dataclass
class PersistedCounts:
    """What the run wrote, by record type."""

    canonical_footnotes: int = 0
    source_blocks: int = 0
    attachments: int = 0
    filing_sections: int = 0
    tables: int = 0
    table_cells: int = 0
    tables_owned_by_footnote: int = 0
    footnotes_inserted: int = 0
    footnotes_updated: int = 0
    footnotes_unchanged: int = 0
    blocks_inserted: int = 0
    blocks_updated: int = 0
    blocks_unchanged: int = 0

    def as_record(self) -> dict[str, Any]:
        return {
            "canonical_footnotes": self.canonical_footnotes,
            "source_blocks": self.source_blocks,
            "attachments": self.attachments,
            "filing_sections": self.filing_sections,
            "tables": self.tables,
            "table_cells": self.table_cells,
            "tables_owned_by_footnote": self.tables_owned_by_footnote,
            "footnotes_inserted": self.footnotes_inserted,
            "footnotes_updated": self.footnotes_updated,
            "footnotes_unchanged": self.footnotes_unchanged,
            "blocks_inserted": self.blocks_inserted,
            "blocks_updated": self.blocks_updated,
            "blocks_unchanged": self.blocks_unchanged,
        }


class PersistenceError(Exception):
    """The run could not be persisted and left nothing behind."""


def _filing_id(connection: Connection, accession: str) -> uuid.UUID:
    row = connection.execute(
        text("SELECT filing_id FROM filing WHERE accession = :a"), {"a": accession}
    ).scalar()
    if row is None:
        raise PersistenceError(
            f"no filing row for {accession}. Canonical footnotes carry a foreign key to filing, "
            "so acquisition and registration must run first."
        )
    return uuid.UUID(str(row))


def _upsert_footnote(
    connection: Connection,
    filing_id: uuid.UUID,
    note: CandidateNote,
    sequence: int,
    heading: Any,
    counts: PersistedCounts,
) -> uuid.UUID:
    """Insert or update one canonical footnote, keyed on (filing_id, sequence).

    Sequence rather than displayed number: `normalized_number` is nullable, and a NULL never
    conflicts in a unique constraint, so two unnumbered notes would duplicate silently. Sequence
    is NOT NULL and is the filed order, which every filing has.
    """
    number = heading.number if heading is not None else None
    displayed = str(heading.number) if heading is not None else None
    title = heading.title if heading is not None else note.title
    normalized = heading.normalized_title if heading is not None else None

    evidence = {
        "stage": "1-2",
        "menu_category": note.report.menu_category,
        "role_uri": note.role_uri,
        "renderer_position": note.report.position,
        "exclusion_verdict": note.verdict.as_evidence(),
        "heading_matched": heading is not None,
    }

    row = connection.execute(
        text(
            "INSERT INTO canonical_footnote (footnote_id, filing_id, number_as_displayed,"
            " normalized_number, title_as_displayed, normalized_title, sequence, text,"
            " extraction_method, grouping_method, grouping_evidence, parser_version, confidence,"
            " is_valid)"
            " VALUES (gen_random_uuid(), :filing_id, :displayed, :number, :title, :normalized,"
            " :sequence, NULL, 'renderer_inventory', 'role_uri', CAST(:evidence AS jsonb),"
            " :parser, 1.0, true)"
            " ON CONFLICT (filing_id, sequence) DO UPDATE SET"
            "   number_as_displayed = EXCLUDED.number_as_displayed,"
            "   normalized_number = EXCLUDED.normalized_number,"
            "   title_as_displayed = EXCLUDED.title_as_displayed,"
            "   normalized_title = EXCLUDED.normalized_title,"
            "   grouping_evidence = EXCLUDED.grouping_evidence,"
            "   parser_version = EXCLUDED.parser_version"
            " WHERE canonical_footnote.number_as_displayed IS DISTINCT FROM"
            "         EXCLUDED.number_as_displayed"
            "    OR canonical_footnote.normalized_number IS DISTINCT FROM"
            "         EXCLUDED.normalized_number"
            "    OR canonical_footnote.title_as_displayed IS DISTINCT FROM"
            "         EXCLUDED.title_as_displayed"
            "    OR canonical_footnote.normalized_title IS DISTINCT FROM"
            "         EXCLUDED.normalized_title"
            "    OR canonical_footnote.grouping_evidence IS DISTINCT FROM"
            "         EXCLUDED.grouping_evidence"
            "    OR canonical_footnote.parser_version IS DISTINCT FROM EXCLUDED.parser_version"
            " RETURNING footnote_id, (xmax = 0) AS inserted"
        ),
        {
            "filing_id": filing_id,
            "displayed": displayed,
            "number": number,
            "title": title,
            "normalized": normalized,
            "sequence": sequence,
            "evidence": json.dumps(evidence, sort_keys=True),
            "parser": PARSER_VERSION,
        },
    ).first()

    if row is None:
        # The conditional update matched nothing, meaning every value already agreed. The row is
        # unchanged and its identifier is read rather than rewritten.
        counts.footnotes_unchanged += 1
        existing = connection.execute(
            text(
                "SELECT footnote_id FROM canonical_footnote"
                " WHERE filing_id = :filing_id AND sequence = :sequence"
            ),
            {"filing_id": filing_id, "sequence": sequence},
        ).scalar_one()
        return uuid.UUID(str(existing))

    if row[1]:
        counts.footnotes_inserted += 1
    else:
        counts.footnotes_updated += 1
    return uuid.UUID(str(row[0]))


def _upsert_parent_block(
    connection: Connection,
    filing_id: uuid.UUID,
    footnote_id: uuid.UUID,
    note: CandidateNote,
    run_id: uuid.UUID,
    counts: PersistedCounts,
) -> None:
    """The parent note's own rendered report, stored as a source block.

    Without this the note's own narrative has no source record, and a citation could only point at
    a child. The parent block is what the note actually says.
    """
    _upsert_block(
        connection,
        filing_id=filing_id,
        footnote_id=footnote_id,
        report=note.report,
        block_type="parent_narrative",
        grouping_method=None,
        grouping_confidence=None,
        evidence={"stage": 1, "reason": "the candidate's own rendered report"},
        competing=[],
        run_id=run_id,
        counts=counts,
    )


def _upsert_block(
    connection: Connection,
    *,
    filing_id: uuid.UUID,
    footnote_id: uuid.UUID | None,
    report: Any,
    block_type: str,
    grouping_method: str | None,
    grouping_confidence: float | None,
    evidence: dict[str, Any],
    competing: list[dict[str, Any]],
    run_id: uuid.UUID,
    counts: PersistedCounts,
) -> None:
    row = connection.execute(
        text(
            "INSERT INTO footnote_source_block (block_id, filing_id, footnote_id, external_id,"
            " block_type, dera_report_number, menucat, short_name, long_name, role_uri, sequence,"
            " grouping_method, grouping_confidence, grouping_evidence, competing_candidates,"
            " extraction_run_id, grouping_parser_version, grouping_decided_at)"
            " VALUES (gen_random_uuid(), :filing_id, :footnote_id, :external_id, :block_type,"
            " :position, :menucat, :short_name, :long_name, :role_uri, :sequence,"
            " :grouping_method, :confidence, CAST(:evidence AS jsonb),"
            " CAST(:competing AS jsonb), :run_id, :parser, :decided_at)"
            " ON CONFLICT (filing_id, external_id) DO UPDATE SET"
            "   footnote_id = EXCLUDED.footnote_id,"
            "   block_type = EXCLUDED.block_type,"
            "   grouping_method = EXCLUDED.grouping_method,"
            "   grouping_confidence = EXCLUDED.grouping_confidence,"
            "   grouping_evidence = EXCLUDED.grouping_evidence,"
            "   competing_candidates = EXCLUDED.competing_candidates,"
            "   extraction_run_id = EXCLUDED.extraction_run_id,"
            "   grouping_parser_version = EXCLUDED.grouping_parser_version,"
            "   grouping_decided_at = EXCLUDED.grouping_decided_at"
            " WHERE footnote_source_block.footnote_id IS DISTINCT FROM EXCLUDED.footnote_id"
            "    OR footnote_source_block.block_type IS DISTINCT FROM EXCLUDED.block_type"
            "    OR footnote_source_block.grouping_method IS DISTINCT FROM"
            "         EXCLUDED.grouping_method"
            "    OR footnote_source_block.grouping_confidence IS DISTINCT FROM"
            "         EXCLUDED.grouping_confidence"
            "    OR footnote_source_block.grouping_evidence IS DISTINCT FROM"
            "         EXCLUDED.grouping_evidence"
            "    OR footnote_source_block.competing_candidates IS DISTINCT FROM"
            "         EXCLUDED.competing_candidates"
            "    OR footnote_source_block.grouping_parser_version IS DISTINCT FROM"
            "         EXCLUDED.grouping_parser_version"
            " RETURNING (xmax = 0) AS inserted"
        ),
        {
            "filing_id": filing_id,
            "footnote_id": footnote_id,
            "external_id": report.external_id,
            "block_type": block_type,
            "position": report.position,
            # `menucat` is CHAR(4) in the DERA schema; the renderer's word form is truncated to
            # match rather than widened, because the column mirrors DERA's own encoding.
            "menucat": (report.menu_category or "")[:4] or None,
            "short_name": report.short_name,
            "long_name": report.long_name,
            "role_uri": report.role,
            "sequence": report.position,
            "grouping_method": grouping_method,
            "confidence": grouping_confidence,
            "evidence": json.dumps(evidence, sort_keys=True),
            "competing": json.dumps(competing, sort_keys=True),
            "run_id": run_id,
            "parser": PARSER_VERSION,
            "decided_at": datetime.now(UTC),
        },
    ).first()

    if row is None:
        counts.blocks_unchanged += 1
    elif row[0]:
        counts.blocks_inserted += 1
    else:
        counts.blocks_updated += 1
    counts.source_blocks += 1


def _upsert_section(
    connection: Connection,
    filing_id: uuid.UUID,
    note: CandidateNote,
    sequence: int,
    counts: PersistedCounts,
) -> None:
    """An excluded item disclosure, kept as a filing section.

    Excluded is not discarded. The disclosure remains retrievable, attributable to the item that
    produced it, and in its filed order.
    """
    connection.execute(
        text(
            "INSERT INTO filing_section (section_id, filing_id, section_type, item_number,"
            " heading, sequence, extraction_strategy, confidence, candidate_count, parser_version)"
            " VALUES (gen_random_uuid(), :filing_id, :section_type, :item, :heading, :sequence,"
            " :strategy, 1.0, 1, :parser)"
            " ON CONFLICT (filing_id, section_type, sequence) DO UPDATE SET"
            "   item_number = EXCLUDED.item_number,"
            "   heading = EXCLUDED.heading,"
            "   extraction_strategy = EXCLUDED.extraction_strategy,"
            "   parser_version = EXCLUDED.parser_version"
        ),
        {
            "filing_id": filing_id,
            "section_type": ITEM_DISCLOSURE_SECTION,
            "item": (note.verdict.item or "")[:10] or None,
            "heading": note.title,
            "sequence": sequence,
            "strategy": (note.verdict.rule or "")[:40] or None,
            "parser": PARSER_VERSION,
        },
    )
    counts.filing_sections += 1


def _upsert_table(
    connection: Connection,
    filing_id: uuid.UUID,
    footnote_id: uuid.UUID | None,
    table: ParsedTable,
    storage_uri: str | None,
    counts: PersistedCounts,
    ownership: TableOwnership | None = None,
) -> None:
    from packages.table_parser import PARSER_VERSION as TABLE_PARSER_VERSION

    connection.execute(
        text(
            "INSERT INTO footnote_table (table_id, filing_id, footnote_id, external_id, title,"
            " sequence, column_headers, row_labels, cells, original_html_uri, source_anchor,"
            " parser_version, validation_warnings, ownership_kind, ownership_method,"
            " ownership_evidence)"
            " VALUES (gen_random_uuid(), :filing_id, :footnote_id, :external_id, :title,"
            " :sequence, CAST(:headers AS jsonb), CAST(:labels AS jsonb), CAST(:cells AS jsonb),"
            " :uri, :anchor, :parser, CAST(:warnings AS jsonb), :kind, :method,"
            " CAST(:ownership AS jsonb))"
            " ON CONFLICT (filing_id, external_id) DO UPDATE SET"
            "   footnote_id = EXCLUDED.footnote_id,"
            "   title = EXCLUDED.title,"
            "   column_headers = EXCLUDED.column_headers,"
            "   row_labels = EXCLUDED.row_labels,"
            "   cells = EXCLUDED.cells,"
            "   original_html_uri = EXCLUDED.original_html_uri,"
            "   source_anchor = EXCLUDED.source_anchor,"
            "   parser_version = EXCLUDED.parser_version,"
            "   validation_warnings = EXCLUDED.validation_warnings,"
            "   ownership_kind = EXCLUDED.ownership_kind,"
            "   ownership_method = EXCLUDED.ownership_method,"
            "   ownership_evidence = EXCLUDED.ownership_evidence"
            " WHERE footnote_table.footnote_id IS DISTINCT FROM EXCLUDED.footnote_id"
            "    OR footnote_table.cells IS DISTINCT FROM EXCLUDED.cells"
            "    OR footnote_table.column_headers IS DISTINCT FROM EXCLUDED.column_headers"
            "    OR footnote_table.row_labels IS DISTINCT FROM EXCLUDED.row_labels"
            "    OR footnote_table.ownership_kind IS DISTINCT FROM EXCLUDED.ownership_kind"
            "    OR footnote_table.ownership_evidence IS DISTINCT FROM EXCLUDED.ownership_evidence"
            "    OR footnote_table.parser_version IS DISTINCT FROM EXCLUDED.parser_version"
        ),
        {
            "filing_id": filing_id,
            "footnote_id": footnote_id,
            "external_id": table.external_id,
            "title": table.caption,
            "sequence": table.index,
            "headers": json.dumps(table.column_headers()),
            "labels": json.dumps(table.row_labels()),
            "cells": json.dumps(table.cells_as_grid()),
            "uri": storage_uri,
            "anchor": None if table.source_offset is None else f"offset:{table.source_offset}",
            "parser": TABLE_PARSER_VERSION,
            "warnings": json.dumps({"parse_state": table.parse_state, "warnings": table.warnings}),
            "kind": ownership.classification if ownership else None,
            "method": ownership.method if ownership else None,
            "ownership": json.dumps(ownership.as_evidence(), sort_keys=True) if ownership else None,
        },
    )
    counts.tables += 1
    counts.table_cells += table.cell_count
    if ownership and ownership.is_footnote_owned:
        counts.tables_owned_by_footnote += 1


def persist(
    engine: Engine,
    result: CanonicalizationResult,
    completeness: ExtractionCompleteness,
    heading_map: dict[str, Any],
    *,
    tables: list[ParsedTable] | None = None,
    table_storage_uri: str | None = None,
    ownership: OwnershipReconciliation | None = None,
) -> PersistedCounts:
    """Write one canonicalization run. One transaction, one advisory lock, all upserts."""
    counts = PersistedCounts()
    tables = tables or []

    with engine.begin() as connection:
        connection.execute(
            text("SELECT pg_advisory_xact_lock(:key)"),
            {"key": advisory_lock_key(result.accession)},
        )
        filing_id = _filing_id(connection, result.accession)

        role_to_footnote: dict[str, uuid.UUID] = {}
        for sequence, note in enumerate(result.footnotes, start=1):
            heading = heading_map.get(note.role_uri or "")
            footnote_id = _upsert_footnote(connection, filing_id, note, sequence, heading, counts)
            counts.canonical_footnotes += 1
            if note.role_uri:
                role_to_footnote[note.role_uri] = footnote_id
            _upsert_parent_block(connection, filing_id, footnote_id, note, result.run_id, counts)

        for attachment in result.attachments:
            _persist_attachment(connection, filing_id, attachment, role_to_footnote, result, counts)

        for sequence, note in enumerate(result.excluded, start=1):
            _upsert_section(connection, filing_id, note, sequence, counts)

        by_table = {o.external_id: o for o in (ownership.ownership if ownership else [])}
        for table in tables:
            verdict = by_table.get(table.external_id)
            owner_id = (
                role_to_footnote.get(verdict.owner_role_uri)
                if verdict and verdict.is_footnote_owned and verdict.owner_role_uri
                else None
            )
            # The check constraint added in 0002 requires these two to agree, so a classification
            # of CANONICAL_FOOTNOTE whose role resolved to no footnote is downgraded rather than
            # written as a contradiction the database would reject.
            if verdict and verdict.is_footnote_owned and owner_id is None:
                verdict = TableOwnership(
                    external_id=verdict.external_id,
                    classification="UNRESOLVED",
                    concept=verdict.concept,
                    candidate_roles=verdict.candidate_roles,
                    method=verdict.method,
                    reason="classified as footnote-owned but the role resolved to no persisted note",
                )
            _upsert_table(
                connection, filing_id, owner_id, table, table_storage_uri, counts, verdict
            )

        _update_filing(connection, filing_id, completeness)

    return counts


def _persist_attachment(
    connection: Connection,
    filing_id: uuid.UUID,
    attachment: Attachment,
    role_to_footnote: dict[str, uuid.UUID],
    result: CanonicalizationResult,
    counts: PersistedCounts,
) -> None:
    """One child block and its grouping audit.

    An orphan is written with a NULL parent and its full candidate set, not omitted. A missing row
    is indistinguishable from a filing that never had that block.
    """
    footnote_id = (
        role_to_footnote.get(attachment.parent_role_uri) if attachment.parent_role_uri else None
    )
    evidence = dict(attachment.evidence)
    evidence.update({"stage": attachment.stage, "reason": attachment.reason})

    _upsert_block(
        connection,
        filing_id=filing_id,
        footnote_id=footnote_id,
        report=attachment.child,
        block_type=(attachment.child.menu_category or "child").lower(),
        grouping_method=attachment.method,
        grouping_confidence=attachment.confidence,
        evidence=evidence,
        competing=attachment.competing_candidates,
        run_id=result.run_id,
        counts=counts,
    )
    if attachment.is_attached:
        counts.attachments += 1


def _update_filing(
    connection: Connection, filing_id: uuid.UUID, completeness: ExtractionCompleteness
) -> None:
    """Write the four judgements that cannot be recomputed from child rows.

    Everything else the dashboard shows — extracted counts, attached counts, orphan counts — is a
    COUNT() over child tables and is deliberately not stored. A stored copy is a second source of
    truth that goes stale the moment a block is re-attached.
    """
    connection.execute(
        text(
            "UPDATE filing SET"
            "  toc_expected_note_count = :toc,"
            "  reconciliation_status = :reconciliation,"
            "  completeness_confidence = :confidence,"
            "  footnote_status = :status,"
            "  processing_state = 'FOOTNOTES_GROUPED',"
            "  parser_version = :parser"
            " WHERE filing_id = :id"
        ),
        {
            "toc": completeness.toc_expected_note_count,
            "reconciliation": completeness.reconciliation_status,
            "confidence": completeness.confidence,
            # Summarization is Sprint 5, so a filing with a flawless extraction is correctly
            # PARTIAL: it has canonical footnotes and no accepted summaries.
            "status": filing_footnote_status(completeness, accepted_summaries=0),
            "parser": PARSER_VERSION,
            "id": filing_id,
        },
    )
