"""Canonicalization persisted to a live PostgreSQL: idempotency, audit, orphans, rollback.

Builds a synthetic filing rather than depending on the preserved Apple objects, so the suite runs
on a fresh clone with no `var/`. The shapes are the ones the real filings produce.

Runs against the DISPOSABLE integration database, never the application one. It still removes
exactly what it created, because a suite that relies on its target being thrown away cannot prove
idempotency — the whole point of the assertions below is that a second run changes nothing.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

from packages.footnote_canonicalizer import ExclusionList, canonicalize, evaluate
from packages.footnote_canonicalizer.persistence import (
    PersistenceError,
    advisory_lock_key,
    persist,
)
from packages.footnote_extractor import NoteHeading, RendererReport, ReportInventory
from packages.table_parser import parse_tables

pytestmark = pytest.mark.integration

CIK = "0000999997"
ACCESSION = "9999999997-25-000001"

TABLE_HTML = (
    "<table><tr><th>Year</th><th>Value</th></tr><tr><td>2025</td><td>(1,234)</td></tr></table>"
)


def report(position: int, category: str, name: str, role: str | None) -> RendererReport:
    return RendererReport(
        position=position,
        menu_category=category,
        short_name=name,
        long_name=name,
        role=role,
        html_file_name=f"R{position}.htm",
        xml_file_name=None,
        report_type="Sheet",
    )


def build_result(*, orphan: bool = False):
    """Two notes, one excluded disclosure, three children — and optionally one orphan."""
    reports = [
        report(1, "Cover", "Cover", "http://x/role/Cover"),
        report(2, "Notes", "Debt", "http://x/role/Debt"),
        report(3, "Notes", "Leases", "http://x/role/Leases"),
        report(4, "Notes", "Insider Trading Arrangements", "http://xbrl.sec.gov/ecd/role/ITA"),
        report(5, "Details", "Debt Details", "http://x/role/DebtDetails"),
        report(6, "Tables", "Debt Tables", "http://x/role/DebtTables"),
        report(
            7,
            "Details",
            "Leases Details" if not orphan else "Unattachable",
            "http://x/role/LeasesDetails" if not orphan else "http://x/role/NoParentAnywhere",
        ),
    ]
    inventory = ReportInventory(
        reports=tuple(reports), source_sha256="0" * 64, source_path="synthetic"
    )
    headings = (
        NoteHeading(1, "Debt", 0, False),
        NoteHeading(2, "Leases", 1, False),
    )
    result = canonicalize(
        accession=ACCESSION,
        inventory=inventory,
        headings=headings,
        exclusions=ExclusionList.load(),
    )
    return result, headings


@pytest.fixture
def filing(integration_engine):
    """An issuer and filing for the canonical footnotes to attach to, removed afterwards."""
    engine = integration_engine
    with engine.begin() as connection:
        issuer_id = connection.execute(
            text(
                "INSERT INTO issuer (issuer_id, cik, legal_name, is_active)"
                " VALUES (gen_random_uuid(), :cik, 'Canonicalization Fixture', true)"
                " RETURNING issuer_id"
            ),
            {"cik": CIK},
        ).scalar_one()
        connection.execute(
            text(
                "INSERT INTO filing (filing_id, issuer_id, cik, accession, form, filing_date,"
                " is_amendment, is_xbrl, is_inline_xbrl, processing_state, footnote_status,"
                " reconciliation_status)"
                " VALUES (gen_random_uuid(), :i, :cik, :a, '10-K', '2025-10-31', false, true,"
                " true, 'DISCOVERED', 'NOT_STARTED', 'NOT_ATTEMPTED')"
            ),
            {"i": issuer_id, "cik": CIK, "a": ACCESSION},
        )
    try:
        yield engine
    finally:
        with engine.begin() as connection:
            for statement in (
                "DELETE FROM footnote_table WHERE filing_id IN"
                " (SELECT filing_id FROM filing WHERE accession = :a)",
                "DELETE FROM footnote_source_block WHERE filing_id IN"
                " (SELECT filing_id FROM filing WHERE accession = :a)",
                "DELETE FROM canonical_footnote WHERE filing_id IN"
                " (SELECT filing_id FROM filing WHERE accession = :a)",
                "DELETE FROM filing_section WHERE filing_id IN"
                " (SELECT filing_id FROM filing WHERE accession = :a)",
                "DELETE FROM filing WHERE accession = :a",
            ):
                connection.execute(text(statement), {"a": ACCESSION})
            connection.execute(text("DELETE FROM issuer WHERE cik = :c"), {"c": CIK})


def run(engine, *, orphan: bool = False):
    result, headings = build_result(orphan=orphan)
    completeness = evaluate(result)
    heading_map = {
        note.role_uri: heading
        for note, heading in zip(result.footnotes, headings, strict=False)
        if note.role_uri
    }
    counts = persist(
        engine,
        result,
        completeness,
        heading_map,
        tables=parse_tables(TABLE_HTML),
        table_storage_uri="filings/x/y.htm",
    )
    return result, completeness, counts


def counts_for(engine, table: str) -> int:
    with engine.connect() as connection:
        return connection.execute(
            text(
                f"SELECT count(*) FROM {table} WHERE filing_id IN"  # noqa: S608 - fixed identifiers
                " (SELECT filing_id FROM filing WHERE accession = :a)"
            ),
            {"a": ACCESSION},
        ).scalar_one()


# --- the first run ----------------------------------------------------------------------------


def test_a_run_persists_footnotes_blocks_sections_and_tables(filing) -> None:
    _, _, counts = run(filing)
    assert counts.canonical_footnotes == 2
    assert counts.footnotes_inserted == 2
    assert counts.attachments == 3
    assert counts.filing_sections == 1
    assert counts.tables == 1
    assert counts_for(filing, "canonical_footnote") == 2
    # Two parent narrative blocks plus three children.
    assert counts_for(filing, "footnote_source_block") == 5


def test_the_excluded_disclosure_becomes_a_filing_section_not_a_footnote(filing) -> None:
    """Excluded is not discarded. The disclosure stays retrievable and attributable."""
    run(filing)
    with filing.connect() as connection:
        row = connection.execute(
            text(
                "SELECT section_type, item_number, heading FROM filing_section WHERE filing_id IN"
                " (SELECT filing_id FROM filing WHERE accession = :a)"
            ),
            {"a": ACCESSION},
        ).one()
    assert row[0] == "item_disclosure"
    assert row[1] == "Item 408"
    assert "Insider Trading" in row[2]


def test_every_attachment_persists_its_audit_record(filing) -> None:
    """Storing only the parent foreign key cannot answer why the block was attached there."""
    run(filing)
    with filing.connect() as connection:
        rows = connection.execute(
            text(
                "SELECT grouping_method, grouping_confidence, grouping_evidence,"
                " competing_candidates, extraction_run_id, grouping_parser_version,"
                " grouping_decided_at FROM footnote_source_block"
                " WHERE footnote_id IS NOT NULL AND block_type <> 'parent_narrative'"
                " AND filing_id IN (SELECT filing_id FROM filing WHERE accession = :a)"
            ),
            {"a": ACCESSION},
        ).all()

    assert len(rows) == 3
    for method, confidence, evidence, competing, run_id, parser, decided in rows:
        assert method == "role_uri"
        assert float(confidence) == 1.0
        assert evidence["matched_parent_role_uri"]
        assert evidence["stage"] == 3
        assert evidence["reason"]
        # Unambiguous, so empty — but the field is represented rather than absent.
        assert competing == []
        assert run_id and parser and decided


def test_the_filing_records_the_judgements_that_cannot_be_derived(filing) -> None:
    run(filing)
    with filing.connect() as connection:
        row = connection.execute(
            text(
                "SELECT reconciliation_status, completeness_confidence, footnote_status,"
                " processing_state FROM filing WHERE accession = :a"
            ),
            {"a": ACCESSION},
        ).one()
    assert row[0] == "NOT_ATTEMPTED"
    assert row[1] is not None
    # Extraction is clean, but no summaries exist, so the filing is correctly PARTIAL.
    assert row[2] == "PARTIAL"
    assert row[3] == "FOOTNOTES_GROUPED"


# --- idempotency and concurrency -----------------------------------------------------------------


def test_a_rerun_creates_no_duplicates(filing) -> None:
    """IDEMPOTENCY. Every write is ON CONFLICT DO UPDATE against a real constraint."""
    run(filing)
    before = {
        table: counts_for(filing, table)
        for table in (
            "canonical_footnote",
            "footnote_source_block",
            "footnote_table",
            "filing_section",
        )
    }

    _, _, second = run(filing)

    after = {table: counts_for(filing, table) for table in before}
    assert after == before
    assert second.footnotes_inserted == 0
    assert second.blocks_inserted == 0
    # `unchanged`, not `updated`: the upsert is conditional on a value actually differing, so an
    # identical rerun performs no write at all. See test_an_identical_rerun_writes_nothing_at_all.
    assert second.footnotes_updated == 0
    assert second.footnotes_unchanged == 2
    assert second.blocks_updated == 0
    assert second.blocks_unchanged == 5


def test_the_reconciliation_result_is_stable_across_runs(filing) -> None:
    _, first, _ = run(filing)
    _, second, _ = run(filing)
    assert first.as_record() == second.as_record()


def test_the_advisory_lock_key_is_deterministic_across_processes() -> None:
    """Two workers must take the SAME lock, or neither serializes the other."""
    import subprocess
    import sys

    here = advisory_lock_key(ACCESSION)
    there = subprocess.run(
        [
            sys.executable,
            "-c",
            "from packages.footnote_canonicalizer.persistence import advisory_lock_key;"
            f"print(advisory_lock_key({ACCESSION!r}))",
        ],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    assert str(here) == there
    assert -(2**63) <= here < 2**63


def test_the_lock_is_held_for_the_transaction(filing) -> None:
    """A second connection must not acquire the same key while a run holds it."""
    key = advisory_lock_key(ACCESSION)
    with filing.begin() as holder:
        holder.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": key})
        with filing.connect() as other:
            acquired = other.execute(
                text("SELECT pg_try_advisory_xact_lock(:k)"), {"k": key}
            ).scalar_one()
    assert acquired is False


# --- orphans and failure ---------------------------------------------------------------------------


def test_an_orphan_is_persisted_with_a_null_parent_not_omitted(filing) -> None:
    """A missing row is indistinguishable from a filing that never had that block."""
    result, completeness, _ = run(filing, orphan=True)
    assert result.orphan_count == 1
    assert completeness.extraction_status == "PARTIAL"

    with filing.connect() as connection:
        row = connection.execute(
            text(
                "SELECT external_id, grouping_method, grouping_evidence FROM footnote_source_block"
                " WHERE footnote_id IS NULL AND filing_id IN"
                " (SELECT filing_id FROM filing WHERE accession = :a)"
            ),
            {"a": ACCESSION},
        ).one()
    assert row[0] == "R7"
    assert row[1] is None
    assert row[2]["reason"]


def test_a_missing_filing_row_fails_before_anything_is_written(integration_engine) -> None:
    result, headings = build_result()
    with pytest.raises(PersistenceError, match="no filing row"):
        persist(integration_engine, result, evaluate(result), {})


def test_a_failed_run_leaves_nothing_behind(filing, monkeypatch) -> None:
    """ONE TRANSACTION. A partially canonicalized filing would carry counters no run produced."""
    from packages.footnote_canonicalizer import persistence

    original = persistence._upsert_section

    def explode(*args, **kwargs):
        raise RuntimeError("deliberate failure after footnotes were written")

    monkeypatch.setattr(persistence, "_upsert_section", explode)
    with pytest.raises(RuntimeError, match="deliberate failure"):
        run(filing)
    monkeypatch.setattr(persistence, "_upsert_section", original)

    assert counts_for(filing, "canonical_footnote") == 0
    assert counts_for(filing, "footnote_source_block") == 0


def test_no_model_was_invoked(filing) -> None:
    """Sprint 4 is deterministic. The acceptance run must produce zero llm_invocation rows."""
    run(filing)
    with filing.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM llm_invocation")).scalar_one() == 0


def test_the_table_is_persisted_with_cell_provenance(filing) -> None:
    run(filing)
    with filing.connect() as connection:
        row = connection.execute(
            text(
                "SELECT external_id, cells, column_headers, validation_warnings"
                " FROM footnote_table WHERE filing_id IN"
                " (SELECT filing_id FROM filing WHERE accession = :a)"
            ),
            {"a": ACCESSION},
        ).one()
    assert row[0] == "T1"
    flat = [cell for grid_row in row[1] for cell in grid_row]
    assert any(c["text"] == "(1,234)" for c in flat), "the filed numeric text must survive"
    assert all("row" in c and "column" in c for c in flat)
    assert row[2] == [["Year", "Value"]]
    assert row[3]["parse_state"]


def test_uuid_identity_is_stable_across_reruns(filing) -> None:
    """A rerun updates in place; a footnote keeps its identifier so citations stay valid."""
    run(filing)
    with filing.connect() as connection:
        first = {
            r[0]: uuid.UUID(str(r[1]))
            for r in connection.execute(
                text(
                    "SELECT sequence, footnote_id FROM canonical_footnote WHERE filing_id IN"
                    " (SELECT filing_id FROM filing WHERE accession = :a)"
                ),
                {"a": ACCESSION},
            )
        }
    run(filing)
    with filing.connect() as connection:
        second = {
            r[0]: uuid.UUID(str(r[1]))
            for r in connection.execute(
                text(
                    "SELECT sequence, footnote_id FROM canonical_footnote WHERE filing_id IN"
                    " (SELECT filing_id FROM filing WHERE accession = :a)"
                ),
                {"a": ACCESSION},
            )
        }
    assert first == second


# --- ownership and true no-op idempotency --------------------------------------------------------


def _ownership_for(result):
    """Classify the synthetic filing's one table as belonging to the Debt note."""
    from packages.footnote_canonicalizer import classify_tables
    from packages.footnote_extractor.presentation import PresentationLinkbase, RolePresentation
    from packages.footnote_extractor.tagged_blocks import TaggedSpan

    debt = "http://x/role/Debt"
    linkbase = PresentationLinkbase(
        roles={debt: RolePresentation(debt, ("us-gaap:DebtDisclosureTextBlock",))}
    )
    tables = parse_tables(TABLE_HTML)
    spans = [
        TaggedSpan(
            concept="us-gaap:DebtDisclosureTextBlock",
            start=0,
            end=10_000,
            tag="ix:nonnumeric",
        )
    ]
    return classify_tables(result, tables, spans, linkbase)


def run_with_ownership(engine):
    result, headings = build_result()
    ownership = _ownership_for(result)
    completeness = evaluate(result, ownership)
    heading_map = {
        note.role_uri: heading
        for note, heading in zip(result.footnotes, headings, strict=False)
        if note.role_uri
    }
    counts = persist(
        engine,
        result,
        completeness,
        heading_map,
        tables=parse_tables(TABLE_HTML),
        table_storage_uri="filings/x/y.htm",
        ownership=ownership,
    )
    return result, completeness, counts, ownership


def test_a_footnote_owned_table_persists_its_owner_and_evidence(filing) -> None:
    """CRITERION 10. A table in a note's tagged block carries that note's footnote_id."""
    run_with_ownership(filing)
    with filing.connect() as connection:
        row = connection.execute(
            text(
                "SELECT t.footnote_id, t.ownership_kind, t.ownership_method, t.ownership_evidence,"
                " c.title_as_displayed FROM footnote_table t"
                " JOIN canonical_footnote c ON c.footnote_id = t.footnote_id"
                " WHERE t.filing_id IN (SELECT filing_id FROM filing WHERE accession = :a)"
            ),
            {"a": ACCESSION},
        ).one()
    assert row[0] is not None
    assert row[1] == "CANONICAL_FOOTNOTE"
    assert row[2]
    assert row[3]["owner_role_uri"] == "http://x/role/Debt"
    assert row[3]["reason"]
    assert row[4] == "Debt"


def test_the_database_rejects_a_contradictory_ownership_row(filing) -> None:
    """Migration 0002's check constraint: CANONICAL_FOOTNOTE requires a footnote_id.

    Enforced in the database so the classification and the foreign key cannot drift apart no
    matter which code path writes them.
    """
    from sqlalchemy.exc import IntegrityError

    run_with_ownership(filing)
    with pytest.raises(IntegrityError), filing.begin() as connection:
        connection.execute(
            text(
                "UPDATE footnote_table SET footnote_id = NULL"
                " WHERE ownership_kind = 'CANONICAL_FOOTNOTE'"
                "   AND filing_id IN (SELECT filing_id FROM filing WHERE accession = :a)"
            ),
            {"a": ACCESSION},
        )


def test_an_identical_rerun_writes_nothing_at_all(filing) -> None:
    """IDEMPOTENCY, stronger than "no duplicates".

    An unconditional upsert rewrites every row, stamping a fresh extraction_run_id and
    grouping_decided_at onto decisions that did not change — so those fields end up answering
    "which run last touched this" while their names promise "which run decided this".
    """
    run_with_ownership(filing)
    before = _digest(filing)

    _, _, counts, _ = run_with_ownership(filing)

    assert counts.footnotes_inserted == 0
    assert counts.footnotes_updated == 0
    assert counts.footnotes_unchanged == 2
    assert counts.blocks_inserted == 0
    assert counts.blocks_updated == 0
    assert counts.blocks_unchanged == 5
    assert _digest(filing) == before, "an identical rerun changed persisted state"


def test_a_changed_input_still_updates_deliberately(filing) -> None:
    """A no-op rerun must not cost the ability to correct a record.

    The conditional update is on the VALUES, not on a flag, so genuinely changed authoritative
    input still writes — and its audit fields move with it.
    """
    run_with_ownership(filing)
    before = _digest(filing)

    with filing.begin() as connection:
        connection.execute(
            text(
                "UPDATE canonical_footnote SET title_as_displayed = 'Stale Title'"
                " WHERE sequence = 1 AND filing_id IN"
                " (SELECT filing_id FROM filing WHERE accession = :a)"
            ),
            {"a": ACCESSION},
        )

    _, _, counts, _ = run_with_ownership(filing)
    assert counts.footnotes_updated == 1
    assert counts.footnotes_unchanged == 1
    assert _digest(filing) == before, "the correction did not restore the authoritative value"


def test_the_audit_run_id_survives_an_unchanged_rerun(filing) -> None:
    """`grouping_decided_at` means when the decision was made, not when it was last confirmed."""
    run_with_ownership(filing)
    with filing.connect() as connection:
        first = connection.execute(
            text(
                "SELECT external_id, extraction_run_id, grouping_decided_at"
                " FROM footnote_source_block WHERE filing_id IN"
                " (SELECT filing_id FROM filing WHERE accession = :a) ORDER BY external_id"
            ),
            {"a": ACCESSION},
        ).all()

    run_with_ownership(filing)
    with filing.connect() as connection:
        second = connection.execute(
            text(
                "SELECT external_id, extraction_run_id, grouping_decided_at"
                " FROM footnote_source_block WHERE filing_id IN"
                " (SELECT filing_id FROM filing WHERE accession = :a) ORDER BY external_id"
            ),
            {"a": ACCESSION},
        ).all()

    assert first == second


def _digest(engine) -> str:
    """A normalized snapshot of every persisted value for this filing, timestamps included."""
    import hashlib
    import json as _json

    queries = (
        "SELECT * FROM canonical_footnote WHERE filing_id IN"
        " (SELECT filing_id FROM filing WHERE accession = :a) ORDER BY sequence",
        "SELECT * FROM footnote_source_block WHERE filing_id IN"
        " (SELECT filing_id FROM filing WHERE accession = :a) ORDER BY external_id",
        "SELECT * FROM footnote_table WHERE filing_id IN"
        " (SELECT filing_id FROM filing WHERE accession = :a) ORDER BY external_id",
        "SELECT * FROM filing_section WHERE filing_id IN"
        " (SELECT filing_id FROM filing WHERE accession = :a) ORDER BY sequence",
    )
    rows = []
    with engine.connect() as connection:
        for query in queries:
            rows.append(
                [
                    tuple(str(v) for v in row)
                    for row in connection.execute(text(query), {"a": ACCESSION})
                ]
            )
    return hashlib.sha256(_json.dumps(rows, sort_keys=True).encode()).hexdigest()
