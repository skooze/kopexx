# Data Dictionary

IMPLEMENTATION STATUS: IMPLEMENTED (Sprint 2).

24 domain tables. Models in `packages/persistence/models.py`; migration in
`migrations/versions/0001_initial_control_plane_schema.py`.

## Conventions

| Convention | Rule |
|---|---|
| Primary keys | `uuid`, generated application-side so a record has identity before insert |
| Timestamps | `timestamptz`, always UTC |
| Identifiers from SEC | `text`, never integer. `0000320193` is not the number 320193 |
| Money | `numeric`, never float. Never a currency-scaled integer without a `scale` column |
| Enums | `text` with a check constraint, so a new value is a migration not a deploy |
| Soft delete | Not used. Supersession columns instead |
| `created_at` | On every table |

## Identifier formats

| Identifier | Format | Example | Notes |
|---|---|---|---|
| CIK | 10-digit zero-padded text | `"0000320193"` | Unpadded for Archives URLs only |
| Accession | dashed text | `"0000320193-25-000079"` | Undashed only as a folder segment |
| Ticker | uppercase text | `"AAPL"` | Never unique on its own; temporal |
| Footnote id | uuid | | |
| Source block id | text | `"debt-narrative-01"` | Stable within a filing; cited by the model |
| Dataset version | text | `"2026-08-01T04:38Z-r3"` | Names an immutable Parquet directory |

## Unit conventions

```
USD, USD_thousands, USD_millions, USD_billions, shares, percent, years, count, ratio
```

Unit and `scale` are stored separately and always together. A value without both is not
interpretable. A unit is never inferred at display time from magnitude.

## Period conventions

```
period_type      instant | duration
instant_date     set for instants, null for durations
period_start     null for instants
period_end       always set
duration_months  computed at ingest; charts filter on it
is_derived       true for a computed Q4
```

The database enforces this: `ck_xbrl_fact_period_fields_match_period_type` requires an
`instant_date` for an instant and both boundaries for a duration.

### Period fidelity depends on the source, and the source is recorded

`xbrl_fact.source_dataset` is not decoration. Period precision differs by source, and a chart that
mixed them without knowing would be quietly wrong.

**`source_dataset = 'dera_notes'` periods are normalized approximations.** DERA rounds `ddate` to
the nearest month end, states `qtrs` as a whole number of quarters, and publishes the residuals
separately as `datp` and `durp`. It publishes no period start at all, so `period_start` is
DERIVED: the first day of the month `duration_months - 1` before `period_end`.

The consequence is concrete. Apple's FY2025 ended 2025-09-27, a 52/53-week fiscal year end; DERA
records 2025-09-30, and the derived start is 2024-10-01 where the filed context begins 2024-09-29.
Days differ; the quarter does not.

Every row loaded this way carries `validation_status = 'UNVALIDATED'`, because nothing has
validated it and the exact filed boundaries live in the XBRL instance document. When the instance
is parsed, its facts are APPENDED — `xbrl_fact` is append-only — and supersede the DERA
observations through the ordinary restatement path. The DERA rows are never edited in place; the
trigger would reject it.

**Do not use a DERA `period_start` as a filed date.** Use it to bucket a period. Anything that
must cite an exact boundary reads from a source that publishes one.

## Footnote extraction conventions — Sprint 4

```
canonical_footnote.sequence          filed order, 1..N; the idempotency key
canonical_footnote.normalized_number displayed note number, NULL when the filing shows none
footnote_source_block.external_id    the renderer position, R9, matching its own file naming
footnote_source_block.block_type     parent_narrative | details | tables | policies
footnote_source_block.footnote_id    NULL means ORPHAN, which is a reportable state, not an error
filing_section.section_type          item_disclosure for an excluded Regulation S-K item
footnote_table.footnote_id           the owning note; NULL for every non-footnote kind
footnote_table.ownership_kind        CANONICAL_FOOTNOTE | EXCLUDED_FILING_SECTION
                                     | FINANCIAL_STATEMENT | OTHER_FILING_REPORT | UNRESOLVED
footnote_table.ownership_evidence    tagged concept, candidate roles, deterministic reason
```

`sequence` rather than `normalized_number` is the upsert key. `normalized_number` is nullable, and
a NULL never conflicts in a unique constraint, so two unnumbered notes would duplicate silently.

`ownership_kind` and `footnote_id` must agree, enforced by a check constraint: a NULL
`footnote_id` alone cannot distinguish a statement from an excluded disclosure from an unresolved
table, and only the last is a defect.

Numeric text inside `footnote_table.cells` is the string the filer wrote — `(1,234)`, `$`, commas
intact. It is never converted to a number at extraction time.

## State enums

Filing processing: `DISCOVERED`, `QUEUED`, `DOWNLOADING`, `DOWNLOADED`, `PARSING`, `PARSED`,
`EXTRACTING_FACTS`, `FACTS_EXTRACTED`, `EXTRACTING_SECTIONS`, `SECTIONS_EXTRACTED`,
`EXTRACTING_FOOTNOTES`, `FOOTNOTES_EXTRACTED`, `GROUPING_FOOTNOTES`, `FOOTNOTES_GROUPED`,
`VALIDATING_FOOTNOTES`, `FOOTNOTES_VALIDATED`, `SUMMARIZING`, `SUMMARIES_GENERATED`,
`VALIDATING_SUMMARIES`, `CALCULATING_METRICS`, `PUBLISHING`, `COMPLETE`, `PARTIAL`, `FAILED`,
`REQUIRES_REVIEW`.

Footnote status: `COMPLETE`, `PARTIAL`, `REQUIRES_REVIEW`, `FAILED`.

Summary validation: the eleven states in `docs/llm/summary-validation.md`.

Grouping method: `role_uri`, `toc_reconciliation`, `heading`, `presentation_hierarchy`,
`concept_overlap`, `title_similarity`, `filing_order`, `model_adjudication`, `human_review`.

Exclusion reason: `foreign_private_issuer_20f`, `fund_n_csr`, `bdc_specialized`, `shell`,
`never_filed`, `unresolved_identity`, `filing_history_unavailable`.

Analysis scope: `FOOTNOTE`, `FILING`, `TIMEFRAME`.

## Source types

```
footnote_narrative   footnote_policy      footnote_detail      footnote_table
filing_section       xbrl_fact            derived_metric       summary
```

Every citation names one of these plus an identifier, so a claim's provenance is typed.

## Tables

24 domain tables. Full column definitions in `packages/persistence/models.py` and the initial
migration.

### Counting the schema

Two methods, both useful, not interchangeable. They agree once `alembic_version` is accounted for.

| Object | Model metadata | Live catalog (`public`) |
|---|---|---|
| Tables | 24 | 24 domain, 25 including `alembic_version` |
| Explicit indexes | 37 | 37 |
| of which partial | 7 | 7 |
| Check constraints | 23 | 23 |
| Unique constraints | 19 | 19 |
| Foreign-key constraints | 29 | 29 |
| Primary-key constraints | 24 | 25 (`alembic_version` has one) |
| Indexes including constraint-backing | not modelled | 81 = 25 PK + 19 unique + 37 explicit |

*Model metadata* is `Base.metadata` — what the code declares. The structural tests assert against
it, and it is available with no database.

*Live catalog* is `pg_class`, `pg_constraint`, `pg_indexes` restricted to `public`. It is what
actually exists, including objects PostgreSQL creates on its own behalf. Migration verification
uses it.

Two traps when reading these numbers. SQLAlchemy reflection omits primary-key-backing indexes, so
`inspect().get_indexes()` sums to 56, not 81 — the difference is exactly the 25 PK indexes. And a
`pg_constraint` query without a schema filter picks up `cardinal_number_domain_check` and
`yes_or_no_check` from `information_schema`, reporting 25 check constraints where the application
has 23. Always filter on `nspname='public'`.
Summary of ownership:

| Table | Owns | Key invariant |
|---|---|---|
| `issuer` | Issuer identity | CIK unique |
| `issuer_former_name` | Name history | Needed because delisted issuers are renamed |
| `listing` | Ticker history | Unique on `(ticker, exchange, effective_start)`, never on ticker |
| `listing_observation` | Raw snapshots | Append only; never overwritten |
| `excluded_filer` | Exclusions | Reason always populated |
| `filing` | Filing metadata | Accession unique; carries `completeness_confidence` and `reconciliation_status`, the two completeness values that cannot be derived from child rows |
| `filing_document` | Acquired objects | Every row has a sha256 |
| `filing_section` | Item sections | Carries extraction strategy and confidence |
| `canonical_footnote` | Footnotes | Unique on `(filing_id, normalized_number)` |
| `footnote_source_block` | Source blocks | Parent nullable so orphans are visible; carries the per-attachment grouping audit (method, confidence, evidence, competing candidates, run id) |
| `footnote_table` | Tables | Structure preserved; original HTML retained |
| `xbrl_fact` | Filed facts | `value_as_filed` append-only, enforced by trigger |
| `metric_definition` | Curated mappings | Versioned; git commit recorded |
| `derived_metric` | Computed values | Records formula version and input fact ids |
| `footnote_summary` | Summaries | One active version per footnote, partial unique index |
| `processing_job` | Job state | Idempotency key unique |
| `analysis_session` | Deep Analysis scope | Immutable after creation |
| `analysis_message` | Turns | Carries citations and cost |
| `conversation_memory` | Structured memory | Only evidenced findings |
| `llm_invocation` | Model audit | Exact request and response URIs and hashes |
| `prompt_version` | Prompt registry | Content hash recorded |
| `dera_package` | DERA mirror ledger | Monthly rows retained after quarterly consolidation |
| `dataset_version` | Published Parquet pointer | Partial unique index: at most one current |
| `filing_amendment` | Amendment relationships | Amendment is never its own target |

### Enforcement highlights

    xbrl_fact               BEFORE UPDATE trigger rejects any change to a filed value, unit,
                            scale, concept, or period. Append a new observation instead.
    listing                 unique on (ticker, exchange, effective_start), never on ticker
    footnote_summary        partial unique index gives exactly one active version per footnote
    footnote_source_block   footnote_id nullable, with a partial index over orphans
    llm_invocation          check constraint restricts content format to plain_text or yaml
    dataset_version         partial unique index over is_current
    filing                  reconciliation_status constrained to RECONCILED | MISMATCH |
                            NOT_ATTEMPTED, so "no TOC found" is distinguishable from "reconciled"

### Derived, deliberately not stored

Eleven of the thirteen completeness counters in docs/footnotes/completeness.md are COUNT()
queries over canonical_footnote, footnote_source_block, footnote_table, and footnote_summary.
They are not columns. A stored copy of a derivable count is a second source of truth that goes
stale the moment a summary is superseded or a block is re-attached.

## Retention

Filing data and facts: indefinite; public data with provenance value.
Summaries: indefinite, including superseded versions.
Model invocation records: indefinite; principal anonymized on user deletion rather than the row
removed, so cost accounting stays reconcilable.
Analysis sessions and messages: user-deletable.
Dataset versions: last N retained plus one per quarter as an archive.
