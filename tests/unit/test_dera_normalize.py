"""Mapping DERA rows to fact-lake values."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from packages.dera_notes.normalize import (
    minus_months,
    natural_key,
    normalize_fact,
    split_version,
)

CIK = "0000320193"
ACCESSION = "0000320193-25-000079"


def _row(**overrides: str) -> dict[str, str]:
    row = {
        "adsh": ACCESSION,
        "tag": "Revenues",
        "version": "us-gaap/2025",
        "ddate": "20250930",
        "qtrs": "4",
        "uom": "USD",
        "dimh": "0x00000000",
        "iprx": "0",
        "value": "416161000000.0000",
        "coreg": "",
    }
    row.update(overrides)
    return row


# --- version splitting ----------------------------------------------------------------------


def test_standard_taxonomy_splits_into_family_and_namespace() -> None:
    assert split_version("us-gaap/2025", ACCESSION) == (
        "us-gaap",
        "http://fasb.org/us-gaap/2025",
    )


def test_an_accession_in_the_version_field_marks_an_extension_concept() -> None:
    """91.4 percent of distinct tags in the corpus are issuer extensions.

    An extension named `Revenues` is not the us-gaap `Revenues`, and conflating them would merge
    two different companies' private concepts into one series.
    """
    taxonomy, namespace = split_version("0000320193-25-000079", ACCESSION)
    assert taxonomy == "extension"
    assert ACCESSION in namespace


def test_a_missing_version_is_treated_as_an_extension_not_as_us_gaap() -> None:
    taxonomy, _ = split_version(None, ACCESSION)
    assert taxonomy == "extension", "defaulting to a standard taxonomy would fabricate provenance"


# --- calendar arithmetic --------------------------------------------------------------------


def test_month_subtraction_clamps_to_a_valid_day() -> None:
    """31 March minus one month is 28 or 29 February, never an invalid 31 February."""
    assert minus_months(date(2025, 3, 31), 1) == date(2025, 2, 28)
    assert minus_months(date(2024, 3, 31), 1) == date(2024, 2, 29)


def test_month_subtraction_crosses_year_boundaries() -> None:
    assert minus_months(date(2025, 1, 15), 3) == date(2024, 10, 15)
    assert minus_months(date(2025, 9, 30), 12) == date(2024, 9, 30)


def test_month_subtraction_does_not_drift_across_a_long_series() -> None:
    """Thirty-day arithmetic would lose five days a year and compound silently."""
    assert minus_months(date(2025, 9, 30), 120) == date(2015, 9, 30)


# --- period mapping -------------------------------------------------------------------------


def test_qtrs_zero_is_an_instant() -> None:
    fact = normalize_fact(_row(qtrs="0"), cik=CIK)
    assert fact is not None
    assert fact.period_type == "instant"
    assert fact.instant_date == date(2025, 9, 30)
    assert fact.period_start is None and fact.period_end is None
    assert fact.duration_months is None


def test_qtrs_four_is_a_twelve_month_duration() -> None:
    fact = normalize_fact(_row(qtrs="4"), cik=CIK)
    assert fact is not None
    assert fact.period_type == "duration"
    assert fact.duration_months == 12
    assert fact.period_end == date(2025, 9, 30)
    assert fact.period_start == date(2024, 10, 1)
    assert fact.instant_date is None


def test_a_duration_start_is_derived_because_dera_does_not_publish_one() -> None:
    """DERA gives an end date and a quarter count, never a start.

    The derived start is calendar-exact against DERA's own month-end convention, which is itself
    a rounding of the filed context. That is why every row this loader writes stays UNVALIDATED
    until the XBRL instance supplies the filed boundaries.
    """
    fact = normalize_fact(_row(qtrs="1", ddate="20250630"), cik=CIK)
    assert fact is not None
    assert fact.period_start == date(2025, 4, 1)
    assert fact.period_end == date(2025, 6, 30)
    assert fact.duration_months == 3
    assert fact.duration_days == 91


def test_an_unparseable_ddate_leaves_the_period_incomplete_for_validation_to_reject() -> None:
    """Normalization does not invent a date. Validation rejects the row and counts it."""
    fact = normalize_fact(_row(ddate="garbage"), cik=CIK)
    assert fact is not None
    assert fact.period_end is None and fact.period_start is None


# --- values and identity --------------------------------------------------------------------


def test_the_filed_string_is_preserved_beside_the_numeric_view() -> None:
    fact = normalize_fact(_row(value="416161000000.0000"), cik=CIK)
    assert fact is not None
    assert fact.value_as_filed == "416161000000.0000"
    assert fact.value_numeric == Decimal("416161000000.0000")


def test_a_row_without_a_value_is_not_a_fact() -> None:
    """DERA emits label rows whose value is genuinely absent. Not a defect, just not a fact."""
    assert normalize_fact(_row(value=""), cik=CIK) is None


@pytest.mark.parametrize("field", ["adsh", "tag"])
def test_a_row_missing_an_identity_field_is_not_a_fact(field: str) -> None:
    assert normalize_fact(_row(**{field: ""}), cik=CIK) is None


def test_scale_and_sign_are_recorded_explicitly_rather_than_inferred() -> None:
    """A value without a recorded unit, scale, and sign is not interpretable later."""
    fact = normalize_fact(_row(), cik=CIK)
    assert fact is not None
    assert fact.scale == 1
    assert fact.sign == 1
    assert fact.unit == "USD"


def test_the_natural_key_is_stable_across_reads() -> None:
    """Idempotency depends entirely on this being a pure function of the row."""
    assert natural_key(_row(), ACCESSION) == natural_key(_row(), ACCESSION)


def test_the_natural_key_separates_dimensional_variants() -> None:
    """Without dimh in the key, every dimensional variant of a concept collapses into one row."""
    base = natural_key(_row(dimh="0x00000000"), ACCESSION)
    other = natural_key(_row(dimh="0x0000d669546b5e8518d9f602e93b8b5a"), ACCESSION)
    assert base != other


def test_the_natural_key_separates_dera_duplicate_facts() -> None:
    """iprx exists precisely because DERA emits rows that collide on every other key field."""
    assert natural_key(_row(iprx="0"), ACCESSION) != natural_key(_row(iprx="1"), ACCESSION)


def test_dimensions_default_to_empty_which_means_consolidated() -> None:
    fact = normalize_fact(_row(), cik=CIK)
    assert fact is not None
    assert fact.dimensions == {}
    assert fact.is_consolidated is True


def test_a_dimensional_fact_is_not_consolidated() -> None:
    fact = normalize_fact(_row(), cik=CIK, dimensions={"EquityComponents": "RetainedEarnings"})
    assert fact is not None
    assert fact.is_consolidated is False


def test_the_cik_is_padded_to_ten_digits() -> None:
    fact = normalize_fact(_row(), cik="320193")
    assert fact is not None
    assert fact.cik == "0000320193"


def test_an_undashed_accession_is_normalized() -> None:
    fact = normalize_fact(_row(adsh="000032019325000079"), cik=CIK)
    assert fact is not None
    assert fact.accession == ACCESSION


def test_the_derived_start_is_not_a_day_short_when_the_end_month_is_shorter() -> None:
    """The defect this guards: 30 June minus three months clamps to 30 March, because March has
    31 days. Adding a day then gives 31 March and the quarter starts a day short.

    It is invisible on Apple's annual periods, which end 30 September and land on 1 October
    either way, and wrong on every quarter ending in a 30-day month. It was caught by a unit test
    after the first real load had already written the wrong value.
    """
    fact = normalize_fact(_row(qtrs="1", ddate="20250630"), cik=CIK)
    assert fact is not None
    assert fact.period_start == date(2025, 4, 1)

    september = normalize_fact(_row(qtrs="1", ddate="20250930"), cik=CIK)
    assert september is not None
    assert september.period_start == date(2025, 7, 1)


def test_derived_starts_cover_every_quarter_end_without_gap_or_overlap() -> None:
    """Consecutive quarters must tile the year exactly: no shared day, no missing day."""
    ends = ["20241231", "20250331", "20250630", "20250930"]
    periods = []
    for ddate in ends:
        fact = normalize_fact(_row(qtrs="1", ddate=ddate), cik=CIK)
        assert fact is not None
        periods.append((fact.period_start, fact.period_end))

    for (_, earlier_end), (later_start, _) in zip(periods, periods[1:], strict=False):
        assert earlier_end is not None and later_start is not None
        assert (later_start - earlier_end).days == 1, "quarters must abut exactly"


def test_an_annual_period_derives_the_same_start_either_way() -> None:
    fact = normalize_fact(_row(qtrs="4", ddate="20250930"), cik=CIK)
    assert fact is not None
    assert fact.period_start == date(2024, 10, 1)
    assert fact.duration_days == 365
