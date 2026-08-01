# Data Dictionary

IMPLEMENTATION STATUS: IMPLEMENTED (Sprint 2).

24 tables, 36 indexes, 93 constraints. Models in `packages/persistence/models.py`; migration in
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

24 tables. Full column definitions in `packages/persistence/models.py` and the initial migration.
Summary of ownership:

| Table | Owns | Key invariant |
|---|---|---|
| `issuer` | Issuer identity | CIK unique |
| `issuer_former_name` | Name history | Needed because delisted issuers are renamed |
| `listing` | Ticker history | Unique on `(ticker, exchange, effective_start)`, never on ticker |
| `listing_observation` | Raw snapshots | Append only; never overwritten |
| `excluded_filer` | Exclusions | Reason always populated |
| `filing` | Filing metadata | Accession unique |
| `filing_document` | Acquired objects | Every row has a sha256 |
| `filing_section` | Item sections | Carries extraction strategy and confidence |
| `canonical_footnote` | Footnotes | Unique on `(filing_id, normalized_number)` |
| `footnote_source_block` | Source blocks | Parent nullable so orphans are visible |
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

## Retention

Filing data and facts: indefinite; public data with provenance value.
Summaries: indefinite, including superseded versions.
Model invocation records: indefinite; principal anonymized on user deletion rather than the row
removed, so cost accounting stays reconcilable.
Analysis sessions and messages: user-deletable.
Dataset versions: last N retained plus one per quarter as an archive.
