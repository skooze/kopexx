# Data Dictionary

> **RE-FOUNDED 2026-08-02 ON MEASURED EVIDENCE.** A representative corpus of **112 SEC issuers and
> 613 filings across six transport eras** was acquired and measured — dated Phase 1 evidence, not a
> permanent constant — and it refuted the assumptions the deterministic semantic parser rested on.
> The product is an orchestrator-driven, model-first SEC filing product: the backend acquires,
> preserves, transports, orchestrates and VALIDATES; a user-selected parsing model determines what
> a filing means. The user selects four models independently — parsing, image, summary, and
> analysis/chat. The current authorized input mode is `INTACT_SOURCE_ONLY`. The deterministic
> content ontology, migration `0003` and the local application database are withdrawn. Sections
> below that describe the withdrawn design are historical.
>
> **NO MODEL HAS BEEN INVOKED AND AWS IS NOT CONFIGURED.** Authoritative:
> `docs/adr/ADR-0016-corpus-first-model-first-architecture.md` and `roadmap.md`.

---

# ARCHITECTURAL VOCABULARY — AUTHORITATIVE. Everything below this section is historical.

**THIS IS NOT A SCHEMA.** No table definition here is current, and the final persistence
representation is **DEFERRED to Phase 8**, after real parsed artifacts from real models over
materially different corpus samples exist. Designing tables before seeing model output is exactly
what produced the withdrawn migration `0003`.

**Rigid semantic categories are removed from the mandatory vocabulary.** There is no required
content-unit type, no required hierarchy, and no enum of filing sections. Terms like MD&A, Item 7,
Part I, Footnote, Certification or Signature may appear as filing-native labels, model annotations,
optional derived indexes or search facets. They are not vocabulary the system requires.

## The terms

| Term | Meaning |
|---|---|
| **Entity** | An SEC filer. Identity is the CIK. Names and tickers are temporal aliases. |
| **Filing** | One submission. Identity is `(CIK, accession)` — never the accession alone, because co-registration puts one submission under two filer CIKs. |
| **Source artifact** | An original SEC document, preserved byte-for-byte with its SHA-256 and provenance. Authoritative. Never replaced by anything derived. |
| **Processing job** | One authorized unit of work over an entity, a timeframe and four model selections. Durable and resumable. |
| **Model role** | One of exactly four: parsing, image, summary, analysis/chat. |
| **Model selection** | The user's explicit choice of a model for one role on one job. No role inherits another's. |
| **Model invocation** | One call to one provider. Records tokens, cost, latency, prompt version, model id, and the object-storage URIs of the exact request and response bodies. |
| **Artifact** | Anything a model produced that the system keeps. Never confused with the source. |
| **Artifact version** | Artifacts are superseded, never overwritten. |
| **Artifact lineage** | What produced this artifact, from what, with which prompt, superseding what. |
| **Parsed artifact** | The accepted output of the parsing model. Deliberately loosely typed. |
| **Summary artifact** | A separate artifact grounded in an accepted parse. Regenerating it does not require reparsing. |
| **Image-analysis artifact** | Produced by the image model, only when the parsing model is text-only. Linked to its source object. |
| **Chat artifact** | A Deep Dive turn: question, answer, citations, cost, bound to an immutable scope. |
| **Source reference** | A byte range in a preserved original artifact. Validation resolves it there, not in the parse. |
| **Validation result** | The backend's independent proof of coverage, citations and numbers against preserved bytes. `COMPLETE`, `PARTIAL` or `REVIEW_REQUIRED`. |
| **Cost record** | Tokens, amount, currency, latency, and whether the figures are measured or estimated. |
| **Cache record** | A reusable accepted result, keyed by what actually determines it. |

## What the vocabulary deliberately omits

No content-unit type. No section kind. No universal hierarchy. No proxy-topic mapping. No
disposition enum describing one interpretation of every filing.

A parsed node carries: an id, an order, an optional parent, an optional filing-native label, an
optional open-ended content type, text, source references, confidence, ambiguity, and an explicit
unresolved flag. Its shape is in `docs/api/openapi.yaml` as `ParsedNode`, and it is
`additionalProperties: true` on purpose.

## The one semantic guarantee that survives

Every financial-statement footnote **the accepted parse identifies** remains an independent node
and an independent required summary target. That is a completeness guarantee about not merging
content away. It is not a taxonomy, and the backend does not decide what a footnote is.


IMPLEMENTATION STATUS: IMPLEMENTED (Sprint 2; table-ownership columns Sprint 4; complete filing
content Sprint 4.1).

27 domain tables. Models in `packages/persistence/models.py`. Migrations: `0001_initial` (SEALED),
`0002_table_ownership` (SEALED), and `0003_filing_content`, which added the complete filing-content
model described below.

---

## Complete filing content — migration `0003` (Sprint 4.1)

Decision: ADR-0016. WITHDRAWN — see the vocabulary section below. Retained here only as the
record of what migration `0003` would have encoded; it was never committed.

### `filing_content_unit`

One node in a filing's canonical content hierarchy: cover page through signatures and filed
exhibits.

| Column | Type | Null | Notes |
|---|---|---|---|
| `content_unit_id` | uuid | no | Primary key |
| `filing_id` | uuid | no | FK `filing`, cascade |
| `document_id` | uuid | yes | FK `filing_document`. Which filed document this came from |
| `parent_content_unit_id` | uuid | yes | FK self, cascade. NULL only on the filing root |
| `canonical_footnote_id` | uuid | yes | FK `canonical_footnote`. **Reference, never a copy** |
| `filing_section_id` | uuid | yes | FK `filing_section`, retained link to Sprint 4 sections |
| `unit_type` | text | no | Taxonomy below; check-constrained |
| `part_number` | text | yes | Roman numeral, e.g. `II` |
| `item_number` | text | yes | e.g. `1A`, `7A` |
| `title_as_displayed` | text | yes | Exactly as filed |
| `normalized_title` | text | yes | Lowercased, for comparison only |
| `sequence` | integer | no | Filed order among siblings |
| `hierarchy_path` | text | no | **Materialized path**; see semantics below |
| `text` | text | yes | Normalized prose. NULL on aggregates and footnote references |
| `source_char_start` / `_end` | integer | yes | Span in the filed document |
| `source_anchor` | text | yes | |
| `source_sha256` | text | yes | Hash of the RAW source span |
| `content_sha256` | text | yes | Hash of the NORMALIZED text. Two hashes distinguish a parser change from a filing change |
| `extraction_method` | text | yes | |
| `parser_version` | text | yes | |
| `confidence` | numeric(5,4) | yes | |
| `coverage_status` | text | no | `COVERED` \| `PARTIAL` \| `UNRESOLVED` \| `EXCLUDED` |
| `summary_required` | boolean | no | Set from unit TYPE and filed position, **never from materiality** |
| `incorporated_by_reference` | boolean | no | |
| `unit_metadata` | jsonb | yes | |

**Idempotency key**: `UNIQUE (filing_id, hierarchy_path)`.

**Constraints.** `content_unit_type_is_known`; `content_coverage_status_is_known`;
`content_unit_is_not_own_parent`; `footnote_reference_requires_footnote_type` — a
`canonical_footnote_id` is only valid on a `FINANCIAL_STATEMENT_FOOTNOTE` unit, so there is no
second path to footnote evidence; `footnote_unit_does_not_copy_text` — a footnote unit stores NULL
text, because two editable copies of one fact diverge and nothing notices.

### `hierarchy_path` — materialization semantics

Dotted zero-padded ordinals from the root: `001.002.007`. **Derived** from
`(parent_content_unit_id, sequence)` and rewritten by the same transaction that writes them.

Stored, rather than computed on read, for two reasons stated so it is not mistaken for a second
source of truth: `(parent_content_unit_id, sequence)` cannot serve as a unique constraint, because
a NULL parent never conflicts in one and two content roots would insert silently; and a stored path
turns a subtree read into a prefix scan rather than a recursive CTE on every dashboard request.
Zero-padding makes lexical order equal filed order past nine siblings.

### `filing_source_block` — the coverage ledger

One discovered human-visible leaf block and its single disposition.

| Column | Type | Null | Notes |
|---|---|---|---|
| `source_block_id` | uuid | no | Primary key |
| `filing_id` | uuid | no | FK `filing`, cascade |
| `document_id` | uuid | yes | FK `filing_document` |
| `content_unit_id` | uuid | yes | **The single owner.** Non-NULL if and only if `ASSIGNED` |
| `block_key` | text | no | `{document_tag}:{ordinal}` over an immutable filed document |
| `sequence` | integer | no | Discovery order |
| `block_kind` | text | no | `heading` \| `text` \| `table` \| `list` \| `graphic` \| `signature` \| `other` |
| `disposition` | text | no | The six below |
| `disposition_reason` | text | yes | Required for every exclusion |
| `normalized_text` | text | yes | |
| `text_sha256` | text | yes | |
| `char_length` | integer | yes | |
| `source_char_start` / `_end` | integer | yes | |
| `parser_version` | text | yes | |
| `evidence` | jsonb | yes | |

**Idempotency key**: `UNIQUE (filing_id, block_key)`. Stable because it derives from position in an
immutable filed document, never from a runtime DOM identity — which would change between runs and
make rerun reconciliation meaningless.

**Dispositions.** Five count as accounted; one does not.

| Disposition | Accounted |
|---|---|
| `ASSIGNED` | yes |
| `REPEATED_LAYOUT` | yes |
| `NAVIGATION_DUPLICATE` | yes |
| `DECORATIVE` | yes |
| `MACHINE_ONLY` | yes |
| `UNRESOLVED` | **no — blocks completion, and is never a reason to discard the block** |

**Constraints.** `assigned_block_has_exactly_one_owner` makes `ASSIGNED` equivalent to a non-NULL
`content_unit_id`, so **double assignment is unrepresentable** rather than merely tested for.
`excluded_block_states_its_reason` — an exclusion without a reason is indistinguishable from a
block nobody looked at.

### `filing_incorporation_reference`

A statement that this filing incorporates material filed elsewhere.

| Column | Type | Null | Notes |
|---|---|---|---|
| `reference_id` | uuid | no | Primary key |
| `filing_id` | uuid | no | FK `filing`, cascade |
| `content_unit_id` | uuid | yes | The unit containing the statement |
| `reference_key` | text | no | Stable digest of accession, unit, and source text |
| `item_number` | text | yes | The Item whose disclosure is incorporated |
| `referenced_form` | text | yes | e.g. `DEF 14A` |
| `referenced_document` | text | yes | |
| `referenced_accession` | text | yes | Set when deterministically resolved |
| `referenced_filing_date` | date | yes | |
| `referenced_deadline` | text | yes | e.g. "within 120 days after September 27, 2025" |
| `resolution_status` | text | no | `UNRESOLVED` \| `IDENTIFIED` \| `RESOLVED` \| `OUT_OF_SCOPE` |
| `acquisition_status` | text | no | `NOT_ATTEMPTED` \| `ACQUIRED` \| `UNAVAILABLE` \| `OUT_OF_SCOPE` |
| `source_text` | text | yes | The exact filed sentence, so a reviewer can check the detector |
| `coverage_consequence` | text | yes | |
| `detected_by`, `parser_version` | text | yes | |

**Idempotency key**: `UNIQUE (filing_id, reference_key)`.

**Constraint.** `resolved_reference_names_its_evidence` — `RESOLVED` requires a
`referenced_accession` and `acquisition_status = 'ACQUIRED'`. Marking a dependency resolved without
evidence is the specific dishonesty this table exists to prevent.

### `filing_document` — columns added by `0003`

| Column | Type | Null | Notes |
|---|---|---|---|
| `document_class` | text | no | `HUMAN_READABLE` \| `MACHINE_ARTIFACT` \| `GRAPHIC` \| `UNKNOWN` |
| `inventory_sequence` | integer | yes | Position in the authoritative accession inventory |
| `is_primary` | boolean | no | |
| `classification_method` | text | yes | `declared_type` where possible; filename only as fallback |
| `classification_evidence` | jsonb | yes | Declared type, role, extraction requirement, reason |

**Idempotency key added**: `UNIQUE (filing_id, filename)`.

### `filing` — columns added by `0003`

| Column | Type | Null | Notes |
|---|---|---|---|
| `content_status` | text | no | `COMPLETE` \| `PARTIAL` \| `REQUIRES_REVIEW` \| `FAILED` \| `NOT_STARTED` |
| `submission_completeness` | text | no | `SUBMISSION_COMPLETE` \| `SUBMISSION_PARTIAL` \| `NOT_ASSESSED` |
| `disclosure_completeness` | text | no | `DISCLOSURE_COMPLETE` \| `DISCLOSURE_PARTIAL` \| `NOT_ASSESSED` |
| `content_coverage_confidence` | numeric(4,3) | yes | A judgement, not a count |
| `documents_listed` | integer | yes | What the AUTHORITATIVE inventory claimed |
| `content_parser_version` | text | yes | |

`footnote_status` is unchanged and remains the **footnote layer**. It must never be read as filing
completeness.

### Content-unit taxonomy

```
FILING_ROOT   COVER_PAGE   PART   ITEM   SUBSECTION   NARRATIVE
FINANCIAL_STATEMENT_SET   FINANCIAL_STATEMENT
FINANCIAL_STATEMENT_FOOTNOTE_SET   FINANCIAL_STATEMENT_FOOTNOTE   FINANCIAL_SCHEDULE
TABLE   LIST   GRAPHIC   EXHIBIT_INDEX   EXHIBIT   CERTIFICATION   SIGNATURE   CONSENT
INCORPORATED_REFERENCE   OTHER_DISCLOSURE   UNRESOLVED
```

There is deliberately **no** disposition or status meaning "skipped because it looked unimportant".

### Derived, deliberately not stored

Every count the coverage report shows — blocks discovered, assigned, excluded, unresolved, content
units, duplicate assignments, required summary units — is a `COUNT()` over
`filing_source_block` and `filing_content_unit`. Only judgements are stored, for the same reason
the eleven footnote counters are not stored: a stored copy of a derivable count is a second source
of truth that goes stale the moment a block is re-dispositioned.

---

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
