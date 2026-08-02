"""Turn DERA num.tsv rows into domain values for the fact lake.

Mapping decisions live here so the loader stays about transactions and the parser stays about
bytes.

DERA-INVARIANT: `ddate` is rounded to the nearest month end and `qtrs` is a whole number of
quarters. DERA publishes the residuals separately as `datp` and `durp`. So a DERA period boundary
is a normalized approximation, not the filed context. That matters for a 52/53-week filer: Apple's
FY2025 ended 2025-09-27 and DERA records 2025-09-30.

The consequence is recorded rather than hidden. `period_end` and `instant_date` hold DERA's value
verbatim, `period_start` is derived by calendar arithmetic because DERA does not publish it at
all, and `xbrl_fact.validation_status` stays `UNVALIDATED` for every row this loader writes. The
exact context boundaries live in the XBRL instance document, which the fact lake reads in
Sprint 6; because `xbrl_fact` is append-only, that later and better observation supersedes these
rows through the ordinary restatement path instead of overwriting them.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from packages.sec_identity import accession_dashed, cik_padded

from .tsv import as_date, as_decimal, as_int, clean

# num.tsv's documented primary key. Every component is needed: `dimh` separates dimensional
# variants of one concept, and `iprx` separates facts that would otherwise collide even so.
NATURAL_KEY_FIELDS = ("adsh", "tag", "version", "ddate", "qtrs", "uom", "dimh", "iprx", "coreg")

# DERA num values are absolute in the stated unit. `scale` is a multiplier in this schema, so 1 is
# the identity and applying no scaling is recorded explicitly rather than left to be inferred.
NO_SCALING = 1

# DERA carries the sign inside `value`. A separate sign flip is never implied.
NO_SIGN_FLIP = 1


@dataclass(frozen=True)
class NormalizedFact:
    """One num.tsv row, mapped to the columns `xbrl_fact` needs."""

    accession: str
    cik: str
    taxonomy: str
    namespace: str
    concept: str
    value_as_filed: str
    value_numeric: Decimal | None
    unit: str
    scale: int
    sign: int
    period_type: str
    period_start: date | None
    period_end: date | None
    instant_date: date | None
    duration_days: int | None
    duration_months: int | None
    dimensions: dict[str, str] = field(default_factory=dict)
    # DERA's own segment expression, verbatim. `dimensions` is the parsed view; the dimension
    # HASH is not stored here — it is already carried inside source_row_id, which is the natural
    # key, so the join back to dim.tsv survives without a column that means something else.
    segment: str | None = None
    coregistrant: str | None = None
    source_row_id: str = ""

    @property
    def is_consolidated(self) -> bool:
        """No dimensions. This is the series the dashboard charts."""
        return not self.dimensions


def minus_months(anchor: date, months: int) -> date:
    """Subtract whole calendar months, clamping to the last valid day of the target month.

    Naive day arithmetic would turn 31 March minus one month into an invalid 31 February; naive
    30-day arithmetic would drift by days per quarter across a multi-year series.
    """
    total = anchor.year * 12 + (anchor.month - 1) - months
    year, month = divmod(total, 12)
    month += 1
    day = min(anchor.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def is_month_end(value: date) -> bool:
    return value.day == calendar.monthrange(value.year, value.month)[1]


def derive_period_start(end: date, months: int) -> date:
    """The first day of a period of `months` whole months ending on `end`.

    DERA rounds `ddate` to a month end, so the common path is the first branch: a period ending on
    the last day of a month starts on the FIRST day of the month `months - 1` earlier.

    Subtracting whole months from the end date and adding a day looks equivalent and is not. A
    quarter ending 30 June, minus three months, clamps to 30 March because March has 31 days;
    adding a day gives 31 March, and the period starts a day short. The error appears only when
    the end month is shorter than the month `months` back, so it is invisible on annual periods
    ending 30 September and wrong on quarterly ones.
    """
    if is_month_end(end):
        total = end.year * 12 + (end.month - 1) - (months - 1)
        year, month = divmod(total, 12)
        return date(year, month + 1, 1)
    return minus_months(end, months) + timedelta(days=1)


def split_version(version: str | None, accession: str) -> tuple[str, str]:
    """DERA `version` is either a standard taxonomy like `us-gaap/2025`, or the filer's accession.

    An accession in that field marks an issuer extension concept. 91.4 percent of distinct tags in
    the corpus are extensions, so this is the common case rather than the exception, and an
    extension concept must never be conflated with a standard one that happens to share a name.
    """
    text = clean(version) or ""
    if "/" in text:
        family, year = text.split("/", 1)
        return family, f"http://fasb.org/{family}/{year}" if family == "us-gaap" else text
    return "extension", f"urn:sec:extension:{accession}"


def natural_key(row: dict[str, str], accession: str) -> str:
    """The stable identity of a DERA fact row.

    Idempotency depends entirely on this. It is built from the accession in canonical dashed form
    plus every remaining key field verbatim, so re-reading the same package produces byte-identical
    keys and inserts nothing the second time.
    """
    parts = [accession]
    parts.extend((row.get(name) or "").strip() for name in NATURAL_KEY_FIELDS[1:])
    return "|".join(parts)


def normalize_fact(
    row: dict[str, str],
    *,
    cik: str,
    dimensions: dict[str, str] | None = None,
    segment: str | None = None,
) -> NormalizedFact | None:
    """Map one num.tsv row. Returns None when the row cannot be a fact at all.

    A row without a value is not a defect worth reporting: DERA emits rows whose value is genuinely
    absent for the period. It simply is not a fact for the lake.
    """
    accession = clean(row.get("adsh"))
    concept = clean(row.get("tag"))
    raw_value = clean(row.get("value"))
    if not accession or not concept or raw_value is None:
        return None

    accession = accession_dashed(accession)
    taxonomy, namespace = split_version(row.get("version"), accession)

    quarters = as_int(row.get("qtrs")) or 0
    boundary = as_date(row.get("ddate"))

    if quarters == 0:
        period_type = "instant"
        instant, start, end = boundary, None, None
        months = days = None
    else:
        period_type = "duration"
        instant = None
        months = quarters * 3
        end = boundary
        start = derive_period_start(end, months) if end is not None else None
        days = (end - start).days + 1 if end is not None and start is not None else None

    return NormalizedFact(
        accession=accession,
        cik=cik_padded(cik),
        taxonomy=taxonomy,
        namespace=namespace,
        concept=concept,
        value_as_filed=raw_value,
        value_numeric=as_decimal(raw_value),
        unit=clean(row.get("uom")) or "pure",
        scale=NO_SCALING,
        sign=NO_SIGN_FLIP,
        period_type=period_type,
        period_start=start,
        period_end=end,
        instant_date=instant,
        duration_days=days,
        duration_months=months,
        dimensions=dict(dimensions or {}),
        segment=clean(segment),
        coregistrant=clean(row.get("coreg")),
        source_row_id=natural_key(row, accession),
    )
