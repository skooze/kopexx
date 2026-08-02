# techspecs.md — FinTek Technical Specification

THIS DOCUMENT DESCRIBES WHAT THE CODE CURRENTLY DOES.
Sections describing future work are marked `PLANNED` and are not descriptions of behaviour that
exists.

LAST SYNCHRONIZED WITH CODE: Sprint 3 complete, including the DERA fact load
VERIFICATION: 337 tests passing and 0 skipped, 92.73 percent coverage on implemented packages,
ruff format and lint clean across `packages tests scripts migrations`, mypy clean across 65 source
files in `packages scripts migrations`, offline Alembic upgrade and downgrade, and pip-audit
clean.

The source-file count fell from 59 to 41 when the alignment review removed eighteen packages that
contained only a docstring (ADR-0015), rose to 45 when type checking extended to `scripts` and
`migrations`, reached 53 when filing discovery and acquisition arrived, and is 65 now that the
DERA loader and the database-isolation guard exist.

`packages/` holds ten implemented libraries. Two were added in Sprint 3: `filing_discovery` and
`filing_acquisition`. `dera_notes` grew from a mirror into a mirror plus a fact loader.

## Build and packaging

`pyproject.toml` declares explicit setuptools discovery: `[tool.setuptools.packages.find]` with
`include = ["packages*"]`. Automatic flat-layout discovery cannot work in this repository — the
root holds `prompts`, `artifacts`, `migrations`, `metric_definitions`, `docs`, and `tests`, and
setuptools refuses to guess. It additionally picked up the gitignored `var/` directory in a local
checkout, so the failure was not even reproducible across environments.

`packages/` is the only importable tree: it and every subpackage carries `__init__.py`, and
every import in the codebase has the form `packages.<name>`. No package-data configuration is
needed because `packages/` contains zero non-`.py` files; prompts, metric definitions, and
migrations are loaded from the repository by path rather than as package resources.

Runtime dependencies are `ruamel.yaml`, `pydantic`, `httpx`, `sqlalchemy`, `alembic`, and
`psycopg[binary]`. The last three were omitted until the first CI run: the package-discovery
failure masked the fact that an install without them cannot import `packages.persistence`.

---

## 1. System context

```
        SEC EDGAR                          Model provider
   www.sec.gov  data.sec.gov                (Bedrock or mock)
   efts.sec.gov  DERA datasets                    |
            |                                     |
            v                                     v
   +--------------------------------------------------------------+
   |                          FinTek                              |
   |                                                              |
   |  ingestion  ->  parsing  ->  facts + footnotes  ->  serving   |
   |                                    |                          |
   |                              summarization                    |
   |                                    |                          |
   |                              Deep Analysis                    |
   +--------------------------------------------------------------+
            |
            v
        Investor dashboard
```

FinTek reads from SEC and from a model provider. It writes nothing back to either. The only
outbound side effect is a model invocation, which is metered and audited.

---

## 2. Implementation status by component

| Component | Package | Status |
|---|---|---|
| SEC identity normalization | `sec_identity` | IMPLEMENTED |
| Configuration and User-Agent validation | `configuration` | IMPLEMENTED |
| Rate limiting and throttle classification | `sec_client` | IMPLEMENTED |
| SEC HTTP client | `sec_client` | IMPLEMENTED |
| Object storage and hashing | `storage` | IMPLEMENTED (filesystem); S3 PLANNED |
| Structured logging and correlation | `observability` | IMPLEMENTED |
| DERA discovery and mirror ledger | `dera_notes` | IMPLEMENTED |
| DERA bulk download | `dera_notes` + `sec_client` | IMPLEMENTED and EXECUTED (78/78 packages) |
| DERA TSV load, normalization, validation, reconciliation | `dera_notes` | IMPLEMENTED and EXECUTED (2,845 facts, 4 filings) |
| PostgreSQL control-plane schema | `persistence` | IMPLEMENTED (24 tables) |
| Database URL resolution, identity comparison, engine construction | `persistence` | IMPLEMENTED |
| Destructive-test database isolation | `persistence` + `tests/conftest.py` | IMPLEMENTED |
| AWS identity and secret-management policy | governance + `tests/architecture` | IMPLEMENTED as governance; no AWS code exists |
| Alembic migration | `migrations` | IMPLEMENTED and APPLIED; `0001_initial` sealed, `0002_table_ownership` added Sprint 4 |
| LLM gateway, boundary, YAML, audit | `llm_gateway` | IMPLEMENTED |
| Filing discovery | `filing_discovery` | IMPLEMENTED (Sprint 3) |
| Filing acquisition, inline-XBRL era | `filing_acquisition` | IMPLEMENTED (Sprint 3) |
| Footnote extraction: inventory, candidates, headings | `footnote_extractor` | IMPLEMENTED (Sprint 4) |
| Canonicalization stages 1-5, audit, completeness | `footnote_canonicalizer` | IMPLEMENTED (Sprint 4); stages 6-11 PLANNED |
| Footnote table structure and cell provenance | `table_parser` | IMPLEMENTED (Sprint 4) |
| Table-to-footnote ownership via tagged spans and the presentation linkbase | `footnote_canonicalizer` | IMPLEMENTED (Sprint 4); 0 unresolved on 4 filings |

Reserved package names. **These directories do not exist.** Sprint 1 created them containing only
a docstring, which reserved names up to twenty sprints ahead of their code and caused two
architecture tests to pass while scanning nothing. They were removed by the alignment review
(ADR-0015); each is created in the sprint that writes its first module. `tests/architecture`
enforces that no package is an empty stub.

| Reserved name | Planned path | Sprint |
|---|---|---|
| Bedrock provider adapter | `packages/llm_gateway/providers/bedrock.py` | 5 |  <!-- constrained by docs/security/aws-identity-and-secrets.md -->
| Era parsers | `packages/filing_parser` | 5 |
| Summarization pipeline | `packages/summarization` | 5 |
| Validation pipeline | `packages/validation` | 5 |
| Fiscal period logic | `packages/fiscal` | 6 |
| XBRL processing | `packages/xbrl` | 6 |
| Fact lake | `packages/fact_lake` | 6 |
| Metric resolution | `packages/financial_metrics` | 6 |
| API | `apps/api` | 6 |
| Web dashboard | `apps/web` | 6 |
| Retrieval | `packages/retrieval` | 7 |
| Deep Analysis | `packages/deep_analysis` | 7 |
| Issuer registry | `packages/issuer_registry` | Stage 2, W-1 |
| Worker and scheduler | `apps/worker`, `apps/scheduler` | Stage 2, W-7 |

---

## 3. Implemented components in detail

### 3.1 `packages/sec_identity` — IMPLEMENTED

RESPONSIBILITY. The single home for CIK normalization, accession normalization, and SEC URL
construction. No other package may reimplement these.

INPUTS. Raw CIK values in any of four forms, accession numbers in either form, filing metadata.

OUTPUTS. Normalized identifiers and fully-formed SEC URLs.

PUBLIC INTERFACE. `parse_cik`, `cik_padded`, `cik_archive`, `cik_submissions_stem`,
`parse_accession`, `accession_dashed`, `accession_undashed`, `accession_filer_prefix`,
`is_valid_accession`, `submissions_url`, `submissions_shard_url`, `filing_folder_url`,
`primary_document_url`, `complete_submission_url`, `filing_xbrl_zip_url`,
`filing_index_json_url`, `extracted_instance_url`, `quarterly_index_url`,
`company_tickers_exchange_url`.

DEPENDENCIES. Standard library only.

PROHIBITED DEPENDENCIES. Everything. This package is a leaf.

DATA OWNED. None; it is pure computation.

INVARIANTS.
- `data.sec.gov` receives the ten-digit padded CIK; `www.sec.gov/Archives` receives the unpadded
  integer.
- The dashed accession is canonical; the undashed form is used only as a folder segment.
- The accession prefix is never used as the issuer CIK.
- An empty primary-document name never produces a URL.

FAILURE MODES. `InvalidCikError`, `InvalidAccessionError`, `MissingPrimaryDocumentError`. All are
permanent; none is retryable.

RETRY BEHAVIOR. None. Malformed input does not become valid on retry.

SECURITY. Rejects boolean input, which would otherwise pass as an integer CIK of 1.

OBSERVABILITY. None required; failures surface as typed exceptions at the call site.

SCALING. Pure functions, no state.

UNIT TESTS. 16 in `tests/unit/test_sec_identity.py`, including the filing-agent prefix trap, the
empty pre-2001 primary document, and both accession forms in one URL.

INTEGRATION TESTS. Exercised transitively by every other package.

### 3.2 `packages/configuration` — IMPLEMENTED

RESPONSIBILITY. Load and eagerly validate settings so a misconfiguration fails at startup rather
than after generating traffic that will be blocked.

PUBLIC INTERFACE. `Settings.from_env`, `SecAccessSettings`, `StorageSettings`, `LlmSettings`,
`validate_user_agent`, `is_valid_user_agent`, `DENYLIST_FRAGMENTS`.

INVARIANTS.
- A User-Agent must exist, must contain a contact email, and must not match a library default.
- Global rate must be within `(0, 10]`.
- Throttle cooldown must be at least 600 seconds.

FAILURE MODES. `InvalidUserAgentError` and `ValueError` at construction. Both are fatal at
startup by design.

UNIT TESTS. 6 in `tests/unit/test_configuration.py`.

### 3.3 `packages/sec_client` — IMPLEMENTED (limiter and classifier Sprint 1; HTTP client Sprint 2)

RESPONSIBILITY. Pace all SEC traffic and classify refusals correctly.

PUBLIC INTERFACE. `SecRateLimiters`, `TokenBucketLimiter`, `Clock`, `FakeClock`, `classify_403`,
`raise_for_403`, `extract_reference_id`, `looks_like_directory_listing`, and the typed error
hierarchy.

DATA OWNED. Token-bucket state, throttle events, reference identifiers.

INVARIANTS.
- `www.sec.gov` and `data.sec.gov` share one bucket, because the documented limit is aggregate.
- `efts.sec.gov` has its own, slower bucket.
- A rate-threshold 403 is retryable; an undeclared-automation 403 is not.
- A directory listing is never treated as filing content.

FAILURE MODES AND RETRY. See the retry matrix in `docs/sec/access-policy.md`.

KNOWN DEFECT FIXED IN SPRINT 1. The token bucket compared `tokens >= 1.0` exactly. After sleeping
the computed delay, refill could land a fraction below 1.0 in binary floating point, so the
acquire loop spun forever on ever-smaller deltas. A nanotoken epsilon fixes it. This was found by
the test suite hanging, not by review.

SCALING. In-process today. A Redis-backed bucket is PLANNED and required before multi-process
ingestion, because the limit is aggregate across machines.

UNIT TESTS. 9 in `tests/unit/test_sec_client.py`, using an injectable fake clock so rate-limit
tests are deterministic and complete in milliseconds.

### 3.4 `packages/storage` — filesystem backend IMPLEMENTED; S3 PLANNED

RESPONSIBILITY. Durable storage for raw filings, datasets, and exact model request and response
bodies, with content hashing.

PUBLIC INTERFACE. `ObjectStore`, `FilesystemObjectStore`, `StoredObject`, `sha256_bytes`,
`sha256_text`, `sha256_stream`, `sha256_file`.

INVARIANTS.
- An object key is relative and never escapes the store root.
- Writes are atomic via a temporary file and replace, so a killed writer leaves no partial object
  under the final key.
- Every stored object records a SHA-256.

SECURITY. Path traversal and absolute keys are rejected rather than silently reinterpreted.

UNIT TESTS. 6 in `tests/unit/test_storage.py`.

### 3.5 `packages/observability` — IMPLEMENTED

RESPONSIBILITY. Structured logging with correlation identifiers.

PUBLIC INTERFACE. `get_logger`, `log_event`, `configure_logging`, `correlation_scope`,
`new_correlation_id`, `get_correlation_id`, `set_correlation_id`, `reset_correlation_id`,
`REDACTED_FIELDS`.

INVARIANT. Filing text and model payload bodies are never logged. A fixed field set is redacted.

### 3.6 `packages/dera_notes` — IMPLEMENTED (mirror Sprint 1; fact load Sprint 3)

RESPONSIBILITY. Discover, mirror, and record SEC DERA NOTES packages, and load one filing's facts
from a mirrored package into the append-only fact lake.

MODULES, one responsibility each. Splitting them is not decoration: a single load script would put
a transaction boundary, a CSV dialect, and a calendar derivation in one place, and the calendar
derivation is where the only correctness defect of this sprint was found.

| Module | Owns |
|---|---|
| `discovery` | scraping the authoritative listing |
| `ledger` | the JSON mirror ledger; resumability |
| `selection` | which package holds a filing; archive completeness; period ordering |
| `tsv` | parsing, quoting DISABLED, streamed |
| `dimensions` | `dimh` to axis and member, from `dim.tsv` |
| `normalize` | row to domain values, including the derived period start |
| `validate` | domain rules mirroring the database constraints |
| `registration` | the `issuer` and `filing` rows the fact foreign keys require |
| `loader` | one transaction: insert, load ledger, idempotency, advisory lock |
| `reconcile` | nine checks against the source and the database |
| `report` | plain text for a person |

PUBLIC INTERFACE. `discover_packages`, `classify_filename`, `DeraPackage`, `PackageCadence`,
`MirrorLedger`, `MirrorEntry`, `NOTES_LANDING_URL`, `locate_filing`, `SelectedPackage`,
`register_filing`, `register_mirror_ledger`, `FilingContext`, `read_package`, `load_facts`,
`LoadResult`, `reconcile`, `Reconciliation`, `full_report`.

INVARIANTS.
- Filenames are scraped from the authoritative listing, never generated.
- Empty discovery raises rather than returning an empty list.
- Monthly packages are retained after quarterly consolidation.
- `pending()` makes a run resumable; a completed run downloads nothing.
- TSVs are parsed with `csv.QUOTE_NONE`. A double quote inside a DERA field is literal data;
  QUOTE_MINIMAL would merge the fields on either side of it with no error raised.
- The package holding a filing is found by reading `sub.tsv`, never by deriving a period from a
  date. A filing belongs to the period it was SUBMITTED in.
- The archive is re-hashed before every load. The download-time hash is not trusted.
- A required member missing fails the load closed.
- Numeric values are `Decimal`, never `float`.
- Idempotency is by the DERA natural key `(adsh, tag, version, ddate, qtrs, uom, dimh, iprx,
  coreg)`, recomputed from the package on every run. `dera_package.loaded_at` records what
  happened and never authorises a skip.
- Insertion, the load ledger update, and the row counts are one transaction. A failure leaves no
  rows and an unmarked ledger.
- Every row is written `validation_status = 'UNVALIDATED'` and `is_latest_selected = false`. The
  validation pipeline is Sprint 5 and latest-selection is Sprint 6.

KNOWN PROPERTY OF THE SOURCE. `ddate` is rounded to the nearest month end and `qtrs` is a whole
number of quarters; DERA publishes the residuals as `datp` and `durp`. `period_start` is not
published at all and is derived. Exact filed boundaries come from the XBRL instance in Sprint 6
and supersede these rows through the append-only restatement path.

SCOPE LIMIT. Per accession, not per package. `xbrl_fact` has foreign keys to `issuer` and
`filing`, so loading a whole monthly package would first require registering thousands of issuers
— Stage 2 phase W-1, out of scope by ADR-0015.

TESTS. 105. Unit: `test_dera_notes` 7, `test_dera_tsv` 16, `test_dera_normalize` 25,
`test_dera_validate` 18, `test_dera_selection` 16, `test_dera_report` 8. Integration:
`test_dera_load` 13 against a live database, `test_dera_mirror` 2. The integration suite was proven
non-vacuous by removing the idempotency guard and observing the rerun test fail with 8 rows where
4 belong.

EXECUTED. 2,845 facts across Apple's FY2025 10-K and three 10-Qs, from four packages, every load
reconciled on nine checks including an exact numeric-total match against PostgreSQL's own `sum()`.

### 3.7 `packages/sec_client.client` — IMPLEMENTED (Sprint 2)

RESPONSIBILITY. The only component permitted to issue HTTP requests to an SEC host.

PUBLIC INTERFACE. `SecHttpClient(user_agent, limiters, cooldown_seconds, ...)` with `get_text`,
`head`, `download(url, destination, expect_zip)`, and `FetchResult`.

INVARIANTS. Every request passes the shared limiter and carries the validated User-Agent. A
rate-threshold 403 triggers a full 600-second cooldown, never exponential backoff. An
undeclared-automation 403 raises immediately and is never retried. A download writes to a
temporary path and is renamed only after every assertion passes.

CONTENT ASSERTIONS, all rejecting rather than storing: HTML page where content was expected,
directory listing, wrong magic bytes for an expected ZIP, body shorter than its declared
Content-Length, ZIP with no members, ZIP whose member fails CRC.

FAILURE MODES. `SecRateLimitedError` retryable; `SecUndeclaredAutomationError` never;
`SecNotFoundError` permanent; `DirectoryListingError` permanent; `SecTransientError` retryable
with bounded backoff.

SCALING. Single-process. The in-process limiter means exactly one client may run at a time,
because the SEC limit is aggregate across machines. The Redis-backed limiter is required before
multi-process ingestion and is BLOCKING for Stage 2 phase W-2.

TESTS. 15 in `tests/unit/test_sec_http_client.py` using `httpx.MockTransport`, including a test
asserting the cooldown is exactly one 600-second pause rather than a backoff sequence.

PROVEN IN PRODUCTION. Executed the full DERA mirror: 78 packages, 27,228,877,737 bytes, zero
failures, zero throttle events.

### 3.8 `packages/persistence` — IMPLEMENTED (Sprint 2)

RESPONSIBILITY. The PostgreSQL control-plane schema.

SCOPE. 24 domain tables. In the live database: 23 check, 19 unique, 29 foreign-key and 25 primary-key constraints, and 37 explicit indexes (81 including constraint-backing). Issuer identity with temporal validity, filings and
documents and sections and amendments, canonical footnotes with source blocks and tables, the
append-only fact lake, metric definitions and derived values, versioned summaries, the ingest
ledger, the DERA mirror ledger, Deep Analysis sessions and messages and memory, model invocation
audit, prompt registry, and the dataset version pointer.

PROHIBITED DEPENDENCIES. Pure-logic packages must never import this package. Dependency flows
domain <- persistence.

KEY ENFORCEMENT.
- `xbrl_fact` carries a BEFORE UPDATE trigger rejecting any change to a filed value, unit, scale,
  concept, or period. The guarantee holds against a direct SQL session, not only against
  application code.
- `listing` is unique on `(ticker, exchange, effective_start)`, never on ticker alone.
- `footnote_summary` has a partial unique index giving exactly one active version per footnote.
- `footnote_source_block.footnote_id` is nullable, with a partial index over orphans, so an
  ungrouped block is a visible defect rather than a silent loss.
- `llm_invocation` has a check constraint restricting content format to plain_text or yaml.

MIGRATION. `migrations/versions/0001_initial_control_plane_schema.py`. Generated deterministically
from the model metadata by `scripts/generate_initial_migration.py`, because Alembic autogenerate
requires a live database and this environment has none.

TESTS. 14 in `tests/unit/test_migrations.py`. Twelve structural tests run everywhere; two live
tests SKIP with an explicit reason when no PostgreSQL is reachable, so a missing database never
masquerades as a pass.

### 3.9 `packages/llm_gateway` — IMPLEMENTED

RESPONSIBILITY. The only path from FinTek to a language model. Owns payload compilation, boundary
validation, budget enforcement, provider invocation, response validation, safe parsing, cost
calculation, and audit.

FULL SPECIFICATION. `docs/llm/content-boundary.md`.

PUBLIC INTERFACE. `LlmGateway`, `Budget`, `GatewayResult`, `InvocationRecord`, `compile_yaml`,
`compile_plain_text`, `compile_footnote_summary_request`, `FootnoteSummaryRequest`,
`SourceBlockPayload`, `TablePayload`, `validate_plain_text`, `validate_yaml_text`, `enforce`,
`parse_yaml`, `require_mapping`, `require_string`, `to_yaml`, `estimate_tokens`,
`SerializationComparison`, `PricingRegistry`, `ModelPricing`, `ModelCapabilities`,
`reject_native_tools`, and the typed error hierarchy.

PROHIBITED DEPENDENCIES. No provider SDK outside `providers/`. No application package.

INVARIANTS. The eight listed in `docs/llm/content-boundary.md`, of which the load-bearing ones
are: model-visible content is plain text or one unfenced YAML 1.2 document; only the compiler
produces it; exact bodies are preserved; budgets are checked before invocation; every identifier
is quoted.

YAML PARSER, PINNED. ruamel.yaml 0.19.1, `YAML(typ="safe", pure=True)`, YAML 1.2 core schema,
VersionedResolver, on Python 3.14.6. PyYAML is not used because it implements YAML 1.1.

THREE VERIFIED FACTS THE DESIGN RESTS ON.
- YAML 1.2 does not coerce `yes`, `no`, `on`, `off` to booleans; YAML 1.1 does. `ruamel.yaml` in
  pure safe mode is used for exactly this reason.
- YAML 1.2 parses an unquoted `0000320193` as the integer `320193`, destroying a CIK. Identifiers
  are always quoted, and `require_string` refuses an identifier that arrived unquoted.
- Alias expansion was UNBOUNDED before Sprint 2. A five-line document expanded to 59,049 leaf
  nodes. A pre-parse anchor and alias budget now rejects it, because a post-parse check runs after
  the allocation has already happened.

UNIT TESTS. 36 across boundary and parser suites.

---

## 4. Repository structure

```
apps/            api, worker, scheduler, web            PLANNED
packages/        25 domain packages, 7 implemented
prompts/         versioned .txt and .yaml, never .md
metric_definitions/  6 curated metric YAML files
migrations/      PLANNED
scripts/         mirror_dera.py
tests/           unit, integration, contract, golden, evaluation, security, architecture, fixtures
docs/            architecture, sec, financial, footnotes, llm, deep-analysis, api,
                 data-dictionary, testing, operations, runbooks, adr, sprints, diagrams
infrastructure/  Terraform                              PLANNED
```

## 5. Dependency direction

```
domain
  ^
parsers / facts / metrics / summaries
  ^
application services
  ^
api / worker / scheduler
```

Enforced by `tests/architecture/test_architecture.py`, which also asserts no generic `utils`
module, no reimplemented CIK padding, no provider SDK outside the adapter, no Markdown prompt
files, no prompt requesting a prohibited output format, and a public interface on every package.

## 6. Storage architecture

| Store | Owns | Status |
|---|---|---|
| Object storage | Raw filings, datasets, exact model bodies | IMPLEMENTED (filesystem) |
| Parquet | Fact lake, serving datasets | PLANNED |
| DuckDB | In-process query engine over Parquet | PLANNED |
| PostgreSQL | All control-plane state including the ingest ledger | PLANNED |
| Redis | Cache, rate buckets, locks, fan-out | PLANNED |

SQLite is deliberately not used. See ADR-0004.

The DuckDB decision is load-bearing: a reader cannot open a database file another process holds
read-write, so the serving path reads immutable versioned Parquet through an in-memory connection
and no file lock ever exists. See ADR-0002.

## 7. Processing state machine — PLANNED

```
DISCOVERED -> QUEUED -> DOWNLOADING -> DOWNLOADED -> PARSING -> PARSED
  -> EXTRACTING_FACTS -> FACTS_EXTRACTED
  -> EXTRACTING_SECTIONS -> SECTIONS_EXTRACTED
  -> EXTRACTING_FOOTNOTES -> FOOTNOTES_EXTRACTED
  -> GROUPING_FOOTNOTES -> FOOTNOTES_GROUPED
  -> VALIDATING_FOOTNOTES -> FOOTNOTES_VALIDATED
  -> SUMMARIZING -> SUMMARIES_GENERATED -> VALIDATING_SUMMARIES
  -> CALCULATING_METRICS -> PUBLISHING -> COMPLETE

Any state -> FAILED | PARTIAL | REQUIRES_REVIEW

Forbidden: any transition directly to COMPLETE that skips VALIDATING_SUMMARIES.
Forbidden: PARTIAL -> COMPLETE without re-entering SUMMARIZING.
```

There is no `processed` boolean anywhere in the schema.

## 8. Security

Full threat model in `docs/deep-analysis/security.md`. Boundary controls implemented in Sprint 1;
session and retrieval controls are Sprint 7.

Implemented today: User-Agent validation failing closed, path-traversal rejection, log redaction,
model content-boundary enforcement in both directions, native tool-call refusal, budget
enforcement before spend, and audit persistence of exact model bodies.

## 9. Known defects and limitations

1. The rate limiter is in-process. Multi-process ingestion requires the Redis-backed bucket
   because the SEC limit is aggregate across machines. BLOCKING for Stage 2 phase W-2. The Sprint 2 mirror
   ran as a single process precisely because of this.
2. Canonical grouping by role URI is verified on exactly one filing. Breadth validation across
   25 issuers and four eras precedes scale-out. BLOCKING for Stage 2 phase W-3.
3. Token estimation is a character-ratio heuristic, adequate for budget guards and relative
   comparison, not for billing reconciliation.
4. The provider catalog and pricing are unverified. BLOCKING for any cost commitment.
5. Authentication is a local single-user implementation. BLOCKING for any public deployment.
   See ADR-0014.
6. `packages/sec_identity/accession.py` sits at 79 percent statement coverage, the lowest of the
   implemented modules; the uncovered lines are error branches on malformed input.
7. The Alembic migration has NOT been applied to a live PostgreSQL. This environment has no
   PostgreSQL and its Docker daemon cannot start containers, so upgrade and downgrade were
   verified by offline DDL generation and by structural tests only. The two live tests skip with
   an explicit reason. BLOCKING for Sprint 3, and the first thing to run wherever a database
   exists.
