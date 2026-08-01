# Immutable Fact Lake

IMPLEMENTATION STATUS: PLANNED (Phase 3)
OWNER PACKAGE: `packages/fact_lake`

## Invariant

A filed fact is never updated. A restatement appends a new observation. Selection of the
currently-preferred observation is computed separately and stored separately, so history is never
destroyed by a later opinion about it.

Enforced by a database trigger that rejects `UPDATE` on `value_as_filed`.

## Schema

```
xbrl_fact
  fact_id                 uuid primary key
  issuer_id               uuid not null references issuer
  cik                     text not null
  filing_id               uuid not null references filing
  accession               text not null
  form                    text not null
  filing_date             date not null
  report_date             date
  fiscal_year             integer
  fiscal_period           text            -- describes the FILING, not this fact
  taxonomy                text not null   -- us-gaap, dei, or an issuer namespace
  namespace               text not null
  concept                 text not null
  label                   text
  value_as_filed          text not null   -- APPEND ONLY, never updated
  value_numeric           numeric
  unit                    text not null
  scale                   integer not null default 1
  sign                    smallint not null default 1
  context_id              text
  period_start            date
  period_end              date
  instant_date            date
  duration_days           integer
  duration_months         integer         -- computed at ingest; charts filter on this
  dimensions              jsonb not null default '{}'
  segment                 text
  coregistrant            text
  statement_role          text
  disclosure_role         text
  source_dataset          text not null   -- dera_notes_2026_06, companyfacts, filing_xbrl
  source_row_id           text
  source_anchor           text
  filed_at                timestamptz not null
  restates_fact_id        uuid references xbrl_fact
  is_latest_selected      boolean not null default false
  validation_status       text not null default 'UNVALIDATED'
  created_at              timestamptz not null default now()
```

Indexes: `(cik, concept, period_end)`, `(filing_id)`, `(accession)`,
`(cik, concept, duration_months, period_end) where dimensions = '{}'` for the consolidated
series path, and a GIN index on `dimensions`.

## How `is_latest_selected` is computed without mutating history

It is a **derived flag**, recomputed by a pure function over the observation set. It never
implies an earlier fact was wrong or that its value changed.

```
for each group of (cik, concept, unit, period_start, period_end, dimensions):
    selected = argmax(observations, key=(filed_at, accession))
    set is_latest_selected = true  on selected
    set is_latest_selected = false on the rest
```

Recomputation is idempotent and can be re-run after any ingest. The as-originally-reported view
is `min(filed_at)` within the same grouping, which remains available forever.

## Why companyfacts is not the source

| Failure | Evidence |
|---|---|
| Drops dimensional facts | One Apple 10-K instance carries 57 occurrences of a revenue concept; the API returns 3 |
| Contains zero extension concepts | Apple declares 16 `aapl:` elements; extensions are 91.4 percent of distinct tags in a recent quarter |
| Mixes form types | 22 of 338 Apple `NetIncomeLoss` observations came from 8-K filings |
| `frame` is the restated view | Apple fiscal 2023 revenue appears in three 10-Ks; the `CY2023` frame sits on the 2025 filing |
| `fy` and `fp` describe the filing | One 10-Q carries `fy=2026, fp=Q2` on both the six-month and three-month facts, so grouping by `fp` double counts |
| 61 percent of observations carry no frame | Frame is a dedup hint, never a period filter |

It is retained as a freshness patch for filings newer than the latest DERA publication, and as a
reconciliation signal that flags disagreement for review.
