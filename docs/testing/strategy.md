# Testing Strategy

IMPLEMENTATION STATUS: unit, integration, architecture, and migration layers IMPLEMENTED;
golden, property, security, and performance layers PLANNED

## Current state, after the Sprint 2 alignment review

```
143 tests collected, 143 passing and 2 skipped
 93% statement coverage across the implemented packages
 129 test functions; the difference is parametrized cases

tests/unit/test_llm_boundary.py         25  content boundary, compiler, gateway
tests/unit/test_migrations.py           17  schema structure, reversibility, attachment audit,
                                            completeness design, 2 live tests that SKIP
tests/unit/test_yaml_parser.py          16  safe parsing, identifier preservation, alias bomb
tests/unit/test_sec_identity.py         15  CIK, accession, URL construction
tests/unit/test_sec_http_client.py      15  UA, 403 classification, cooldown, content assertions
tests/architecture/test_architecture.py 11  structural invariants from rules.md
tests/unit/test_sec_client.py            9  throttle classification, rate limiting
tests/unit/test_dera_notes.py            7  discovery, irregular filenames, resumability
tests/unit/test_configuration.py         6  User-Agent validation, settings guards
tests/unit/test_storage.py               6  hashing, object store, traversal
tests/integration/test_dera_mirror.py    2  discovery plus storage plus ledger
```

### The two skips

`tests/unit/test_migrations.py` contains two live-database tests that skip with an explicit
reason when no PostgreSQL is reachable. They are the only tests in the suite that have never
executed. **Sprint 3 makes them run.** A skip is reported as a skip and never counted as a pass.

### Anti-vacuity

`test_architecture_suite_has_something_to_check` and `test_no_package_is_an_empty_stub` exist
because Sprint 1 created eighteen packages containing only a docstring, and two architecture
tests scanned those empty directories and passed while enforcing nothing. A green suite must
mean the invariants held, not that there was nothing to check.

## Layers

### Unit

IMPLEMENTED: CIK formatting, accession formatting, SEC URLs, rate limiter, throttle
classification, User-Agent validation, YAML safe parsing, boundary detection, hashing, object
store, DERA classification.

PLANNED: fiscal periods, duration buckets, Q4 derivation, unit and scale normalization, metric
resolution, canonical grouping, citation validation, scope validation, budget enforcement.

### Integration

IMPLEMENTED: DERA mirror idempotency and provenance across discovery, storage, and ledger.

PLANNED: SEC fixture ingestion, DERA TSV loading, parser execution per era, fact persistence,
footnote extraction, summary model adapter, validation pipeline, dataset publication, dashboard
APIs, analysis session creation, scoped retrieval.

### Golden

PLANNED. Frozen real filing fixtures, one per era, checked into `tests/fixtures/filings/`.

```
apple_fy2025_10k        inline XBRL, 13 canonical footnotes, 46 child blocks
apple_fy2013_10k        standalone XBRL, double-escaped text blocks
apple_2005_10k          HTML, no XBRL
apple_1994_10k          PEM armor, IMS-DOCUMENT, empty primaryDocument
amd_10ka                partial amendment, 545KB against a 14MB original
ntrb_10ka               near-empty amendment, one 4-character text block
```

### Property

PLANNED. Invariants that must hold across the whole corpus:

```
no summary crosses an accession boundary
no session retrieves a foreign CIK
no completed filing lacks a footnote summary
no raw fact is ever overwritten
no chart series mixes incompatible durations
no amendment erases its original
every canonical footnote has exactly one active summary
every source block has a parent or is in the review queue
```

### Security

PLANNED, specified per threat in `docs/deep-analysis/security.md`. Every threat T-01 through T-12
has a named test.

### Architecture

IMPLEMENTED:

```
test_bedrock_client_not_imported_outside_provider
test_no_generic_utils_module
test_sec_identity_logic_has_a_single_home
test_domain_layer_has_no_infrastructure_imports
test_no_prompt_strings_embedded_in_packages
test_prompt_directory_contains_no_markdown
test_prompts_do_not_request_prohibited_output_formats
test_every_package_exposes_a_public_interface
```

### Migration

PLANNED. Every migration applies forward and reverses cleanly on a populated database.

### Performance

PLANNED. Backfill throughput, DERA load time, Parquet publication time, dashboard query latency,
concurrent readers during publication, analysis retrieval latency, queue recovery.

## Fixture policy

Fixtures are real SEC responses, captured once and committed. They are never hand-edited to make
a test pass; a wrong fixture is recaptured. Fixtures carry the URL and capture date so staleness
is visible.

## What a test must not do

Reach the network in the unit or integration layers. Depend on wall-clock time; the rate limiter
takes an injectable clock precisely so its tests are deterministic and fast. Assert on log text.
Share mutable state between tests.
