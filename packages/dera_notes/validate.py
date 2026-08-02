"""Domain validation for normalized DERA facts.

Every rule here mirrors a constraint the database would enforce anyway. Checking in Python first
is not redundancy: a constraint violation inside a batch INSERT aborts the whole transaction and
reports one row, so a single malformed fact would take the entire load down and say almost nothing
about why. Validating first turns that into a counted, named rejection with the offending row
identified, and lets the rest of the package load.

FAIL LOUD, NOT SILENT. A rejected row is never dropped quietly. `LoadResult` carries the count and
the reasons, and reconciliation asserts accepted + rejected equals what was read.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal

from .normalize import NormalizedFact

ACCESSION_PATTERN = re.compile(r"^[0-9]{10}-[0-9]{2}-[0-9]{6}$")
CIK_PATTERN = re.compile(r"^[0-9]{10}$")

# xbrl_fact.value_numeric is NUMERIC(38, 6): 32 integer digits and 6 fractional. PostgreSQL rounds
# excess fractional digits silently but RAISES on integer overflow, so the magnitude is checked and
# the rounding is accepted deliberately.
MAX_MAGNITUDE = Decimal(10) ** 32

# Column widths that would truncate rather than raise if the database were more forgiving.
MAX_UNIT = 40
MAX_TAXONOMY = 40


@dataclass(frozen=True)
class Violation:
    """One broken rule, named after the constraint it corresponds to."""

    rule: str
    detail: str

    def __str__(self) -> str:
        return f"{self.rule}: {self.detail}"


def violations(fact: NormalizedFact) -> list[Violation]:
    """Every rule this fact breaks. An empty list means it is loadable."""
    found: list[Violation] = []

    if not ACCESSION_PATTERN.match(fact.accession):
        found.append(Violation("accession_is_dashed_form", fact.accession))

    if not CIK_PATTERN.match(fact.cik):
        found.append(Violation("cik_is_ten_digits", fact.cik))

    if fact.period_type not in ("instant", "duration"):
        found.append(Violation("period_type_is_known", fact.period_type))

    # The database check constraint, restated. A duration missing either boundary and an instant
    # missing its date are both rejected here rather than aborting the batch.
    if fact.period_type == "instant" and fact.instant_date is None:
        found.append(
            Violation(
                "period_fields_match_period_type", "instant without a date (unparseable ddate)"
            )
        )
    if fact.period_type == "duration" and (fact.period_start is None or fact.period_end is None):
        found.append(
            Violation(
                "period_fields_match_period_type",
                "duration without both boundaries (unparseable ddate)",
            )
        )

    if fact.sign not in (-1, 1):
        found.append(Violation("sign_is_plus_or_minus_one", str(fact.sign)))

    if not fact.unit:
        found.append(Violation("unit_present", "empty"))
    elif len(fact.unit) > MAX_UNIT:
        found.append(Violation("unit_fits_column", f"{len(fact.unit)} characters"))

    if len(fact.taxonomy) > MAX_TAXONOMY:
        found.append(Violation("taxonomy_fits_column", f"{len(fact.taxonomy)} characters"))

    if not fact.value_as_filed:
        found.append(Violation("value_present", "empty"))

    if fact.value_numeric is not None:
        if not fact.value_numeric.is_finite():
            found.append(Violation("value_is_finite", str(fact.value_numeric)))
        elif abs(fact.value_numeric) >= MAX_MAGNITUDE:
            found.append(Violation("value_fits_numeric_38_6", f"|{fact.value_numeric}| >= 1e32"))

    if not fact.source_row_id:
        found.append(Violation("natural_key_present", "empty; idempotency would be impossible"))

    return found


def is_loadable(fact: NormalizedFact) -> bool:
    return not violations(fact)


@dataclass
class Rejection:
    """A row that was read and deliberately not loaded."""

    source_row_id: str
    concept: str
    reasons: tuple[str, ...]

    @classmethod
    def create(cls, fact: NormalizedFact, found: list[Violation]) -> Rejection:
        return cls(
            source_row_id=fact.source_row_id,
            concept=fact.concept,
            reasons=tuple(str(v) for v in found),
        )
