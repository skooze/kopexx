# techspecs.md — FinTek Technical Specification

THIS DOCUMENT DESCRIBES WHAT THE CODE CURRENTLY DOES.

> **CUT BACK TO TRANSPORT ON 2026-08-03.** The deterministic semantic parser, the application
> PostgreSQL persistence layer, its Alembic migrations, the DERA mirror and fact loader, and the
> accession document classifier were DELETED from the active tree — not deprecated, not moved,
> not retained as an oracle. Git history is the archive. What remains acquires, preserves,
> transports and validates; a user-selected parsing model determines what a filing means.
> Authoritative and not repeated elsewhere:
> `docs/adr/ADR-0017-delete-the-rejected-parser-and-application-persistence.md`, which builds on
> `docs/adr/ADR-0016-corpus-first-model-first-architecture.md`.
>
> **PHASE 1 COMPLETED 2026-08-03.** AWS identity is verified, all five approved candidate LABELS map
> to real provider models, and every one of them has answered a minimal invocation — the first model
> calls in this project's history, seven of them, USD 0.00023, no SEC content. The verified
> identifiers, regions, modalities, limits and prices live in ONE place,
> `docs/llm/bedrock-capability-snapshot.yaml`, and are not repeated here. Decision:
> `docs/adr/ADR-0018-verified-capability-snapshot-over-a-provider-adapter.md`.
>
> **PHASE 2 COMPLETED 2026-08-03.** The first SEC filings in this project's history have been sent
> to real models. A parser-only orchestration path, a durable evaluation store, a Bedrock runtime
> adapter, the four-role model router, a hash-locked prompt registry, generic output validation and
> a working parser-review UI all exist and run. Seven packages were added; the runtime dependency
> list did not grow. Decision:
> `docs/adr/ADR-0019-parser-review-application-over-a-framework.md`.
>
> **PHASE 2.1 COMPLETED 2026-08-03.** The assumption that one filing's parse must fit one
> provider response is WITHDRAWN. A model-directed multipart protocol exists and runs: the
> selected parsing model plans the division, one call produces each part, subparts and
> replanning after truncation are model-directed, reconciliation may create more work, and the
> backend assembles a mechanical INDEX over the exact responses. Blind continuation is
> prohibited and structurally impossible. One package was added; the runtime dependency list
> did not grow. Decision: `docs/adr/ADR-0020-model-directed-multipart-parsing.md`.
>
> **THE FIVE-MODEL PROOF IS INCOMPLETE AND THE REASON IS EXTERNAL.** One candidate produced a
> valid 24-part plan and four completed parts resolving 65 of 66 source references against the
> preserved bytes; the AWS IAM Identity Center session then expired mid-run and the remaining
> runs stopped. `docs/sprints/PHASE-0201-model-directed-multipart-parsing.md` section 7.
>
> **CORRECTED 2026-08-04, ADDITIVELY: THE PROOF FINISHED.** The paragraph above was true when
> written and the blocker was cleared by `aws sso login` on the host. All five candidates then ran
> the multipart protocol against the preserved 3M 10-K405 of 1996, and both multimodal candidates
> also ran an image-bearing Macy's 10-Q/A — seven runs, `USD 2.603827` measured. Plan sizes for one
> identical filing ranged from 5 parts to 28. `table_count` is ZERO in all seven.
>
> **PHASE 2.2 COMPLETED 2026-08-04, EXCEPT THE BENCHMARK RUN IT EXISTS TO ENABLE.** A mechanical
> source inventory and a completeness ledger now exist, so a parse can be measured against the
> FILING rather than against its own citations. The six-level anchor ladder replaced a three-level
> search. Two packages were added; the runtime dependency list did not grow. **NO MODEL WAS
> INVOKED** — measured Bedrock spend for the phase is `USD 0.00000000` — and the single-filing
> benchmark is BLOCKED: four of the five candidates can receive Apple's 10-Q
> `0000320193-25-000008` intact and running those four costs `USD 13.3745` against `USD 5.00`
> authorized. The fifth, GPT OSS 120B, cannot receive it at all. Decision:
> `docs/adr/ADR-0021-single-filing-completeness-measurement.md`. Record:
> `docs/sprints/PHASE-0202-bedrock-research-and-completeness-benchmark.md`.
>
> **STILL TRUE, AND THEY ARE NOT SMALL.** No application database exists. No Redis exists. No
> summary artifact, no image artifact and no chat session exists — Phase 2 and Phase 2.1 both ran
> the PARSING stage only, and invoking another raises. Multipart multiplies the number of PARSER
> calls and authorizes no other stage. Approval exists as a recorded judgement and activates no
> reuse. No parser has been selected, ranked or promoted. Prompt caching was investigated and is
> not available for any approved candidate. Nothing is deployed.

Sections marked `PLANNED` describe work that does not exist. `roadmap.md` is authoritative for
sequencing.

LAST SYNCHRONIZED WITH CODE: 2026-08-04, Phase 2.2.

VERIFICATION, measured locally on that date:

```
1,564 tests passing, 0 skipped        coverage 92.72 percent against an 85 percent gate
ruff format and lint clean            across `packages tests`
mypy clean                            119 source files under `packages`
```

`pip-audit`, `gitleaks` and the wheel, sdist and external-import checks are commit-time obligations
listed under the validation suite below. They are not restated as results here, because a result is
only true on the day it was measured.

**THE COUNT IN THIS BLOCK WAS STALE AND THE CORRECTION IS RECORDED RATHER THAN QUIETLY APPLIED.**
It read `1,253` while Phase 2.1 in fact finished at `1,261` — eight tests written and never counted
here, which is `rules.md` section 18 not being applied at the end of a phase rather than a defect in
anything the code does. Phase 2.2 added 202 new test functions across four new files, collecting as
247 cases, and `tests/unit/test_benchmark_review.py` adds 56 more, which is the whole of the
move from 1,261 to 1,564. No existing test was weakened,
disabled, skipped or deleted.

---

# 1. CURRENT STATE

## 1.1 Runtime packages — nineteen

None of them interprets meaning. That is the whole architecture, and it did not change when the
first filing was parsed, or when one parse became a dozen calls: the seven packages Phase 2 added
transport, orchestrate, preserve, prove and display, and the one Phase 2.1 added carries a plan
the MODEL wrote. Not one of them decides what a filing says.

**THE TWO PHASE 2.2 PACKAGES COUNT AND MEASURE, WHICH IS THE HARDEST PLACE TO KEEP THAT LINE.**
`source_inventory` says where a `table` tag sits and how many non-empty cells it holds; it does not
say the table is a balance sheet. `completeness` says a claimed interval resolves in the preserved
bytes and an inventory item is COVERED, UNRESOLVED, HUMAN_EXCLUDED or SILENTLY_OMITTED; it does not
say the parse is complete, and no enum in it carries a value that means semantically complete.

```
packages/sec_identity        CIK, accession and URL normalization — the single home       5 modules
packages/sec_client          HTTP with the shared rate limiter and throttle classification 5
packages/configuration       startup validation, the SEC User-Agent gate, review settings  4
packages/observability       structured logging, field redaction, correlation scope        3
packages/storage             object storage, key listing, atomic fsynced writes, hashing   3
packages/filing_discovery    qualifying-filing discovery against a SUPPLIED form set       4
packages/filing_acquisition  byte-exact acquisition, provenance, and the NON-CLASSIFYING   5
                             filed-document lister that reads EDGAR's SGML envelope
packages/llm_gateway         the model chokepoint, boundary validator, YAML 1.2 parser,   13
                             and the Bedrock Converse adapter — the ONLY AWS SDK import
packages/model_catalog       verified capabilities, label mapping, cost ceiling, and the   6
                             FOUR-ROLE ROUTER. No AWS import, no ARN, no region literal.
packages/evaluation_store    parent runs, child jobs, exact evidence, events, comments,    8
                             THREE independent state machines, the durable hierarchical
                             multipart task queue, and the versioned benchmark truth.
                             NOT the product database.
packages/source_transport    mechanical source-set assembly, local-first reuse, transport  8
                             disposition, lossless decoding, intact-source compatibility
packages/coverage_validation elastic reader, the SIX-LEVEL anchor ladder against the       6
                             preserved bytes, generic numeric signals. No COMPLETE verdict.
packages/prompt_registry     versioned, SHA-256 hash-locked prompts. A used version is     3
                             never edited; the hash is what makes that impossible.
packages/orchestrator        preflight, the THREE-CEILING durable spend journal, parser-   9
                             only execution, the multipart scheduler, the synthetic brief
                             compiler, the output-sizing policy, the catalog, and a
                             bounded in-process worker
packages/review_api          the review HTTP application on the standard library: router,  6
                             security policy, handlers, threaded server, assembly
packages/review_web          server-rendered pages, escaping, the two assets, the         13
                             multipart hierarchy, per-call and assembled views, the
                             completeness review surface where a person classifies one
                             filing's inventory, the parse hub, the contextual review
                             menu, the navigation and progress vocabularies, and the
                             assembled pane that is the parsed half of side-by-side for
                             a multipart parse. No framework, no bundler, no npm, no
                             build step.
packages/multipart           the MODEL-DIRECTED multipart envelopes, their generic         9
                             structural validation, safe carriage of a model-created
                             identifier, mechanical assembly, the effective-artifact
                             resolver, the structured-table reader, gap fingerprints
packages/source_inventory    the MECHANICAL denominator: members, visible text spans,       6
                             table elements and filed images, measured from the
                             preserved bytes. A validation instrument, never an input
                             filter — nothing here changes what a model receives
packages/completeness        the six-dimension status model, interval algebra, the         8
                             versioned human benchmark truth, the ledger and the
                             fourteen-condition mechanical gate. Its strongest verdict
                             is MECHANICAL_COMPLETENESS_CANDIDATE, which means a person
                             can now review it
```

## 1.2 Dependency graph — measured, not asserted

```
configuration        -> (none)
observability        -> (none)
storage              -> (none)
sec_identity         -> (none)
sec_client           -> configuration
llm_gateway          -> storage        (hashing, for provenance admission; imported locally)
filing_discovery     -> sec_identity
filing_acquisition   -> sec_identity, storage, source_transport (locally, to avoid a cycle)
model_catalog        -> llm_gateway    (the hardened YAML 1.2 parser, not reimplemented)
evaluation_store     -> llm_gateway, storage
source_transport     -> filing_acquisition, sec_identity, storage, llm_gateway
coverage_validation  -> llm_gateway
source_inventory     -> source_transport, storage
completeness         -> source_inventory, coverage_validation
prompt_registry      -> llm_gateway, storage
orchestrator         -> evaluation_store, source_transport, coverage_validation,
                        prompt_registry, model_catalog, llm_gateway
review_web           -> (none)
review_api           -> orchestrator, evaluation_store, coverage_validation, review_web,
                        configuration, storage, sec_client, model_catalog, prompt_registry,
                        source_transport, filing_acquisition, llm_gateway
```

No cycles. **No package imports a database driver, a cache client or a web framework**, and an
architecture test enforces it. The only provider SDK import is in
`packages/llm_gateway/providers/bedrock.py`, it is lazy, and boto3 is an OPTIONAL extra — so
ordinary CI does not install it at all.

`packages/configuration` gained a non-test caller in Phase 2: `packages/review_api/app.py` builds
every instance from validated settings. `packages/observability` still has none, and that is
recorded rather than hidden — the review server silences the standard library's access log
precisely because that log would carry query strings which `observability` exists to redact, and
wiring it is the change that closes this gap.

Both Phase 2.2 packages are wired in. `packages/orchestrator/service.py` calls
`source_inventory.build_inventory` and memoises the result per source set;
`packages/review_api/handlers.py` reads `packages/completeness` for the benchmark truth and its
mechanical suggestions; `packages/review_web/benchmark_view.py` reads both, and is the surface on
which a person turns a raw inventory into a REQUIRED SET one item at a time.

**`packages/multipart/gaps.py` AND `packages/multipart/tables.py` STILL HAVE NO NON-TEST CALLER.**
They are exported and tested and the scheduler does not read them yet. Stated rather than implied,
because a module with no caller is indistinguishable from a module that is wired in if nobody
writes it down.

## 1.3 Committed test infrastructure

```
five ORIGINAL SEC SOURCE documents        four inline-XBRL primary documents plus the 1994
                                          complete submission, every one hash-verified against
                                          the manifest on every run
four original FilingSummary.xml artifacts hash-verified against the manifest
tests/fixtures/filings/manifest.yaml      source URL, SHA-256 and byte count for every object
tests/fixtures/form_family.yaml           41 adjudicated forms, 22 included, 19 excluded
tests/fixtures/corpus_identity.yaml       issuer and co-registration identity cases
three transport HTML fixtures             two 403 bodies and one directory listing
```

**No derived parser output is committed any more.** The four `report-inventory.yaml` and four
`table-ownership.json` fixtures were the deterministic pipeline's own output; a test now fails if
either name reappears under `tests/fixtures/`.

## 1.4 Corpus evidence — dated Phase 0, reverified 2026-08-03

```
112 issuers            613 filings            6 transport eras
760,174,532 bytes preserved, 613 of 613 hash-verified, 0 missing, 0 hash mismatches
22 direct substantive form strings, 19 adjudicated exclusions, all 22 present in the corpus
0 duplicate (cik, accession) pairs   0 accession-to-CIK ownership mismatches
75 SIC industries      138 amendments         313 annual, 300 quarterly
187 filings carry images, 11 carry PDFs, packages range from 4 to 283 files
44 percent of primary documents exceed ~200,000 ESTIMATED tokens
```

A measurement of one sample on one date. Not a permanent constant.

## 1.5 Databases — none

```
fintek                    DOES NOT EXIST. Verified 2026-08-03: connecting with the configured
                          application URL returns FATAL: database "fintek" does not exist.
fintek_test               exists on the development host, 1 table, UNUSED
fintek_integration_test   exists on the development host, 25 tables, UNUSED
```

Nothing in this repository can reach any of them: no ORM, no engine, no driver dependency, no
migration, no test. The two disposable databases are host leftovers; removing them is host
administration and needs separate authorization.

## 1.6 What was deleted

| Deleted | Was |
|---|---|
| `packages/footnote_extractor` | renderer inventory, footnote candidates, `Note N —` heading parsing, inline-XBRL tagged spans, presentation linkbase |
| `packages/footnote_canonicalizer` | the five-stage grouping chain, item-disclosure exclusions, table OWNERSHIP, footnote completeness, footnote-schema persistence |
| `packages/table_parser` | original-filing table structure, header hierarchy, cell provenance |
| `packages/persistence` | 24 ORM tables, engine, URL resolution, disposable-database isolation |
| `migrations/`, `alembic.ini` | `0001_initial_control_plane_schema`, `0002_table_ownership` |
| `packages/dera_notes` | DERA discovery, mirror ledger, TSV, dimensions, normalize, validate, registration, loader, reconcile, report |
| `packages/filing_acquisition/inventory.py` | accession document classifier and its Item 601 role taxonomy |
| `scripts/` (all seven) | parser, migration, test-database and DERA entry points |
| `metric_definitions/` | curated concept priorities and the item-disclosure exclusion taxonomy |
| `prompts/footnote-summary/` | the footnote-summary prompt set |
| `artifacts/dera/` | byte-identical copies of ledgers that travel with the payloads in `var/dera/` |
| `docs/footnotes/`, parts of `docs/financial/`, `docs/sec/dera-notes.md`, `docs/architecture/components.md`, `docs/architecture/data-flows.md`, nine runbooks | specifications for the above |

Why each, once, in `docs/adr/ADR-0017`.

---

# 2. Implementation status by component

| Component | Package | Status |
|---|---|---|
| SEC identity normalization | `sec_identity` | IMPLEMENTED |
| Configuration and User-Agent validation | `configuration` | IMPLEMENTED, not yet wired to a caller |
| Rate limiting and throttle classification | `sec_client` | IMPLEMENTED |
| SEC HTTP client | `sec_client` | IMPLEMENTED |
| Object storage and hashing | `storage` | IMPLEMENTED (filesystem); S3 PLANNED |
| Structured logging, redaction, correlation | `observability` | IMPLEMENTED, not yet wired to a caller |
| Filing discovery and master-index reconciliation | `filing_discovery` | IMPLEMENTED |
| Filing acquisition, inline-XBRL era only | `filing_acquisition` | IMPLEMENTED |
| LLM content boundary, YAML 1.2, budget, audit | `llm_gateway` | IMPLEMENTED against a mock |
| Verified capability catalog, label mapping, cost ceiling | `model_catalog` | IMPLEMENTED — Phase 1 |
| Four-role model router | `model_catalog/routing.py` | IMPLEMENTED — Phase 2 |
| AWS identity and secret policy | governance + `tests/architecture` | IMPLEMENTED; the only AWS code is the Bedrock adapter, and boto3 is an OPTIONAL extra |
| Filed-document lister, non-classifying | `filing_acquisition/documents.py` | IMPLEMENTED — Phase 2 |
| Real provider adapter | `llm_gateway/providers/bedrock.py` | IMPLEMENTED — Phase 2 |
| Source-set assembly, raw-first reuse, compatibility | `source_transport` | IMPLEMENTED — Phase 2 |
| Coverage validation of model output | `coverage_validation` | IMPLEMENTED — Phase 2 |
| Versioned, hash-locked prompts | `prompt_registry` | IMPLEMENTED — Phase 2 |
| Parent runs, child jobs, evaluation evidence | `evaluation_store` | IMPLEMENTED — Phase 2 |
| Preflight, spend journal, parser-only execution | `orchestrator` | IMPLEMENTED — Phase 2 |
| Parser-review API and pages | `review_api`, `review_web` | IMPLEMENTED — Phase 2 |
| Parsed evaluation artifacts | `coverage_validation`, `evaluation_store` | IMPLEMENTED — Phase 2, provisional |
| Model-directed multipart protocol and mechanical assembly | `multipart` | IMPLEMENTED — Phase 2.1 |
| Durable hierarchical task queue and the multipart scheduler | `evaluation_store`, `orchestrator` | IMPLEMENTED — Phase 2.1 |
| Mechanical source inventory: members, spans, table elements, images | `source_inventory` | IMPLEMENTED — Phase 2.2 |
| Completeness status model, ledger, interval algebra, mechanical gate | `completeness` | IMPLEMENTED — Phase 2.2 |
| Six-level source-anchor ladder against the preserved bytes | `coverage_validation/references.py` | IMPLEMENTED — Phase 2.2 |
| Completeness review surface: classify one filing's inventory | `review_web/benchmark_view.py` | IMPLEMENTED — Phase 2.2 |
| Versioned human benchmark truth, stored per accession and source hash | `completeness/truth.py`, `evaluation_store` | IMPLEMENTED — Phase 2.2 |
| Effective-artifact resolution, structured tables, gap fingerprints | `multipart` | IMPLEMENTED — Phase 2.2; `tables.py` and `gaps.py` have no caller yet |
| Pre-transport reservation release | `llm_gateway`, `orchestrator/spend_journal.py` | IMPLEMENTED — Phase 2.2 |
| Navigation, breadcrumbs, panel modes, link destinations | `review_web/nav.py` | IMPLEMENTED — Phase 3 |
| The contextual review menu for one parse or filing | `review_web/panel.py` | IMPLEMENTED — Phase 3 |
| Progress words, and the only place a count becomes one | `review_web/progress.py` | IMPLEMENTED — Phase 3 |
| The parse hub: the seven questions asked of one parse | `review_web/hub_view.py` | IMPLEMENTED — Phase 3 |
| The filings index and the judgements record | `review_web/filings_view.py` | IMPLEMENTED — Phase 3 |
| The assembled pane: a multipart parse beside its filing | `review_web/multipart_view.py` | IMPLEMENTED — Phase 3 |
| The opened trail — scratch, never evidence | `evaluation_store/attention.py` | IMPLEMENTED — Phase 3 |
| The optional image, summary and analysis stages | `orchestrator/service.py`, `prompts/parser/stage-*` | IMPLEMENTED — Phase 3; verified against the MOCK provider only |
| Which adapter answered an attempt | `evaluation_store/records.py` | IMPLEMENTED — Phase 3 |
| Single-filing completeness benchmark run | — | BLOCKED — Phase 2.2, on a cost-ceiling decision |
| Image / summary / chat artifacts | — | PLANNED, Phase 3 |
| Persistence, approval gate, Redis cache | — | PLANNED, Phase 4 |

Reserved package names. **These directories do not exist.** Sprint 1 created eighteen packages
containing only a docstring, which reserved names twenty sprints ahead of their code and made two
architecture tests pass while scanning nothing. Each is created in the change that writes its first
module, and an architecture test rejects an empty stub.

| Reserved name | Planned path | Phase |
|---|---|---|
| Artifact persistence and approval | `packages/artifact_store` | 4 |
| Deep Analysis | `packages/deep_analysis` | 7 |

**Every Phase 2 reservation was taken up, and two of them landed somewhere else.** `apps/api` and
`apps/web` were reserved for a web surface; the Phase 2 parser-review application was built as
`packages/review_api` and `packages/review_web` instead, and the reason is tooling reach rather
than preference. Everything under `packages/` is formatted, linted, type-checked, coverage-measured
and scanned by the architecture guards, and it ships in the wheel through one `include` pattern.
A top-level `apps/` tree would have needed every one of those extended to reach it, and the first
guard nobody remembered to extend is the guard that stops holding. `apps/api` and `apps/web` remain
reserved for the Phase 6 beta UI, which is a different product surface with different users.

---

# 3. Implemented components in detail

### 3.1 `packages/sec_identity` — IMPLEMENTED

RESPONSIBILITY. The single home for CIK normalization, accession normalization and SEC URL
construction. No other package may reimplement these; an architecture test enforces it.

PUBLIC INTERFACE. `parse_cik`, `cik_padded`, `cik_archive`, `cik_submissions_stem`,
`parse_accession`, `accession_dashed`, `accession_undashed`, `accession_filer_prefix`,
`is_valid_accession`, `submissions_url`, `submissions_shard_url`, `filing_folder_url`,
`primary_document_url`, `complete_submission_url`, `filing_xbrl_zip_url`, `filing_index_json_url`,
`extracted_instance_url`, `quarterly_index_url`, `company_tickers_exchange_url`.

DEPENDENCIES. Standard library only. This package is a leaf and must stay one.

INVARIANTS.
- `data.sec.gov` receives the ten-digit padded CIK; `www.sec.gov/Archives` receives the unpadded
  integer. The wrong form costs a 301 or a 404 against a single-digit-per-second budget.
- The dashed accession is canonical; the undashed form is a folder segment only.
- **The accession prefix is the FILING AGENT's CIK and is never the issuer.** 361 of 613 corpus
  filings carry an agent prefix; using it as identity produces 361 false mismatches.
- An empty primary-document name never produces a URL. SEC answers the resulting bare folder URL
  with HTTP 200 and a directory listing, which is a silent corruption rather than an error.

SEMANTIC BOUNDARY. None of it reads a filing. Every function is a regex or a format string over an
identifier SEC assigned.

TESTS. 15 in `tests/unit/test_sec_identity.py`, including the filing-agent prefix trap and the
empty pre-2001 primary document.

### 3.2 `packages/configuration` — IMPLEMENTED; its caller arrived in Phase 2

RESPONSIBILITY. Load and eagerly validate settings so a misconfiguration fails at startup rather
than after generating traffic that will be blocked.

PUBLIC INTERFACE. `Settings.from_env`, `SecAccessSettings`, `StorageSettings`, `LlmSettings`,
`validate_user_agent`, `is_valid_user_agent`, `DENYLIST_FRAGMENTS`.

INVARIANTS. A User-Agent must exist, must contain a contact email, and must not match a library
default. Global rate within `(0, 10]`. Throttle cooldown at least 600 seconds.

DEFECT FIXED IN PHASE 1. `LlmSettings.region` defaulted to a hardcoded `"us-east-1"`. That is the
form-family defect with a bill attached: a guessed value in runtime source, no reviewed contract
behind it, and a silent success when the operator sets nothing. Phase 1 made the cost concrete — one
of the five approved candidates is not offered in `us-east-1` at all, so an unset region would have
reported a real model as unavailable with nothing in the code to point at. The default is gone,
`AWS_REGION` has no fallback, and a non-mock provider with no region raises
`MissingModelRegionError` at construction. The mock still needs none, so the suite keeps its zero
environmental preconditions.

KNOWN GAP. `LlmSettings` carries `standard_model_id` and `analysis_model_id`, a two-role shape that
predates the four-role product. It is deliberately NOT replaced with a guessed four-role shape:
roles resolve through the reviewed capability snapshot in `packages/model_catalog`, and a parallel
set of identifier fields here would give the same fact two homes.

TESTS. 10 in `tests/unit/test_configuration.py`.

### 3.3 `packages/sec_client` — IMPLEMENTED

RESPONSIBILITY. Pace all SEC traffic, classify refusals correctly, and be the only component that
issues an HTTP request to an SEC host.

PUBLIC INTERFACE. `SecHttpClient` with `get_text`, `get_bytes`, `head`, `download`; `FetchResult`;
`SecRateLimiters`, `TokenBucketLimiter`, `Clock`, `FakeClock`; `classify_403`, `raise_for_403`,
`extract_reference_id`, `looks_like_directory_listing`; and the typed error hierarchy.

INVARIANTS.
- `www.sec.gov` and `data.sec.gov` share one bucket, because the documented limit is aggregate.
  `efts.sec.gov` has its own slower bucket.
- **A rate-threshold 403 triggers one full 600-second cooldown, never exponential backoff.**
  Backoff starting at 1 second extends the block and is prohibited.
- An undeclared-automation 403 is a configuration error: raise, never retry.
- A directory listing is never treated as filing content.
- A download writes to a temporary path and is renamed only after every assertion passes.

CONTENT ASSERTIONS, all rejecting rather than storing: an HTML page where content was expected; a
directory listing; wrong magic bytes for an expected ZIP; a body shorter than its declared
Content-Length; a ZIP with no members; a ZIP whose member fails CRC.

KNOWN DEFECT FIXED IN SPRINT 1. The token bucket compared `tokens >= 1.0` exactly. After sleeping
the computed delay, refill could land a fraction below 1.0 in binary floating point, so the acquire
loop spun forever on ever-smaller deltas. A nanotoken epsilon fixes it. Found by the suite hanging,
not by review.

SCALING. In-process. Exactly one client may run at a time because the SEC limit is aggregate across
machines. A shared limiter is required before multi-process ingestion.

TESTS. 9 in `test_sec_client.py` using an injectable fake clock, 15 in `test_sec_http_client.py`
using `httpx.MockTransport`, including one asserting the cooldown is a single 600-second pause
rather than a backoff sequence.

PROVEN IN PRODUCTION. Executed a 78-package, 27,228,877,737-byte mirror with zero failures and zero
throttle events, and acquired the 613-filing research corpus with zero throttle events.

### 3.4 `packages/storage` — filesystem backend IMPLEMENTED; S3 PLANNED

RESPONSIBILITY. Durable storage for raw filings and, later, exact model request and response
bodies, with content hashing.

PUBLIC INTERFACE. `ObjectStore`, `FilesystemObjectStore`, `StoredObject`, `sha256_bytes`,
`sha256_text`, `sha256_stream`, `sha256_file`.

INVARIANTS. An object key is relative and never escapes the store root. Writes are atomic via a
temporary file and replace, so a killed writer leaves no partial object under the final key. Every
stored object records a SHA-256.

SECURITY. Path traversal and absolute keys are rejected rather than silently reinterpreted.

TESTS. 6 in `tests/unit/test_storage.py`.

### 3.5 `packages/observability` — IMPLEMENTED, no non-test caller

RESPONSIBILITY. Structured logging with correlation identifiers and centralized field redaction.

PUBLIC INTERFACE. `get_logger`, `log_event`, `configure_logging`, `StructuredFormatter`,
`REDACTED_FIELDS`, `correlation_scope`, `new_correlation_id`, `get_correlation_id`,
`set_correlation_id`, `reset_correlation_id`.

SECURITY-INVARIANT. **Filing text and model-visible payload bodies are never logged.** They may be
very large and may carry content a prompt-injection attempt placed inside a filing. Bodies go to
object storage and are referenced by URI and hash. Redaction is centralized so a new logger cannot
forget it. The AWS credential names are in the redaction set before any AWS integration exists, on
purpose: a credential that reaches a log has already been disclosed, and a log is the one place
nobody thinks to check.

TESTS. 12 in `tests/unit/test_observability.py`, new in this cleanup — the package previously had
none at all. The redaction test is parametrized over EVERY entry in `REDACTED_FIELDS`, so adding a
name without wiring it in cannot pass, and one test asserts an unlisted field IS emitted so the
others cannot pass vacuously.

### 3.6 `packages/filing_discovery` — IMPLEMENTED

RESPONSIBILITY. Which filings an issuer has, before anything is downloaded, and an independent
reconciliation against the quarterly master index.

PUBLIC INTERFACE. `discover_filings`, `issuer_profile`, `DiscoveredFiling`, `classify_era`,
`is_amendment`, `parse_master_index`, `reconcile_against_master`, `quarters_between`,
`raise_if_incomplete`.

INVARIANTS.
- **The qualifying form set is a REQUIRED argument with no default**, matched on the EXACT filed
  string with no normalization, no case folding and no amendment-suffix stripping. An empty set is
  rejected rather than silently discovering nothing.
- SEC-INVARIANT: `filings.recent` caps at 1,000 entries. Apple hits that cap exactly with 1,238
  further filings in an overflow shard reaching back to 1994. Reading only `recent` returned 45 of
  Apple's 134 qualifying filings when measured live.
- A shard boundary can repeat an entry; deduplication is by accession.
- Era classification is behavioural, not cosmetic: inline XBRL carries everything in one
  `-xbrl.zip`; older XBRL needs the primary document separately; pre-2001 filings are PEM-armored
  inside the complete submission and have no primary document name at all.
- A malformed submissions payload raises. A shape change absorbed quietly is indistinguishable
  from an issuer that filed nothing.

DEFECT FIXED IN THIS CLEANUP. This package shipped `ANNUAL_FORMS = ("10-K", "10-K405", "10-KSB")`
and `QUARTERLY_FORMS = ("10-Q", "10-QSB")` for four sprints. EDGAR files `10KSB` and `10QSB`
unhyphenated, so that filter matched none of the small-business family and none of the transition
family — while a committed contract adjudicating all 41 observed strings sat beside it. The
reconciliation that existed to catch a discovery gap applied the same filter, so both sides agreed
and reported a complete history. An architecture test now parses runtime source and fails if a form
literal is written back into it. ADR-0017 section 8.

TESTS. 18 in `tests/unit/test_filing_discovery.py`, reading the qualifying set out of
`tests/fixtures/form_family.yaml` so code and contract cannot drift apart.

### 3.7 `packages/filing_acquisition` — IMPLEMENTED, inline-XBRL era only

RESPONSIBILITY. Download a filing's source objects and preserve them byte-for-byte with provenance.

PUBLIC INTERFACE. `acquire_filing`, `plan_inline_xbrl`, `AcquiredObject`, `AcquisitionResult`,
`storage_key`, `SUPPORTED_ERAS`, and the typed error hierarchy.

INVARIANTS. Every acquired object records source URL, SHA-256, byte count and acquisition
timestamp. Bytes are never transformed on the way in.

KNOWN GAP, and it is a real one. `plan_inline_xbrl` acquires five objects — primary document, XBRL
package, SEC-extracted instance, `FilingSummary.xml`, schema. **That is not the filed submission.**
Apple's FY2025 10-K accession lists seventeen filed documents, including a description of
securities, a subsidiaries list, an auditor consent, three officer certifications and two graphics.
The module that listed them was deleted in this cleanup because it also CLASSIFIED them into a
Regulation S-K role taxonomy and ruled that a courtesy PDF duplicated the primary document, which
suppressed a filed source range on a semantic judgement. A non-classifying replacement is Phase 2a
work and is named in the roadmap.

TESTS. 12 in `tests/unit/test_filing_acquisition.py`.

### 3.8 `packages/llm_gateway` — IMPLEMENTED against a mock

RESPONSIBILITY. The only path from FinTek to a language model. Owns payload compilation, boundary
validation in both directions, budget enforcement before spend, provider invocation, safe parsing,
cost calculation and audit.

PUBLIC INTERFACE. `LlmGateway`, `Budget`, `GatewayResult`, `InvocationRecord`, `compile_yaml`,
`compile_plain_text`, `CompiledPayload`, `reject_native_tools`, `validate_plain_text`,
`validate_yaml_text`, `enforce`, `BoundaryReport`, `ContentFormat`, `Violation`, `parse_yaml`,
`require_mapping`, `require_string`, `to_yaml`, `estimate_tokens`, `PricingRegistry`,
`ModelPricing`, `default_registry`, and the typed error hierarchy.

WHAT LEFT IN THIS CLEANUP. `FootnoteSummaryRequest`, `SourceBlockPayload`, `TablePayload` and
`compile_footnote_summary_request` — a request contract built around canonical footnotes, which was
the deleted parser's output shape. `ModelCapabilities` and `SerializationComparison`, both dead:
zero callers, zero tests. Four footnote identifiers left the YAML quoting rule; the generic `id` and
`number` keys already cover whatever labels a filing or a model produces. The mock provider's canned
response was a `footnote-summary-v1.0.0` document with a fixed taxonomy of topics, accounting
policies and risk categories, which quietly made the mock the de facto response schema; it is now a
minimal well-formed YAML mapping that asserts no contract.

**A PROVISIONAL request and response contract now exists, DERIVED from what real models returned.**
The request is a plain-text instruction plus preserved `OriginalSourceBlock`s admitted by
provenance; the response is the minimum envelope in `packages/coverage_validation` — artifact,
document, nodes, unresolved, metadata — read elastically, with unknown model-returned keys
preserved and no node-type vocabulary required. It is PROVISIONAL and stays so: roadmap.md 2c says
the final contract is derived from what models return, and three filings is not enough to fix one.

INVARIANTS.
- Model-visible SYNTHETIC content is unmarked plain text or exactly one unfenced YAML 1.2 document.
  Only the compiler produces it; the boundary validator is a backstop that catches bypasses.
- ORIGINAL-SOURCE EXCEPTION: a preserved SEC artifact is admitted by PROVENANCE and sent intact in
  whatever syntax SEC published, never rewritten into YAML and never routed through the compiler.
- Native tool calling is refused. It requires JSON Schema definitions and yields JSON arguments,
  both prohibited at the boundary.
- Budgets are checked BEFORE invocation, never reconciled after.
- Exact request and response bodies are preserved.
- Every identifier is quoted.
- No provider SDK outside `providers/`, enforced by an architecture test.

DEFECT FIXED IN THIS CLEANUP. The pre-spend budget guard added `len(system_text) // 4` to a payload
estimate computed at 3.8 characters per token — one guard, two different unverified ratios, and the
system prompt under-counted. Under-counting is the unsafe direction for a check that runs before
the money is spent. Both now use `estimate_tokens`.

YAML PARSER, PINNED. ruamel.yaml, `YAML(typ="safe", pure=True)`, YAML 1.2 core schema. PyYAML is not
used because it implements YAML 1.1.

THREE VERIFIED FACTS THE DESIGN RESTS ON.
- YAML 1.2 does not coerce `yes`, `no`, `on`, `off` to booleans; YAML 1.1 does.
- YAML 1.2 parses an unquoted `0000320193` as the integer `320193`, destroying a CIK. Identifiers
  are always quoted, and `require_string` refuses one that arrived unquoted.
- Alias expansion was UNBOUNDED before Sprint 2. A five-line document expanded to 59,049 leaf
  nodes. A pre-parse anchor and alias budget rejects it, because a post-parse check runs after the
  allocation has already happened.

UNVERIFIED CONSTANT, disclosed. `max_output_tokens` defaults to 4096 in `gateway.invoke` and
`providers/base`. It is a REQUEST cap chosen by the caller, not a claim about any model's real
output limit — no model has been reached and no limit is known.

TESTS. 26 in `test_llm_boundary.py`, 16 in `test_yaml_parser.py`.

### 3.9 `packages/model_catalog` — IMPLEMENTED in Phase 1, half of its eventual scope

RESPONSIBILITY. Answer three questions about a user-facing model LABEL without guessing at any of
them: does it resolve to exactly one real provider model, may it fill this role in this region, and
what would an invocation cost at worst before it is made.

PUBLIC INTERFACE. `load_snapshot`, `CapabilitySnapshot`, `ResolvedModel`, `ModelCapability`,
`ModelRole`, `Availability`, `Mapping`, `SmokeTransport`, `SmokeInstruction`, `PriceInputs`,
`SpendLedger`, `RetryBudget`, and the typed error hierarchy.

DEPENDENCIES. `packages/llm_gateway`, for the hardened YAML 1.2 safe parser only. That parser is
the single home for YAML parsing and rules.md section 5 forbids a second copy.

INVARIANTS.
- **No model identifier, region, limit or price appears in this source.** Every one is supplied
  from `docs/llm/bedrock-capability-snapshot.yaml`, and an architecture test parses shipped source
  and fails on a provider identifier or region literal. Same discipline, same reason, as the
  qualifying-form set.
- **There is no default snapshot path and no fallback.** A fallback is how a stale catalog keeps
  answering after the real one has moved.
- **`multimodal` is validated against `image_verified` in the constructor.** A record cannot carry
  the badge without a real image invocation behind it. A published modality flag is a claim.
- **Resolution raises rather than substituting.** No default model, no fallback, no widened region,
  no downgraded role, no choice between ambiguous matches — rules.md section 21 rules 8, 9, 10.
- **A disabled candidate is RETURNED with a concrete reason, not filtered away.** A candidate that
  silently vanishes from a selector is indistinguishable from one that was never approved.
- **Money is `Decimal`, converted through `str`.** `Decimal(0.00015)` is
  `0.000149999999999999993145...`, which is what the binary double holds; over a corpus that stops
  being invisible.
- **The cost reservation is charged immediately and settled against measured usage.** Charging only
  on success would let a run of billable rejections walk past the ceiling.
- **One retry, and only for a transient reason.** Retrying until a model says what you wanted is
  prompt tuning with the measurement removed.

THE FOUR-ROLE ROUTER ARRIVED IN PHASE 2, in `routing.py`, completing the package. `route` resolves
one label to something invocable and DISCLOSES a cross-region route rather than performing one
quietly; `route_selection` returns one entry per SELECTED role, so a blank image, summary or
analysis selector produces no entry and therefore no stage — the absence of the entry IS the
absence of the stage, and there is no flag anywhere saying so. `selector_entries` returns every
candidate including the unavailable ones, each carrying a concrete reason, because a candidate that
vanishes from a dropdown is indistinguishable from one that was never approved.

`verified_regions` became an ORDERED TUPLE rather than a frozenset for this. The router picks the
first verified region when the preferred one is absent, and a set would make that choice depend on
hash ordering — a different region on a different interpreter run, and an unreproducible bill.

TESTS. 50 in `tests/unit/test_model_catalog.py`, all hermetic, plus 12 repository guards in
`tests/architecture/test_phase1_aws_boundary.py`.

---

# 4. Repository structure

```
packages/        19 runtime libraries, enumerated in section 1.1
prompts/         versioned .txt and .yaml, never .md — deep-analysis only
tests/           unit, architecture, fixtures
docs/            architecture, sec, llm, deep-analysis, api, data-dictionary, testing,
                 operations, runbooks, adr, sprints, security
var/             GITIGNORED. Preserved SEC objects, the 613-filing research corpus, the DERA
                 mirror, and the offline corpus tools. Not part of the distribution.
apps/            api, worker, web                          PLANNED
```

**There is no `scripts/` directory and no `migrations/` directory.** Every script was an entry
point for the deterministic parser, the application database or the DERA loader.

### 3.10 `packages/multipart` — IMPLEMENTED in Phase 2.1

The model-directed multipart protocol: reading the envelopes a model returns, checking their
STRUCTURE, carrying a model-created identifier safely, and assembling a mechanical index.

```
envelopes.py    read_plan, read_part, read_amendment, read_replan. Elastic: every unknown key
                survives in `extra`, a missing envelope key is a FINDING and never a refusal,
                and an unrecognised part status is preserved exactly and treated as unfinished.
identity.py     a model-created identifier is returned UNCHANGED, or refused with a reason —
                empty, over 200 characters, or carrying a control character. `storage_token`
                derives a filesystem-safe rendering whose digest guarantees that two distinct
                identifiers can never collide.
validation.py   plan, part and assembly validation. THREE conditions stop work, because each
                makes the QUEUE impossible: no schedulable part, a duplicate identifier, a
                dependency cycle. Everything else is a finding on a result that still gets
                scheduled, stored and reviewed.
assembly.py     order by the model's `order`, nest by the model's `parent_part_id`, link, count,
                aggregate, present. Never rename, merge, move, reassign or drop.
```

**WHAT IT WILL NEVER CONTAIN.** A vocabulary of part types. A required hierarchy. A minimum or
maximum part count. A fixed set of node types, table shapes or relationship names. An architecture
test fails the build if a filing-section name appears as an evaluated literal anywhere in the
multipart surface.

`AssemblyStatus` has three members and none of them is `COMPLETE`: `INCOMPLETE_WORK`,
`RECONCILIATION_UNRESOLVED`, `MECHANICALLY_ASSEMBLED`. Mechanical assembly, model-declared
completion, source-reference coverage and human approval are carried as four separate claims.

### 3.11 The multipart queue and orchestration — IMPLEMENTED in Phase 2.1

```
evaluation_store/queue_states.py   11 task types, 14 durable states, and the transition table.
                                   TRUNCATED is terminal by construction, so a truncated attempt
                                   can never be reopened. FAILED and INTERRUPTED reopen only to
                                   READY, and only through an explicit user action. The child
                                   job's own INTERRUPTED reopens the same way, to RUNNING, so a
                                   parse that is resumed and finished can actually reach review.
evaluation_store/tasks.py          the durable task record: dependencies and their policy, the
                                   model-created identifiers verbatim, the billable identity,
                                   attempts, reservation, settled cost, evidence names.
orchestrator/multipart_service.py  the scheduler and executor. One task at a time, synchronous,
                                   every result durable before the next begins.
orchestrator/briefs.py             the synthetic YAML brief. Every semantic word in one came
                                   from a model on an earlier call.
orchestrator/sizing.py             the cap handed to the provider, the target the model is told,
                                   and the deliberate headroom between them.
```

**Operational limits, never statements about filings**: recursion depth 4, reconciliation cycles 3,
format repairs per artifact 1, automatic retries per attempt 1.

**FOUR MORE ARRIVED IN PHASE 2.2, AND THEY CLOSE A HOLE THAT HAD NO BOTTOM.** There was no limit on
part count at all. Phase 2.1 measured plans of 5, 12, 24, 27 and 28 parts for ONE identical filing —
a 5.6x spread from the same bytes on the same day — and nothing in the code would have stopped 280.
The only economic bound was `filing_budget_usd`, which stops a run by refusing to pay rather than by
noticing the shape of the work, and the only structural bound was a `max_steps=400` DEFAULT
PARAMETER on `drive` that no setting could reach and no page displayed.

```
max_new_parts_per_cycle   20   the remainder of a larger proposal is left unqueued with the
                               reason recorded. It is not renamed, dropped or silently deferred
soft_part_threshold       64   the branch PAUSES with its projected cost and its new-versus-
                               repeated gap split visible. An explicit user action resumes it
hard_part_ceiling        100   automatic scheduling stops for good. Every artifact already
                               bought is preserved and the job is marked for human review
no_progress_tolerance      1   how many consecutive reconciliation cycles may create no new
                               unique work before the loop stops. DECLARED AND VALIDATED; the
                               scheduler does not consult it yet, and the gap fingerprints in
                               `packages/multipart/gaps.py` that would feed it have no caller
```

**A LOGICAL PART IS A PART TASK OR A SUBPART TASK, counted once.** A format repair is not one — it
produces no new coverage, it replaces an artifact — and neither is a reconciliation call. Counting
either would fire the ceiling on work that is not part explosion.

**NONE OF THE FOUR IS A STATEMENT ABOUT A FILING.** A part count is a property of the model reading
it, which is what a 5.6x spread on identical bytes means. These bounds say what this system will pay
for without being asked again; `rules.md` section 21 rule 19 keeps the question of how many parts a
10-Q has with the model.

**Three cost ceilings, tightest wins**: cumulative, phase, and one filing's own parse. A refusal
PAUSES the branch with the reason visible; nothing is shrunk, dropped or downgraded to fit.

**A RESERVATION IS NOW RELEASED WHEN, AND ONLY WHEN, TRANSPORT IS PROVEN NOT TO HAVE HAPPENED.**
`packages/llm_gateway/errors.py` gained `CredentialResolutionError`, a `ProviderError` subclass
carrying `transport_attempted=False`; `ProviderError` itself gained `transport_attempted`,
defaulting to `True`. **The asymmetry is deliberate.** Assuming a request was sent when it was not
merely holds ceiling that could have been used. Assuming it was not sent when it was releases money
that was really spent, and a ceiling enforced against a number smaller than the bill is not a
ceiling. `providers/bedrock.py` raises the new type for an eleven-name frozenset of credential
exceptions — `TokenRetrievalError`, `UnauthorizedSSOTokenError`, `NoCredentialsError` and the rest.

`orchestrator/spend_journal.py` gained `release()` and `unsettled()`. **The journal stays
append-only**: a RELEASE entry carries `amount_usd 0` and `released_usd` equal to the reservation,
so it contributes exactly the negative of the reservation to `sum(amount - released)` and no total
needed different arithmetic. Nothing is edited and nothing is deleted. A release REQUIRES evidence
text and refuses without it.

`unsettled()` is what found the Phase 2.1 accounting error. **Twelve task ids hold unsettled
reservations totalling `USD 0.24197085`**, not the four totalling `USD 0.10396815` that the
Phase 2.1 record states. Eleven are the same credential failure, `USD 0.22590990`, and the four
named earlier are a subset of them. The twelfth is a different defect: a task that SUCCEEDED, with
real usage and a real provider request id, holds TWO reservations of `USD 0.01606095` and one
settlement — it was interrupted after reserving, resumed, and reserved again, and only the later
entry settled. Recorded additively here and in `roadmap.md` section 2.2g; the Phase 2.1 record is
not rewritten.

### 3.12 `packages/source_inventory` — IMPLEMENTED in Phase 2.2

RESPONSIBILITY. Measure the FILING, before any model is invoked, so that what a parse omitted in
silence can be seen at all.

THE DEFECT IT EXISTS TO CLOSE. Phase 2.1 could report that 352 of 364 model-emitted source
references resolved against the preserved bytes. **It could not report what fraction of the filing
that represented**, because a source region a model never cited never entered the count. A reference
rate measures a model's own citations and says nothing about what it left out.

```
records.py    MemberRecord, TextSpan, TableElement, TableCell, ImageRecord, HiddenReason,
              FilingInventory. Every span carries its member, its offsets into the original
              bytes, whether it is visible, and — when it is not — WHY
markup.py     walk_markup, plain_text_spans, normalize_text. A tolerant reader for SGML, HTML
              and XHTML alike, because malformed markup is normal before 2005
images.py     media_type and dimensions read from the BYTE SIGNATURE, never the extension
inventory.py  build_inventory over a SourceSet: 63 members in 0.4 seconds on the benchmark filing
errors.py     MarkupUnreadableError, ImageUnreadableError, SourceInventoryError
```

INVARIANTS.
- **It is a validation instrument and NOT an input filter.** The selected parsing model still
  receives the complete compatible source set intact, in filed order, hash-verified, on every
  invocation. Nothing here narrows, projects, slices or reorders what is sent, and visible-content
  projection remains an unapproved research option under `rules.md` section 21 rule 7.
- **It measures and does not adjudicate.** An offset, a length, a hash, an element name, a grid
  position and an image header field are transport facts, which `rules.md` invariant 14 permits.
  Whether a span is a risk factor, whether a table is a financial statement or a layout device, and
  whether an image is a chart or a logo are decided by the model with source evidence and overruled
  by a human reviewer — never here.
- **A hidden span is recorded with its reason, never dropped.** The benchmark filing's inline-XBRL
  hidden-fact block is one 56,644-character span carrying `display:none`; it is excluded from the
  visible denominator WITH that reason attached, which is a transport observation rather than a
  judgement about content.
- **Table elements are classified by BYTES ONLY.** On the benchmark filing: 18 carry 20 or more
  non-empty cells, 8 carry no non-whitespace character at all, 7 are byte-identical to an earlier
  element, 0 are nested. None of those four counts is a claim about what any table holds.

DEPENDENCIES. `packages/source_transport` for the member set and its dispositions, and
`packages/storage` for hashing. Standard library otherwise; no dependency was added.

TESTS. 75 test functions in `tests/unit/test_source_inventory.py`.

### 3.13 `packages/completeness` — IMPLEMENTED in Phase 2.2

RESPONSIBILITY. Say what a parse accounted for, measured against the mechanical inventory, in a
shape that cannot be misread as a score.

```
status.py     SIX INDEPENDENT DIMENSIONS, never one boolean: TransportState, SerializationState,
              ConvergenceState, SourceCoverageState, TableState, ImageState, plus HumanReadiness
intervals.py  Interval, merge, overlaps, gaps, covered_length. Two resolved quotes bound an
              interval in the preserved bytes; the union of every part's intervals against the
              span inventory is a coverage figure with a real denominator underneath it
truth.py      the VERSIONED human benchmark truth for ONE filing — REQUIRED_SPAN, EXCLUDED_SPAN,
              REQUIRED_TABLE, EXCLUDED_TABLE, REQUIRED_IMAGE, EXCLUDED_IMAGE — plus `suggest`,
              which proposes and never decides
ledger.py     build_ledger and resolve_claims. FOUR DISPOSITIONS PER ITEM: COVERED, UNRESOLVED,
              HUMAN_EXCLUDED, SILENTLY_OMITTED
tables.py     validate one structured table against the source element it names
gate.py       the FOURTEEN-condition mechanical candidate gate, conjunctive
```

INVARIANTS.
- **No enum here has a value meaning SEMANTICALLY COMPLETE**, and none ever will. The strongest
  value backend code may set in `HumanReadiness` is `READY_FOR_REVIEW`. The gate's strongest verdict
  is `MECHANICAL_COMPLETENESS_CANDIDATE`, which means the result carries enough evidence to undergo
  human completeness review. `HUMAN_APPROVED_COMPLETE_FOR_THIS_FILING` is set by a reviewer and by
  nothing else, and is scoped to one filing, one source hash, one model, one model version, one
  region or profile, one prompt version, one settings set and one protocol.
- **SILENTLY_OMITTED is the number this package exists to produce**, and silence is not a
  disposition. An inventory item that no coverage claim, no structured table and no resolved
  reference reaches, and that no human excluded, is reported as omitted rather than left uncounted.
- **Fourteen conditions, all necessary, and no threshold.** A weighted score would let a strong
  showing on twelve dimensions outvote a silently omitted financial statement. Each condition is a
  distinct way a parse can be UNREVIEWABLE, and none substitutes for another. Condition 8 is why a
  budget-paused branch cannot be a candidate: no scheduled required job may remain nonterminal.
- **Nothing validates a table's MEANING.** Not the title, not the type, not the unit, not the period
  label, not whether the header row is really a header. `validate_table` checks that the element
  exists, the member was submitted, the grid has no collision, and every cell's text occurs in that
  element's cells. A cell that is neither in the source nor declared unresolved is a cell supplied
  from somewhere other than this filing, and that is the one thing it refuses. A validator that
  checked `unit` against a list of units would be the first brick of the universal filing taxonomy
  `rules.md` section 21 rule 2 forbids.

DEPENDENCIES. `packages/source_inventory` for the denominator and `packages/coverage_validation` for
resolved references. It reads a structured table by attribute rather than by importing
`packages/multipart`, so the ledger does not depend on one protocol's envelope shape.

TESTS. 94 test functions in `tests/unit/test_completeness.py`.

### 3.14 The six-level anchor ladder — IMPLEMENTED in Phase 2.2

`packages/coverage_validation/references.py` replaced a three-level search. The four extra levels
exist because Phase 2.1's twelve unresolved GPT OSS references were all, on inspection, small
transcription defects over content demonstrably present in the parse: a capitalised first letter, a
non-breaking hyphen, a dropped space, an inserted word.

```
1  EXACT                  character for character
2  UNICODE_NORMALISED     NFKC PER CHARACTER, so every output character maps back to exactly one
                          input position. Whole-string NFKC would compose a base letter and a
                          combining accent into one character and lose that correspondence
3  WHITESPACE_NORMALISED  runs of whitespace collapsed to one space
4  HYPHEN_NORMALISED      Unicode dashes and minus signs to ASCII, soft hyphens removed, curly
                          quotes folded to straight ones in the same pass
5  CASE_INSENSITIVE       a HUMAN-REVIEW CANDIDATE, never a resolution
6  APPROXIMATE            a HUMAN-REVIEW CANDIDATE: head and tail both occur, in order, close
                          enough together to be the same passage
```

**LEVELS 1 THROUGH 4 COUNT AS MECHANICALLY RESOLVED. LEVELS 5 AND 6 DO NOT, EVER, BY DEFAULT.**
Counting a case-folded near-match as proof is how a citation rate starts flattering the model that
produced it.

TWO SEARCH SPACES, ONE COORDINATE SYSTEM. Every level is tried over the preserved text as sent and
over the same bytes with markup removed **and character references decoded**. Every offset reported
is an offset into the ORIGINAL, through composed index maps. A hit found only in the second space is
reported as `TEXT_ONLY`. The second space is not a projection of the INPUT: nothing here changes
what a model receives.

**ENTITY DECODING IS NOT A REFINEMENT.** The benchmark filing carries 970 character references and
ZERO literal non-ASCII characters — 655 `&#160;`, 116 `&#8217;`, 53 `&#8212;`, 51 each of `&#8220;`
and `&#8221;`. A model quoting a sentence back writes the character, not the escape. Without
decoding, every quote containing an apostrophe would have failed to resolve, and a failed resolution
is indistinguishable from a fabricated citation.

**THE LEVELS ARE BUILT LAZILY, WITH IDENTITY SHORTCUTS.** Eight eager transforms over a 732 KB
document is ten million interpreter iterations per artifact, and SEC markup is overwhelmingly ASCII,
so the Unicode and typographic folds usually change not one character.

### 3.15 `packages/multipart` additions — IMPLEMENTED in Phase 2.2

```
effective.py  resolve_effective: WHICH artifact currently holds a part's content when more than
              one exists for it. It was a 44-line private method with ONE call site while six
              other consumers read the malformed original — so the reconciliation brief was shown
              node_count 0 for a part that had two nodes, and four of the five mechanical findings
              could not fire for such a part at all. THREE FACTS STAY SEPARATE: raw parseability,
              repair parseability, effective usability. Nothing is ever replaced or rewritten
tables.py     read_table and read_tables: the model-returned STRUCTURED TABLE envelope — cells
              with grid positions, row and column spans, original cell text, an optional
              normalised value THAT IS NEVER CHECKED, a unit and a period label that are the
              model's own words, continuation links, image dependency, unresolved cells
gaps.py       fingerprint and fold: a digest over a gap's STRUCTURAL identity — the kind of
              finding and the identifier or filename it names — and deliberately NOT over the
              prose, because two cycles describing the same missing material in different words
              are the same gap and a hash of the sentence would say otherwise
```

**A FALSE EMPTY IS THE INVERSE OF A FALSE COMPLETE AND EXACTLY AS UNTRUE.** This repository spends
considerable effort making sure uncertainty produces PARTIAL or REVIEW_REQUIRED rather than a false
complete; content that exists and is reported as absent had no guard at all until `effective.py`.

`resolve_effective` has callers in `orchestrator/multipart_service.py`. `tables.py` and `gaps.py` do
not yet, and section 1.2 says so.

## Build and packaging

`[tool.setuptools.packages.find] include = ["packages*"]`. **The include pattern is the rule, not a
list and not a count:** everything under `packages/` ships and nothing else does. Adding a runtime
package needs no edit; moving code out of `packages/` removes it from the distribution
automatically. Automatic flat-layout discovery cannot work here because the root holds non-Python
top-level directories and picked up the gitignored `var/` locally, so the failure was not even
reproducible across environments.

Runtime dependencies are `ruamel.yaml` and `httpx`. **That is the whole list**, and both are
imported by surviving source — verified by grep, not by memory. `sqlalchemy`, `alembic` and
`psycopg[binary]` went with the persistence layer; `pydantic` was declared and never imported by a
single module.

## Validation suite

**The Makefile is the single definition. CI invokes the same targets**, so local validation and
GitHub Actions cannot drift apart.

```
make check       fmt-check, lint, typecheck, test
make coverage    tests with coverage and the 85 percent gate
make test-no-skips   the suite, failing if any test skips
```

```
PY_PATHS     packages tests      format and lint
MYPY_PATHS   packages            type check
```

`make migration-check` is gone with the migrations. `make db-*` is gone with the database. **The
suite now has no environmental precondition at all** — no database, no network, no credentials — so
`test-no-skips` is the same suite as `test`, and a skip has no legitimate cause.

Not covered by `make check`, run before proposing a commit:

```
pip-audit --skip-editable
gitleaks git . --log-opts="--all --full-history" --redact --exit-code 1
gitleaks dir . --redact --exit-code 1
```

Gitleaks is a pinned, checksum-verified CLI binary (8.30.1), not a GitHub Action, so the same
command runs locally and in CI.

---

# 5. Security

Full threat model in `docs/deep-analysis/security.md`.

Implemented today: User-Agent validation failing closed; path-traversal rejection; centralized log
redaction covering model content, generic secrets and AWS credential names; model content-boundary
enforcement in both directions; native tool-call refusal; budget enforcement before spend; and
architecture tests that scan every tracked file for credential variables, explicit SDK credential
arguments and credentials in URLs.

Not implemented: authentication of any kind, and there is nothing to authenticate to.

---

# 6. Known defects and limitations

1. The rate limiter is in-process. Multi-process ingestion needs a shared bucket because the SEC
   limit is aggregate across machines.
2. Token estimation is a character-ratio heuristic, adequate for budget guards and relative
   comparison, not for billing reconciliation.
3. The capability snapshot is dated evidence and goes stale silently: nothing in the repository can
   detect that a provider changed a price, moved a model or retired a version. Official price
   INPUTS are now verified; the token counts they multiply are not, so every cost figure in
   `docs/llm/cost-model.md` remains a placeholder. Still BLOCKING for any cost commitment.
   **CORRECTED 2026-08-04, ADDITIVELY. The second half stopped being true in Phase 2.** Token
   counts are measured — Bedrock returns exact usage per invocation — and `docs/llm/cost-model.md`
   now carries measured per-filing figures rather than placeholders. Phase 2.1 measured
   `USD 2.603827` across seven runs at prices re-verified with ZERO DRIFT against the live Price
   List API on 2026-08-04. **The FIRST half is unchanged and is still true**: nothing in the
   repository detects drift, the check was a person re-running a runbook, and what is measured
   covers three filings, which is not a corpus. A PRE-SPEND estimate is still a character ratio at
   3.8 characters per token, an upper bound and not a count.
4. Filing acquisition covers the inline-XBRL era only. The other five transport eras have no
   acquisition path.
5. The complete filed-document set of an accession cannot currently be listed. The module that did
   it was deleted for classifying documents into a Regulation S-K role taxonomy; the replacement is
   Phase 2a.
   **CORRECTED 2026-08-04, ADDITIVELY. False since Phase 2, 2026-08-03.**
   `packages/filing_acquisition/documents.py` is the non-classifying replacement: it reports
   sequence, filer-declared type, filename, description and byte range from EDGAR's SGML envelope,
   and assigns no role, class, importance or meaning to any of it. Phase 2.2 listed all 63 members
   of accession `0000320193-25-000008` through it. One thing it does not do is reconcile: that
   envelope's `PUBLIC DOCUMENT COUNT` declares 63 while the envelope contains 62 `DOCUMENT` blocks,
   and the discrepancy is recorded rather than resolved.
6. There is no local numeric evidence. DERA was deleted; cross-checking model-returned numbers
   against an independent source is reconsidered on measured need.
7. `packages/configuration` and `packages/observability` have no non-test caller.
   **CORRECTED 2026-08-04, ADDITIVELY. Half false since Phase 2, 2026-08-03.**
   `packages/configuration` gained one: `packages/review_api/app.py`. `packages/observability` has
   none. `packages/multipart/tables.py` and `packages/multipart/gaps.py` have none either — the
   scheduler does not read them yet. Section 1.2 carries the detail.
8. `packages/sec_identity` exports several URL builders with no current caller —
   `cik_submissions_stem`, `is_valid_accession`, `filing_index_json_url`,
   `company_tickers_exchange_url`. They are retained, unlike the dead code removed from
   `llm_gateway`, because each is a verified SEC endpoint format rather than a speculative
   contract, and this package is the designated single home for exactly that.
9. No authentication exists. BLOCKING for any exposure beyond loopback.
10. **The single-filing completeness benchmark has not run.** The inventory, the ledger and the gate
    have never been exercised against a real parse of the benchmark filing, and the benchmark truth
    has no recorded human classification. `GPT OSS 120B` cannot receive that filing intact at all,
    and running the four that can costs `USD 13.3745` against `USD 5.00` authorized. BLOCKING for
    any completeness measurement.
11. **`no_progress_tolerance` is declared, validated and not enforced.** The scheduler does not
    consult it and the gap fingerprints that would feed it have no caller, so a reconciliation loop
    is still bounded only by `max_reconciliation_cycles`.
12. **`packages/llm_gateway/providers/bedrock.py` targets `bedrock-runtime`.** A second endpoint,
    `bedrock-mantle`, now appears on most current model cards with an AWS recommendation, and three
    models are mantle-only. Adopting it is a user decision and has its own investigation ahead of
    it; nothing in this repository uses it.
