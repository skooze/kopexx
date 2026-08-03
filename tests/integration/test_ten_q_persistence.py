"""The quarterly filings persisted to a live PostgreSQL: idempotency and digest stability.

tests/unit/test_ten_q_regression.py proves the three FY2025 10-Qs canonicalize to ten notes with
every child attached. This file carries the other half of that claim: writing those results to the
database twice must insert nothing and update nothing the second time, and must leave every
persisted value byte-identical.

Post-Sprint-4 hardening. No behaviour changes; this asserts what the Sprint 4 code already did.

WHY THE ACCESSION IS A FIXTURE VALUE. The STRUCTURE under test is the real filing's — the report
inventory is read from the committed FilingSummary of each 10-Q, so the notes, the children, and
the attachment decisions are the measured ones. The accession the rows are keyed on is not, because
`persist` resolves a filing by accession and the real accessions belong to the four filings already
loaded on a development host. Reusing them would collide with `UNIQUE(accession)` locally while
passing on a fresh CI database, which is a test that only fails where nobody looks. The mapping
below records which real filing each fixture accession stands for.

NON-DESTRUCTIVE. Creates its own issuer and filing rows and removes exactly those. The session gate
in tests/conftest.py fails the run if the application row counts do not return to where they began.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from sqlalchemy import text

from packages.footnote_canonicalizer import ExclusionList, canonicalize, evaluate
from packages.footnote_canonicalizer.persistence import persist
from packages.footnote_extractor import NoteHeading, read_inventory

pytestmark = pytest.mark.integration

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "filings"

CIK = "0000999995"

# fixture accession -> the real filing whose structure it carries, complete as recorded in
# tests/fixtures/filings/manifest.yaml.
SOURCE_OF = {
    "9999999995-25-000001": "0000320193-25-000008",
    "9999999995-25-000002": "0000320193-25-000057",
    "9999999995-25-000003": "0000320193-25-000073",
}

# Measured. Blocks are the ten parent narratives plus the attached children: 10 + 23, 10 + 23,
# 10 + 25. Kept here rather than imported so a change to one file cannot silently move the other.
EXPECTED_BLOCKS = {
    "9999999995-25-000001": 33,
    "9999999995-25-000002": 33,
    "9999999995-25-000003": 35,
}
EXPECTED_FOOTNOTES = 10
EXPECTED_SECTIONS = 2


def _canonicalize(fixture_accession: str):
    """Canonicalize the real quarterly filing under a fixture accession."""
    source = SOURCE_OF[fixture_accession]
    inventory = read_inventory(FIXTURES / source / "filing-summary.xml")
    exclusions = ExclusionList.load()

    discovered = canonicalize(
        accession=fixture_accession, inventory=inventory, headings=(), exclusions=exclusions
    )
    headings = tuple(
        NoteHeading(number=i, title=f"Note {i}", line_index=i, joined_from_next_line=True)
        for i in range(1, len(discovered.footnotes) + 1)
    )
    result = canonicalize(
        accession=fixture_accession,
        inventory=inventory,
        headings=headings,
        exclusions=exclusions,
    )
    heading_map = {
        note.role_uri: heading
        for note, heading in zip(result.footnotes, headings, strict=False)
        if note.role_uri
    }
    return result, heading_map


def _run(engine, fixture_accession: str):
    result, heading_map = _canonicalize(fixture_accession)
    counts = persist(engine, result, evaluate(result), heading_map)
    return result, counts


def _digest(engine, accession: str) -> str:
    """A normalized snapshot of every persisted value for one filing, timestamps included.

    Comparing counts alone would miss an unconditional upsert that rewrites identical values with a
    fresh extraction_run_id — the audit defect the conditional upsert exists to prevent.
    """
    queries = (
        "SELECT * FROM canonical_footnote WHERE filing_id IN"
        " (SELECT filing_id FROM filing WHERE accession = :a) ORDER BY sequence",
        "SELECT * FROM footnote_source_block WHERE filing_id IN"
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
                    for row in connection.execute(text(query), {"a": accession})
                ]
            )
    return hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest()


@pytest.fixture
def quarterly_filings(integration_engine):
    """One issuer and three filing rows for the quarterly results to attach to."""
    engine = integration_engine
    with engine.begin() as connection:
        issuer_id = connection.execute(
            text(
                "INSERT INTO issuer (issuer_id, cik, legal_name, is_active)"
                " VALUES (gen_random_uuid(), :cik, 'Quarterly Regression Fixture', true)"
                " RETURNING issuer_id"
            ),
            {"cik": CIK},
        ).scalar_one()
        for accession in SOURCE_OF:
            connection.execute(
                text(
                    "INSERT INTO filing (filing_id, issuer_id, cik, accession, form, filing_date,"
                    " is_amendment, is_xbrl, is_inline_xbrl, processing_state, footnote_status,"
                    " reconciliation_status)"
                    " VALUES (gen_random_uuid(), :i, :cik, :a, '10-Q', '2025-05-02', false, true,"
                    " true, 'DISCOVERED', 'NOT_STARTED', 'NOT_ATTEMPTED')"
                ),
                {"i": issuer_id, "cik": CIK, "a": accession},
            )
    try:
        yield engine
    finally:
        with engine.begin() as connection:
            for accession in SOURCE_OF:
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
                    connection.execute(text(statement), {"a": accession})
            connection.execute(text("DELETE FROM issuer WHERE cik = :c"), {"c": CIK})


@pytest.mark.parametrize("accession", sorted(SOURCE_OF))
def test_the_first_run_persists_the_measured_structure(accession: str, quarterly_filings) -> None:
    _, counts = _run(quarterly_filings, accession)

    assert counts.canonical_footnotes == EXPECTED_FOOTNOTES
    assert counts.footnotes_inserted == EXPECTED_FOOTNOTES
    assert counts.source_blocks == EXPECTED_BLOCKS[accession]
    assert counts.blocks_inserted == EXPECTED_BLOCKS[accession]
    assert counts.filing_sections == EXPECTED_SECTIONS


@pytest.mark.parametrize("accession", sorted(SOURCE_OF))
def test_an_identical_rerun_inserts_nothing_and_updates_nothing(
    accession: str, quarterly_filings
) -> None:
    """IDEMPOTENCY, on the real quarterly structure rather than a two-note synthetic one."""
    _run(quarterly_filings, accession)
    before = _digest(quarterly_filings, accession)

    _, counts = _run(quarterly_filings, accession)

    assert counts.footnotes_inserted == 0
    assert counts.footnotes_updated == 0
    assert counts.footnotes_unchanged == EXPECTED_FOOTNOTES
    assert counts.blocks_inserted == 0
    assert counts.blocks_updated == 0
    assert counts.blocks_unchanged == EXPECTED_BLOCKS[accession]
    assert _digest(quarterly_filings, accession) == before, "a rerun changed persisted state"


def test_the_three_quarters_persist_independently(quarterly_filings) -> None:
    """Writing one quarter must not touch another's rows.

    All three share an issuer and a note structure that is nearly identical, so a filing_id that
    leaked out of one upsert would land somewhere plausible and stay invisible in a per-filing test.
    """
    digests = {}
    for accession in sorted(SOURCE_OF):
        _run(quarterly_filings, accession)
        digests[accession] = _digest(quarterly_filings, accession)

    for accession in sorted(SOURCE_OF):
        _run(quarterly_filings, accession)
        assert _digest(quarterly_filings, accession) == digests[accession]

    assert len(set(digests.values())) == 3, "two quarters produced the same persisted state"

    with quarterly_filings.connect() as connection:
        total = connection.execute(
            text(
                "SELECT count(*) FROM canonical_footnote WHERE filing_id IN"
                " (SELECT filing_id FROM filing WHERE cik = :c)"
            ),
            {"c": CIK},
        ).scalar_one()
    assert total == EXPECTED_FOOTNOTES * len(SOURCE_OF)


@pytest.mark.parametrize("accession", sorted(SOURCE_OF))
def test_no_source_block_is_persisted_without_a_parent(accession: str, quarterly_filings) -> None:
    """Zero orphans, asserted against the stored rows rather than the in-memory result."""
    _run(quarterly_filings, accession)
    with quarterly_filings.connect() as connection:
        orphans = connection.execute(
            text(
                "SELECT count(*) FROM footnote_source_block WHERE footnote_id IS NULL"
                " AND filing_id IN (SELECT filing_id FROM filing WHERE accession = :a)"
            ),
            {"a": accession},
        ).scalar_one()
    assert orphans == 0
