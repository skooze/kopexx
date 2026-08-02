"""The plain-text load report.

The report is how a person decides whether a load can be trusted, so the things it must never omit
are asserted here: the reconciliation verdict, the failing checks, and the rejection counts.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

from packages.dera_notes.loader import LoadResult, ReadResult
from packages.dera_notes.normalize import NormalizedFact
from packages.dera_notes.reconcile import Check, Reconciliation
from packages.dera_notes.report import (
    full_report,
    load_report,
    reconciliation_report,
    selection_report,
)
from packages.dera_notes.selection import SelectedPackage
from packages.dera_notes.validate import Rejection

ACCESSION = "0000320193-25-000079"


def _selected() -> SelectedPackage:
    return SelectedPackage(
        filename="2025_10_notes.zip",
        path=Path("/var/dera/packages/monthly/2025_10_notes.zip"),
        cadence="monthly",
        period="2025-10",
        sha256="a" * 64,
        size_bytes=97_554_203,
        accessions=(ACCESSION,),
        reason="sub.tsv lists it; a filing belongs to the period it was SUBMITTED in",
    )


def _fact() -> NormalizedFact:
    return NormalizedFact(
        accession=ACCESSION,
        cik="0000320193",
        taxonomy="us-gaap",
        namespace="http://fasb.org/us-gaap/2025",
        concept="Revenues",
        value_as_filed="100.0000",
        value_numeric=Decimal("100.0000"),
        unit="USD",
        scale=1,
        sign=1,
        period_type="duration",
        period_start=date(2024, 10, 1),
        period_end=date(2025, 9, 30),
        instant_date=None,
        duration_days=365,
        duration_months=12,
        source_row_id="key",
    )


def _result() -> LoadResult:
    read = ReadResult(
        rows_matched=3,
        facts=[_fact()],
        rejections=[Rejection("k", "Assets", ("value_present: empty",))],
        duplicate_keys=["dupe"],
        member_rows={"num.tsv": 1_680_427, "sub.tsv": 7_098},
    )
    return LoadResult(
        package="2025_10_notes.zip",
        package_sha256="a" * 64,
        period="2025-10",
        accession=ACCESSION,
        read=read,
        rows_inserted=1,
        rows_already_present=0,
        rows_in_database=1,
        database_value_total=Decimal("100.000000"),
        started_at="2026-08-02T02:00:00+00:00",
        completed_at="2026-08-02T02:00:30+00:00",
        state="COMPLETE",
    )


def test_the_selection_report_says_why_this_package_was_chosen() -> None:
    """A package chosen without a recorded reason cannot be audited later."""
    text = selection_report(_selected(), ACCESSION)
    assert "2025_10_notes.zip" in text
    assert "SUBMITTED" in text
    assert "a" * 64 in text


def test_the_load_report_shows_both_the_source_and_database_totals() -> None:
    text = load_report(_result())
    assert "matched in num.tsv" in text and "3" in text
    assert "accepted" in text
    assert "inserted this run" in text
    assert "100.0000" in text
    assert "100.000000" in text


def test_the_load_report_counts_rejections_by_rule() -> None:
    """A rejection that is not reported is a row silently dropped from a financial record."""
    text = load_report(_result())
    assert "rejections by rule" in text
    assert "value_present" in text


def test_the_load_report_states_the_elapsed_time() -> None:
    assert "30.0 s" in load_report(_result())


def test_a_passing_reconciliation_reports_reconciled() -> None:
    report = Reconciliation(
        accession=ACCESSION,
        package="2025_10_notes.zip",
        checks=[Check("rows_match", "5", "5", True, "detail")],
    )
    text = reconciliation_report(report)
    assert "[PASS] rows_match" in text
    assert "RECONCILED" in text
    assert "MISMATCH" not in text


def test_a_failing_reconciliation_names_the_failure_and_never_reads_as_success() -> None:
    """The failure mode this guards: a report that ends with a reassuring word after a failed check."""
    report = Reconciliation(
        accession=ACCESSION,
        package="2025_10_notes.zip",
        checks=[
            Check("rows_match", "967", "900", False, "a short load"),
            Check("keys_unique", "900", "900", True, ""),
        ],
    )
    text = reconciliation_report(report)
    assert "[FAIL] rows_match" in text
    assert "expected 967" in text and "actual   900" in text
    assert "MISMATCH: 1 check(s) failed" in text
    assert not text.rstrip().endswith("RECONCILED")


def test_the_full_report_contains_all_three_sections() -> None:
    report = Reconciliation(ACCESSION, "2025_10_notes.zip", [Check("c", "1", "1", True)])
    text = full_report(_selected(), _result(), report)
    assert "DERA PACKAGE SELECTED" in text
    assert "DERA FACT LOAD" in text
    assert "RECONCILIATION" in text


def test_the_report_emits_no_json_or_markdown() -> None:
    """LLM-SERIALIZATION-INVARIANT, applied defensively.

    An operational artifact is exactly the kind of text that later gets pasted somewhere it should
    not be. rules.md and ADR-0013 prohibit JSON and Markdown across the model boundary in both
    directions, so the report is plain text by construction.
    """
    report = Reconciliation(ACCESSION, "2025_10_notes.zip", [Check("c", "1", "1", True)])
    text = full_report(_selected(), _result(), report)
    assert "```" not in text
    assert not text.lstrip().startswith("{")
    assert "| ---" not in text
