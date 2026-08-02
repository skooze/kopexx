"""The DERA fact load, end to end against a live PostgreSQL.

Builds a small synthetic package rather than reading a mirrored one. A test that depends on a
2 GiB archive cannot run on a fresh clone, and Sprint 3 committed to `pytest` passing offline.
The package here has the same shape as a real one, so it exercises the same code path.

SKIPS when no database is reachable, with a reason. It never passes vacuously.
"""

from __future__ import annotations

import uuid
import zipfile
from pathlib import Path

import pytest
from sqlalchemy import text

from packages.dera_notes.ledger import MirrorEntry, MirrorLedger
from packages.dera_notes.loader import SOURCE_DATASET, load_facts, read_package, verify_package
from packages.dera_notes.reconcile import reconcile
from packages.dera_notes.registration import register_filing, register_mirror_ledger
from packages.dera_notes.selection import locate_filing
from packages.storage import sha256_file

pytestmark = pytest.mark.integration

CIK = "0000999999"
ACCESSION = "9999999999-25-000001"
PACKAGE = "2025_10_notes.zip"

SUB = (
    "adsh\tcik\tname\tsic\tfye\tform\tperiod\tfy\tfp\tfiled\tprevrpt\tdetail\tinstance"
    "\tcountryinc\tstprinc\n"
    f"{ACCESSION}\t999999\tFIXTURE CORP\t3571\t0930\t10-K\t20250930\t2025\tFY\t20251031"
    "\t0\t1\tfix-20250930_htm.xml\tUS\tCA\n"
)

# Two consolidated facts, one dimensional fact, one instant, and one row with no value at all.
# The last is the shape DERA uses for a line-item label and must be rejected, not loaded.
NUM = (
    "adsh\ttag\tversion\tddate\tqtrs\tuom\tdimh\tiprx\tvalue\tcoreg\n"
    f"{ACCESSION}\tRevenues\tus-gaap/2025\t20250930\t4\tUSD\t0x00000000\t0\t100.0000\t\n"
    f"{ACCESSION}\tRevenues\tus-gaap/2025\t20250630\t1\tUSD\t0x00000000\t0\t25.0000\t\n"
    f"{ACCESSION}\tRevenues\tus-gaap/2025\t20250930\t4\tUSD\t0xAAAA\t0\t60.0000\t\n"
    f"{ACCESSION}\tAssets\tus-gaap/2025\t20250930\t0\tUSD\t0x00000000\t0\t500.0000\t\n"
    f"{ACCESSION}\tCommitmentsAndContingencies\tus-gaap/2025\t20250930\t0\tUSD\t0x00000000\t0\t\t\n"
    "1111111111-25-000001\tRevenues\tus-gaap/2025\t20250930\t4\tUSD\t0x00000000\t0\t999.0000\t\n"
)

DIM = "dimhash\tsegments\tsegt\n0x00000000\t\t0\n0xAAAA\tStatementBusinessSegments=Americas;\t0\n"

EXPECTED_ACCEPTED = 4
EXPECTED_TOTAL = 100 + 25 + 60 + 500


@pytest.fixture
def package(tmp_path: Path) -> Path:
    path = tmp_path / "monthly" / PACKAGE
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as writer:
        writer.writestr("sub.tsv", SUB)
        writer.writestr("num.tsv", NUM)
        writer.writestr("dim.tsv", DIM)
        for member in ("pre.tsv", "tag.tsv", "ren.tsv", "txt.tsv"):
            writer.writestr(member, "adsh\n")
    return path


@pytest.fixture
def ledger(package: Path) -> MirrorLedger:
    ledger = MirrorLedger()
    ledger.record(
        MirrorEntry(
            filename=PACKAGE,
            url=f"https://www.sec.gov/files/{PACKAGE}",
            cadence="monthly",
            period="2025-10",
            sha256=sha256_file(package),
            size_bytes=package.stat().st_size,
            retrieved_at="2026-08-01T00:00:00+00:00",
            storage_key=f"monthly/{PACKAGE}",
        )
    )
    return ledger


@pytest.fixture
def loaded(database_engine, package: Path, ledger: MirrorLedger):  # type: ignore[no-untyped-def]
    """Register, load, and clean up afterwards.

    Cleanup deletes rather than rolls back, because the loader owns its own transaction: a test
    that wrapped it in an outer transaction would not be testing the real commit boundary.
    """
    engine = database_engine
    root = package.parent.parent
    register_mirror_ledger(engine, ledger, root)
    selected = locate_filing(ACCESSION, package_root=root, ledger=ledger)
    context = register_filing(engine, selected.path, ACCESSION)
    result = load_facts(engine, selected, context)
    try:
        yield engine, selected, context, result
    finally:
        with engine.begin() as connection:
            connection.execute(text("DELETE FROM xbrl_fact WHERE accession = :a"), {"a": ACCESSION})
            connection.execute(text("DELETE FROM filing WHERE accession = :a"), {"a": ACCESSION})
            connection.execute(text("DELETE FROM issuer WHERE cik = :c"), {"c": CIK})
            connection.execute(text("DELETE FROM dera_package WHERE filename = :f"), {"f": PACKAGE})


def test_the_load_inserts_only_this_accessions_facts(loaded) -> None:  # type: ignore[no-untyped-def]
    """A monthly package holds thousands of companies. Only the named filing is loaded."""
    _, _, _, result = loaded
    assert result.state == "COMPLETE"
    assert result.read.rows_matched == 5, "the other issuer's row must not even be matched"
    assert result.rows_inserted == EXPECTED_ACCEPTED


def test_a_row_without_a_value_is_rejected_and_counted_not_dropped(loaded) -> None:  # type: ignore[no-untyped-def]
    _, _, _, result = loaded
    assert result.read.rejected == 1
    assert result.read.accepted + result.read.rejected == result.read.rows_matched


def test_reconciliation_passes_on_a_correct_load(loaded) -> None:  # type: ignore[no-untyped-def]
    engine, _, _, result = loaded
    report = reconcile(engine, result)
    assert report.ok, f"failed checks: {[c.name for c in report.failures]}"


def test_the_numeric_total_survives_the_round_trip(loaded) -> None:  # type: ignore[no-untyped-def]
    """The strongest single check that no row was lost, duplicated, or mangled."""
    _, _, _, result = loaded
    assert result.database_value_total == EXPECTED_TOTAL


def test_a_dimensional_fact_does_not_land_in_the_consolidated_series(loaded) -> None:  # type: ignore[no-untyped-def]
    engine, _, _, _ = loaded
    with engine.connect() as connection:
        consolidated = connection.execute(
            text(
                "SELECT count(*) FROM xbrl_fact WHERE accession = :a AND dimensions = '{}'::jsonb"
            ),
            {"a": ACCESSION},
        ).scalar_one()
        dimensional = connection.execute(
            text(
                "SELECT dimensions FROM xbrl_fact"
                " WHERE accession = :a AND dimensions <> '{}'::jsonb"
            ),
            {"a": ACCESSION},
        ).scalar_one()
    assert consolidated == 3
    assert dimensional == {"StatementBusinessSegments": "Americas"}


def test_a_rerun_inserts_nothing(loaded) -> None:  # type: ignore[no-untyped-def]
    """IDEMPOTENCY. The second run re-reads everything and finds every key already present."""
    engine, selected, context, first = loaded
    second = load_facts(engine, selected, context)

    assert second.read.accepted == first.read.accepted, "the package must be re-read, not skipped"
    assert second.rows_inserted == 0
    assert second.rows_already_present == first.read.accepted
    assert second.rows_in_database == first.rows_in_database
    assert reconcile(engine, second).ok


def test_the_load_ledger_is_marked_only_on_success(loaded) -> None:  # type: ignore[no-untyped-def]
    engine, _, _, _ = loaded
    with engine.connect() as connection:
        loaded_at = connection.execute(
            text("SELECT loaded_at FROM dera_package WHERE filename = :f"), {"f": PACKAGE}
        ).scalar_one()
    assert loaded_at is not None


def test_facts_are_written_unvalidated_because_nothing_has_validated_them(loaded) -> None:  # type: ignore[no-untyped-def]
    """Writing VALID would be a claim no code in this repository has earned yet."""
    engine, _, _, _ = loaded
    with engine.connect() as connection:
        statuses = {
            row[0]
            for row in connection.execute(
                text("SELECT DISTINCT validation_status FROM xbrl_fact WHERE accession = :a"),
                {"a": ACCESSION},
            )
        }
    assert statuses == {"UNVALIDATED"}


def test_a_missing_filing_row_fails_before_any_fact_is_written(
    database_engine, package: Path, ledger: MirrorLedger
) -> None:  # type: ignore[no-untyped-def]
    """xbrl_fact has foreign keys to filing and issuer. Acquisition must precede the fact load."""
    from packages.dera_notes.registration import RegistrationError

    root = package.parent.parent
    selected = locate_filing(ACCESSION, package_root=root, ledger=ledger)
    with pytest.raises(RegistrationError, match="does not list"):
        register_filing(database_engine, selected.path, "0000000000-99-999999")


def test_a_package_whose_bytes_changed_since_mirroring_is_refused(
    package: Path, ledger: MirrorLedger
) -> None:
    """Trusting the download-time hash would let a file that rotted on disk load silently."""
    from packages.dera_notes.loader import LoadError

    root = package.parent.parent
    selected = locate_filing(ACCESSION, package_root=root, ledger=ledger)
    tampered = type(selected)(**{**selected.__dict__, "sha256": "0" * 64})
    with pytest.raises(LoadError, match="hash mismatch"):
        verify_package(tampered)


def test_reading_a_package_touches_no_database(package: Path, ledger: MirrorLedger) -> None:
    """Parsing, normalization, and validation are separable from persistence, and stay so."""
    root = package.parent.parent
    selected = locate_filing(ACCESSION, package_root=root, ledger=ledger)
    parsed = read_package(selected, ACCESSION, cik=CIK, count_all_members=False)
    assert parsed.accepted == EXPECTED_ACCEPTED
    assert parsed.value_total == EXPECTED_TOTAL


def test_the_source_dataset_is_recorded_on_every_row(loaded) -> None:  # type: ignore[no-untyped-def]
    """Provenance: a later XBRL-instance load must be distinguishable from this one."""
    engine, _, _, _ = loaded
    with engine.connect() as connection:
        datasets = {
            row[0]
            for row in connection.execute(
                text("SELECT DISTINCT source_dataset FROM xbrl_fact WHERE accession = :a"),
                {"a": ACCESSION},
            )
        }
    assert datasets == {SOURCE_DATASET}


def test_the_filing_row_is_derived_from_the_package_not_guessed(loaded) -> None:  # type: ignore[no-untyped-def]
    engine, _, context, _ = loaded
    assert isinstance(context.filing_id, uuid.UUID)
    with engine.connect() as connection:
        row = (
            connection.execute(
                text(
                    "SELECT form, filing_date, report_date, fiscal_year, fiscal_period, is_xbrl,"
                    " is_inline_xbrl, era FROM filing WHERE accession = :a"
                ),
                {"a": ACCESSION},
            )
            .mappings()
            .one()
        )

    assert row["form"] == "10-K"
    assert row["filing_date"].isoformat() == "2025-10-31"
    assert row["report_date"].isoformat() == "2025-09-30"
    assert row["fiscal_year"] == 2025 and row["fiscal_period"] == "FY"
    assert row["is_xbrl"] is True
    assert row["is_inline_xbrl"] is True, "DERA names an inline instance <doc>_htm.xml"
    assert row["era"] is None, "DERA does not describe the acquisition era; guessing it would lie"
