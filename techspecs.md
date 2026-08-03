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
> **NO MODEL HAS BEEN INVOKED. AWS IS NOT CONFIGURED. NO APPLICATION DATABASE EXISTS.**

Sections marked `PLANNED` describe work that does not exist. `roadmap.md` is authoritative for
sequencing.

LAST SYNCHRONIZED WITH CODE: 2026-08-03, the cleanup commit.

VERIFICATION, measured locally on that date:

```
309 tests passing, 0 skipped          coverage 90.89 percent against an 85 percent gate
ruff format and lint clean            across `packages tests`
mypy clean                            40 source files in `packages`
wheel and sdist built and inspected   packages/ and dist-info only
external import check                 8 runtime packages import; 5 deleted packages do not
gitleaks clean over history and tree  pip-audit clean
```

---

# 1. CURRENT STATE

## 1.1 Runtime packages — eight, 40 modules, 3,469 lines

None of them interprets meaning.

```
packages/sec_identity        CIK, accession and URL normalization — the single home       5 modules
packages/sec_client          HTTP with the shared rate limiter and throttle classification 5
packages/configuration       startup validation, including the SEC User-Agent gate         4
packages/observability       structured logging, field redaction, correlation scope        3
packages/storage             object storage and content hashing                            3
packages/filing_discovery    qualifying-filing discovery against a SUPPLIED form set       4
packages/filing_acquisition  byte-exact acquisition with provenance                        3
packages/llm_gateway         the model chokepoint, boundary validator and YAML 1.2 parser 12
                             running against an in-process mock. NO REAL PROVIDER ADAPTER.
```

## 1.2 Dependency graph — measured, not asserted

```
configuration        -> (none)
observability        -> (none)
storage              -> (none)
sec_identity         -> (none)
sec_client           -> configuration
llm_gateway          -> (none)
filing_discovery     -> sec_identity
filing_acquisition   -> sec_identity, storage
```

No cycles. No package imports a database driver, a web framework, or a provider SDK. Two packages —
`configuration` and `observability` — currently have **no non-test caller**; they are the
designated single homes for startup validation and structured logging and are wired in Phase 2.
This is recorded rather than hidden: unwired code is a liability, and both now carry tests that
prove the behaviour they will be wired for.

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
| AWS identity and secret policy | governance + `tests/architecture` | IMPLEMENTED as governance; NO AWS CODE EXISTS |
| Filed-document lister, non-classifying | — | PLANNED, Phase 2 |
| Real provider adapter | `llm_gateway/providers/` | PLANNED, Phase 2 |
| Parsed / image / summary / chat artifacts | — | PLANNED, Phases 2 and 3 |
| Persistence, approval gate, Redis cache | — | PLANNED, Phase 4 |
| Parser-review UI | — | PLANNED, Phase 2 |

Reserved package names. **These directories do not exist.** Sprint 1 created eighteen packages
containing only a docstring, which reserved names twenty sprints ahead of their code and made two
architecture tests pass while scanning nothing. Each is created in the change that writes its first
module, and an architecture test rejects an empty stub.

| Reserved name | Planned path | Phase |
|---|---|---|
| Bedrock provider adapter | `packages/llm_gateway/providers/bedrock.py` | 2 |
| Filed-document lister | `packages/filing_acquisition/documents.py` | 2 |
| Source-set assembly and compatibility | `packages/source_transport` | 2 |
| Coverage validation of model output | `packages/coverage_validation` | 2 |
| Four-role model catalog and router | `packages/model_catalog` | 2 |
| Orchestrator: parent runs and child jobs | `packages/orchestrator` | 2 |
| API | `apps/api` | 2 |
| Web dashboard | `apps/web` | 2 |
| Artifact persistence and approval | `packages/artifact_store` | 4 |
| Deep Analysis | `packages/deep_analysis` | 7 |

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

### 3.2 `packages/configuration` — IMPLEMENTED, no non-test caller

RESPONSIBILITY. Load and eagerly validate settings so a misconfiguration fails at startup rather
than after generating traffic that will be blocked.

PUBLIC INTERFACE. `Settings.from_env`, `SecAccessSettings`, `StorageSettings`, `LlmSettings`,
`validate_user_agent`, `is_valid_user_agent`, `DENYLIST_FRAGMENTS`.

INVARIANTS. A User-Agent must exist, must contain a contact email, and must not match a library
default. Global rate within `(0, 10]`. Throttle cooldown at least 600 seconds.

KNOWN GAP. `LlmSettings` carries `standard_model_id` and `analysis_model_id`, a two-role shape that
predates the four-role product. It is deliberately NOT replaced with a guessed four-role shape: the
real catalog is built from verified capability discovery, which has not run.

TESTS. 6 in `tests/unit/test_configuration.py`.

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

**No request or response contract is declared.** No model has been invoked, so none is known.

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

---

# 4. Repository structure

```
packages/        8 runtime libraries, 40 modules
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
3. The provider catalog and pricing are entirely unverified. BLOCKING for any cost commitment.
4. Filing acquisition covers the inline-XBRL era only. The other five transport eras have no
   acquisition path.
5. The complete filed-document set of an accession cannot currently be listed. The module that did
   it was deleted for classifying documents into a Regulation S-K role taxonomy; the replacement is
   Phase 2a.
6. There is no local numeric evidence. DERA was deleted; cross-checking model-returned numbers
   against an independent source is reconsidered on measured need.
7. `packages/configuration` and `packages/observability` have no non-test caller.
8. `packages/sec_identity` exports several URL builders with no current caller —
   `cik_submissions_stem`, `is_valid_accession`, `filing_index_json_url`,
   `company_tickers_exchange_url`. They are retained, unlike the dead code removed from
   `llm_gateway`, because each is a verified SEC endpoint format rather than a speculative
   contract, and this package is the designated single home for exactly that.
9. No authentication exists. BLOCKING for any exposure beyond loopback.
