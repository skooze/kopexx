"""Choosing the DERA package that contains a filing, and refusing an incomplete one."""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from packages.dera_notes.dimensions import DimensionIndex, parse_segments
from packages.dera_notes.ledger import MirrorEntry, MirrorLedger
from packages.dera_notes.selection import (
    REQUIRED_MEMBERS,
    PackageSelectionError,
    accessions_in_package,
    assert_members_present,
    locate_filing,
    period_sort_key,
)

ACCESSION = "0000320193-25-000079"
OTHER = "0000320193-25-000008"


def _write_package(path: Path, accessions: list[str], *, omit: str | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    sub = "adsh\tcik\tname\tform\n" + "".join(f"{a}\t320193\tAPPLE INC\t10-K\n" for a in accessions)
    with zipfile.ZipFile(path, "w") as writer:
        for member in REQUIRED_MEMBERS:
            if member == omit:
                continue
            writer.writestr(member, sub if member == "sub.tsv" else "adsh\n")


def _ledger(entries: list[tuple[str, str, str]]) -> MirrorLedger:
    """entries: (filename, cadence, period)."""
    ledger = MirrorLedger()
    for filename, cadence, period in entries:
        ledger.record(
            MirrorEntry(
                filename=filename,
                url=f"https://www.sec.gov/files/{filename}",
                cadence=cadence,
                period=period,
                sha256="0" * 64,
                size_bytes=1,
                retrieved_at="2026-08-01T00:00:00+00:00",
                storage_key=f"{cadence}/{filename}",
            )
        )
    return ledger


# --- period ordering ------------------------------------------------------------------------


def test_monthly_and_quarterly_periods_order_by_the_period_they_end_in() -> None:
    """The ledger writes `2025-10` and `2025Q2`. Raw string order compares '-' against 'Q'."""
    assert period_sort_key("quarterly", "2025Q2") < period_sort_key("monthly", "2025-07")
    assert period_sort_key("monthly", "2025-07") < period_sort_key("quarterly", "2025Q3")
    assert period_sort_key("monthly", "2025-12") < period_sort_key("monthly", "2026-01")


def test_the_quarterly_package_wins_a_tie_because_monthlies_are_deleted_upstream() -> None:
    """A load citing a monthly package becomes unreproducible once SEC consolidates and deletes it."""
    assert period_sort_key("quarterly", "2025Q2") > period_sort_key("monthly", "2025-06")


# --- member completeness --------------------------------------------------------------------


def test_a_complete_package_passes(tmp_path: Path) -> None:
    path = tmp_path / "2025_10_notes.zip"
    _write_package(path, [ACCESSION])
    assert_members_present(path)


def test_a_package_missing_a_member_fails_closed(tmp_path: Path) -> None:
    """A short package loads partially and looks successful: the count is simply lower, which is
    indistinguishable from a quiet month."""
    path = tmp_path / "broken.zip"
    _write_package(path, [ACCESSION], omit="num.tsv")
    with pytest.raises(PackageSelectionError, match="num.tsv"):
        assert_members_present(path)


# --- locating a filing ----------------------------------------------------------------------


def test_the_package_is_chosen_by_reading_sub_tsv_not_by_deriving_a_period(tmp_path: Path) -> None:
    """SEC-INVARIANT: a filing belongs to the period it was SUBMITTED in.

    Apple's FY2025 10-K reports on a year ending 2025-09-27 and was filed 2025-10-31, so it lives
    in the 2025-10 package. Deriving a period from the report date would confidently pick 2025Q3
    and find nothing, or worse, find a different filing.
    """
    _write_package(tmp_path / "monthly" / "2025_10_notes.zip", [ACCESSION])
    _write_package(tmp_path / "quarterly" / "2025q3_notes.zip", [OTHER])

    selected = locate_filing(
        ACCESSION,
        package_root=tmp_path,
        ledger=_ledger(
            [
                ("2025_10_notes.zip", "monthly", "2025-10"),
                ("2025q3_notes.zip", "quarterly", "2025Q3"),
            ]
        ),
    )
    assert selected.filename == "2025_10_notes.zip"
    assert "SUBMITTED" in selected.reason


def test_an_accession_in_no_package_raises_rather_than_returning_a_guess(tmp_path: Path) -> None:
    _write_package(tmp_path / "monthly" / "2025_10_notes.zip", [OTHER])
    with pytest.raises(PackageSelectionError, match="no mirrored package"):
        locate_filing(
            ACCESSION,
            package_root=tmp_path,
            ledger=_ledger([("2025_10_notes.zip", "monthly", "2025-10")]),
        )


def test_an_empty_ledger_raises(tmp_path: Path) -> None:
    with pytest.raises(PackageSelectionError, match="empty"):
        locate_filing(ACCESSION, package_root=tmp_path, ledger=_ledger([]))


def test_a_selected_package_is_also_checked_for_completeness(tmp_path: Path) -> None:
    _write_package(tmp_path / "monthly" / "2025_10_notes.zip", [ACCESSION], omit="txt.tsv")
    with pytest.raises(PackageSelectionError, match="txt.tsv"):
        locate_filing(
            ACCESSION,
            package_root=tmp_path,
            ledger=_ledger([("2025_10_notes.zip", "monthly", "2025-10")]),
        )


def test_accessions_can_be_filtered_to_one_cik(tmp_path: Path) -> None:
    path = tmp_path / "p.zip"
    _write_package(path, [ACCESSION, OTHER])
    assert accessions_in_package(path, cik="0000320193") == [ACCESSION, OTHER]
    assert accessions_in_package(path, cik="0000789019") == []


# --- dimensions -----------------------------------------------------------------------------


def test_segments_parse_into_axis_and_member() -> None:
    assert parse_segments("EquityComponents=RetainedEarnings;") == {
        "EquityComponents": "RetainedEarnings"
    }
    assert parse_segments("A=1;B=2;") == {"A": "1", "B": "2"}
    assert parse_segments("") == {}
    assert parse_segments(None) == {}


def test_a_member_value_containing_a_comma_or_space_survives() -> None:
    """DERA member labels are free text: `InvestmentIdentifier=Arrowhead Holdco Company, ...`."""
    parsed = parse_segments("InvestmentIdentifier=Arrowhead Holdco Company, Inc., Common stock;")
    assert parsed["InvestmentIdentifier"] == "Arrowhead Holdco Company, Inc., Common stock"


def test_an_unparseable_segment_still_marks_the_fact_dimensional() -> None:
    """Dropping it would promote a dimensional fact into the consolidated series."""
    assert parse_segments("MalformedSegment;") == {"MalformedSegment": ""}


def test_the_zero_hash_resolves_to_no_dimensions(tmp_path: Path) -> None:
    """`dimensions = '{}'::jsonb` is what the consolidated-series partial index selects on."""
    index = DimensionIndex({"0xabc": {"A": "1"}}, frozenset())
    assert index.resolve("0x00000000") == {}
    assert index.resolve("") == {}
    assert index.resolve("0xabc") == {"A": "1"}


def test_an_undefined_hash_is_reported_rather_than_treated_as_consolidated() -> None:
    index = DimensionIndex({"0xabc": {"A": "1"}}, frozenset())
    assert index.is_known("0x00000000") is True
    assert index.is_known("0xabc") is True
    assert index.is_known("0xmissing") is False


def test_deras_own_truncation_flag_is_carried_through() -> None:
    index = DimensionIndex({"0xabc": {"A": "1"}}, frozenset({"0xabc"}))
    assert index.is_truncated("0xabc") is True
    assert index.is_truncated("0x00000000") is False


def test_the_advisory_lock_key_is_deterministic_across_processes() -> None:
    """Two loaders of one accession must take the SAME lock, or neither serializes the other.

    Python's `hash()` is salted per process and would give each loader a different key, so both
    would proceed, both would read an empty existing-key set, and both would insert.
    """
    import subprocess
    import sys

    from packages.dera_notes.loader import advisory_lock_key

    here = advisory_lock_key(ACCESSION)
    there = subprocess.run(
        [
            sys.executable,
            "-c",
            "from packages.dera_notes.loader import advisory_lock_key;"
            f"print(advisory_lock_key({ACCESSION!r}))",
        ],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()

    assert str(here) == there
    assert -(2**63) <= here < 2**63, "pg_advisory_xact_lock takes a signed 64-bit integer"
    assert advisory_lock_key(ACCESSION) != advisory_lock_key(OTHER)
