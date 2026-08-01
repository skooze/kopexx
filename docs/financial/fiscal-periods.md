# Fiscal Period Handling

IMPLEMENTATION STATUS: PLANNED (Sprint 6)
OWNER PACKAGE: `packages/fiscal`

Fiscal period handling is where charts silently go wrong. Every rule here exists because a naive
implementation produces a plausible-looking chart that is incorrect.

## Definitions the product must fix

The dashboard offers current year, previous year, five years, ten years, and all history. "Year"
is ambiguous for an issuer whose fiscal year is not the calendar year, so the product fixes these
meanings.

| Term | Definition |
|---|---|
| Fiscal year | The issuer's own annual period, ending on `fiscal_year_end` |
| Calendar year | January 1 to December 31 |
| Filing year | The year in which a document was filed, never used for chart alignment |
| Report period | The period a document covers, which is what charts use |
| **Current year** | The issuer's most recent fiscal year for which any 10-K or 10-Q exists |
| **Previous year** | The fiscal year immediately preceding current year |
| **Five years** | Current year and the four preceding fiscal years, inclusive |
| **Ten years** | Current year and the nine preceding fiscal years, inclusive |
| **All history** | Every fiscal period with at least one filed observation |

Current year may be **partial**. Apple's fiscal 2026 contains three filed quarters and no annual
report until the 10-K lands. The dashboard labels a partial year as partial rather than plotting
it as though it were complete.

## Q4 does not exist as a filing

There is no fourth-quarter 10-Q. In one DERA quarter, 1,003 10-Q filings split across Q1, Q2, and
Q3, with zero Q4. Filtering on filed quarters yields a quarterly chart with a hole every fourth
bar.

```
Q4 = FY - Q1 - Q2 - Q3
```

Every derived Q4 is flagged `derived = true` and carries the identifiers of its four inputs. When
any input is missing, Q4 is null rather than approximated.

## Cumulative year-to-date facts

Cash-flow and some income-statement facts are cumulative. One Apple filing carries roughly 28
three-month, 28 six-month, 30 nine-month, and 48 twelve-month observations under one concept.

```
discrete_quarter(n) = ytd(n) - ytd(n-1)   for n in (2, 3)
discrete_quarter(1) = ytd(1)
discrete_quarter(4) = annual - ytd(3)
```

Every observation stores `duration_months`, computed at ingest. Charts filter on it. Rendering a
cumulative fact as though it were a discrete quarter is the single most common way a cash-flow
chart lies.

## 52 and 53-week fiscal years

Retailers and some technology issuers use a 52/53-week calendar. Apple's fiscal 2017 and fiscal
2023 are 371 days; the surrounding years are 364.

Apple's fiscal 2023 revenue of 383.285 billion against fiscal 2022's 394.328 billion is a real
decline **and** a week-count artifact simultaneously. Both must be visible.

```
is_53_week = (period_end - period_start).days > 368
```

A year-over-year comparison spanning a 53-week year emits a comparability warning naming the
extra week. It is never silently normalized, because normalizing invents a figure the company
never reported.

## Fiscal-year-end changes and transition reports

`fiscalYearEnd` is not a stable issuer attribute. Eight `10-KT` transition reports appeared in a
single recent quarter. Storing the year end only on the issuer mis-stamps every historical period
for an issuer that changed it.

`fiscal_year_end` is therefore stored **per filing**, and the issuer-level value is the most
recent observation only. A transition period is flagged, its length recorded, and it is excluded
from growth calculations while remaining visible in the series.

## Instant versus duration

Balance-sheet facts are instants. Income-statement and cash-flow facts are durations. A metric
definition declares which it expects, and resolution rejects the wrong kind rather than coercing
it.

## Restated comparatives

A later filing restates an earlier period. Both observations are retained. Selection prefers the
most recently filed value for the current view, and the as-originally-reported view is available.
The chart says which view it is showing.

## Duplicate observations

The same period may appear in several filings. Deduplication is on
`(cik, concept, period_start, period_end, unit, dimensions)` selecting by most recent `filed`.
Deduplicating without `dimensions` collapses segment data into consolidated totals.

## Pseudocode

```
def resolve_series(cik, metric, range_spec):
    periods = fiscal_periods_for(cik, range_spec)          # respects the issuer's calendar
    out = []
    for period in periods:
        facts = fact_lake.query(
            cik=cik,
            concepts=metric.accepted_concepts,
            period_start=period.start,
            period_end=period.end,
            duration_months=metric.allowed_duration_months,
            unit=metric.allowed_units,
            dimensions=NONE,                               # consolidated only
        )
        if not facts:
            if period.is_q4 and metric.period_type == DURATION:
                value = derive_q4(cik, metric, period.fiscal_year)   # may be None
                out.append(Observation(period, value, derived=True))
            else:
                out.append(Observation(period, None, missing=True))
            continue
        chosen = select(facts, by=(MAX_FILED, MIN_PRIORITY_RANK))
        out.append(Observation(period, chosen.value, fact_id=chosen.id))
    annotate_comparability(out)     # 53-week weeks, transition periods, restatements, mixed ranks
    return out
```

## Tests

```
test_current_year_respects_non_calendar_fiscal_year
test_current_year_may_be_partial
test_q4_is_derived_not_missing
test_q4_is_null_when_an_input_is_missing
test_ytd_facts_are_converted_to_discrete_quarters
test_no_series_mixes_duration_buckets
test_53_week_year_emits_comparability_warning
test_transition_report_excluded_from_growth
test_fiscal_year_end_change_does_not_restamp_history
test_instant_metric_rejects_duration_fact
test_restatement_retains_both_observations
test_dedup_preserves_dimensional_facts
```
