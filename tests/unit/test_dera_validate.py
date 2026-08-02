"""Domain validation of normalized DERA facts.

Each rule mirrors a database constraint. The test that matters most is the anti-vacuity one: a
validator that accepts everything passes every positive test ever written for it.
"""

from __future__ import annotations

import dataclasses
from datetime import date
from decimal import Decimal

import pytest

from packages.dera_notes.normalize import NormalizedFact
from packages.dera_notes.validate import is_loadable, violations


def _fact(**overrides: object) -> NormalizedFact:
    base = NormalizedFact(
        accession="0000320193-25-000079",
        cik="0000320193",
        taxonomy="us-gaap",
        namespace="http://fasb.org/us-gaap/2025",
        concept="Revenues",
        value_as_filed="416161000000.0000",
        value_numeric=Decimal("416161000000.0000"),
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
    return dataclasses.replace(base, **overrides)  # type: ignore[arg-type]


def _rules(fact: NormalizedFact) -> set[str]:
    return {v.rule for v in violations(fact)}


def test_a_well_formed_fact_is_loadable() -> None:
    assert is_loadable(_fact())
    assert violations(_fact()) == []


def test_an_undashed_accession_is_rejected() -> None:
    assert "accession_is_dashed_form" in _rules(_fact(accession="000032019325000079"))


def test_an_unpadded_cik_is_rejected() -> None:
    assert "cik_is_ten_digits" in _rules(_fact(cik="320193"))


def test_a_duration_without_both_boundaries_is_rejected() -> None:
    """The database check constraint, caught in Python so one bad row does not abort the batch."""
    assert "period_fields_match_period_type" in _rules(_fact(period_end=None))
    assert "period_fields_match_period_type" in _rules(_fact(period_start=None))


def test_an_instant_without_a_date_is_rejected() -> None:
    assert "period_fields_match_period_type" in _rules(
        _fact(period_type="instant", period_start=None, period_end=None, instant_date=None)
    )


def test_an_instant_with_a_date_is_accepted() -> None:
    assert is_loadable(
        _fact(
            period_type="instant",
            period_start=None,
            period_end=None,
            instant_date=date(2025, 9, 30),
            duration_days=None,
            duration_months=None,
        )
    )


@pytest.mark.parametrize("sign", [0, 2, -2])
def test_a_sign_other_than_plus_or_minus_one_is_rejected(sign: int) -> None:
    assert "sign_is_plus_or_minus_one" in _rules(_fact(sign=sign))


def test_an_empty_unit_is_rejected() -> None:
    assert "unit_present" in _rules(_fact(unit=""))


def test_a_unit_too_long_for_its_column_is_rejected_not_truncated() -> None:
    assert "unit_fits_column" in _rules(_fact(unit="U" * 41))


def test_an_empty_filed_value_is_rejected() -> None:
    assert "value_present" in _rules(_fact(value_as_filed=""))


def test_a_value_beyond_numeric_38_6_is_rejected_rather_than_aborting_the_batch() -> None:
    """PostgreSQL raises on integer overflow. One such row would take the whole load down."""
    assert "value_fits_numeric_38_6" in _rules(_fact(value_numeric=Decimal(10) ** 33))


def test_a_value_at_the_boundary_is_accepted() -> None:
    assert is_loadable(_fact(value_numeric=Decimal(10) ** 31))


def test_a_non_finite_value_is_rejected() -> None:
    assert "value_is_finite" in _rules(_fact(value_numeric=Decimal("NaN")))


def test_a_missing_natural_key_is_rejected_because_idempotency_depends_on_it() -> None:
    assert "natural_key_present" in _rules(_fact(source_row_id=""))


def test_a_non_numeric_value_is_allowed_because_the_filed_string_survives() -> None:
    """Some DERA values are not numbers. The filed string is authoritative; the numeric view is a
    derived convenience and its absence is not a defect."""
    assert is_loadable(_fact(value_as_filed="see accompanying notes", value_numeric=None))


def test_the_validator_is_not_vacuous() -> None:
    """A validator that never rejects would pass every positive test above.

    This asserts it rejects a fact broken in several ways at once, and reports all of them rather
    than stopping at the first.
    """
    broken = _fact(accession="nonsense", cik="1", unit="", sign=7, source_row_id="")
    found = _rules(broken)
    assert len(found) >= 5, f"expected several independent violations, got {found}"
