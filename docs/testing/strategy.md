# Testing Strategy

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

# CURRENT DIRECTION — AUTHORITATIVE. Everything below this section is historical.

Tests are grouped by whether they EXIST TODAY, are PLANNED FOR PHASE 2, or are PLANNED FOR THE
ORCHESTRATOR. Nothing below claims a test exists when it does not.

## EXISTING — running in ordinary CI today

```
source byte fidelity            five original SEC fixtures pinned by SHA-256 and size,
                                verified from the committed blob
hash verification               tests/unit/test_filing_fixtures.py
entity and filing identity      tests/unit/test_corpus_identity_contract.py
                                tests/unit/test_corpus_identity_rules.py
exact form-family contract      tests/unit/test_form_family_contract.py — the qualifying set is
                                GENERATED from the reviewed inventory and an unreviewed candidate
                                fails closed
model-boundary rules            tests/unit/test_llm_boundary.py and the architecture suite
accession inventory             tests/unit/test_accession_inventory.py
database isolation              tests/unit/test_database_isolation.py
migration-target routing        tests/unit/test_migration_target_routing.py
migration round trip            tests/unit/test_migrations.py, live against fintek_test
persistence integration         three suites, live against fintek_integration_test
architecture invariants         tests/architecture/, including the CI workflow itself
deterministic ORACLE tests      footnote extraction, canonicalization and table ownership.
                                RETAINED AS BENCHMARKS. They no longer define a correct parse.
```

## PLANNED FOR PHASE 2 — none of these exists

```
source-set completeness         that the complete relevant human-readable set was determined
intact-input compatibility      that an incompatible pairing is refused BEFORE invocation, with
                                measured bytes, estimated tokens and the model's limit
flexible artifact acceptance    that an unfamiliar label or content type is represented, not
                                rejected and not dropped
source-reference validation     that every cited offset resolves in the preserved source
numeric validation              that every reported number appears verbatim
unresolved-content handling     that unresolved ranges are preserved and block completeness
no false completeness           that PARTIAL and REVIEW_REQUIRED are produced rather than a
                                rounded-up COMPLETE
model-output fixture testing    recorded real responses replayed offline
prompt-version testing          that a prompt change is versioned and attributed
A/B model comparison            the same filing through different parsing models
repeat-run variability          the same filing through the same model twice
```

## PLANNED FOR THE ORCHESTRATOR — none of these exists

```
capability-router tests         that a role never inherits another role's model, and that no
                                substitution happens without the user
cost authorization              that no billable call occurs without an explicit ceiling
streaming security              that resumption cannot leak another job's events
cache correctness               that a cached result is keyed by what actually determines it
```

## Rules that apply to all three groups

**A skip is not a pass.** `make test-no-skips` fails the run if anything skips in an environment
that can run it, and CI runs that target.

**A test may not depend on an untracked file.** One did — it read the developer's gitignored
`.env` — and it passed locally while being incapable of passing in CI. Fixtures come from the
repository or from `tmp_path`.

**A gate is never weakened to make a commit pass.** Correcting a demonstrably wrong test is
permitted and must be disclosed in the commit report, with what changed and why the replacement
still protects the behaviour.

**Destructive tests never touch an application database.** Three database identities, no fallback
between them, and the application one does not exist.


IMPLEMENTATION STATUS: unit, integration, architecture, and migration layers IMPLEMENTED;
golden, property, security, and performance layers PLANNED

## Current state, after Sprint 4.1

```
876 tests collected, 876 passing, 0 skipped     715 unit, 68 integration, 93 architecture
 ~92% statement coverage across fifteen measured packages (85% gate)

tests/unit/test_filing_content_regression.py  40  complete-filing census, 4 filings + 9 mutations
tests/unit/test_filing_parser.py              35  blocks, structure, hierarchy, era neutrality
tests/architecture/test_complete_filing_coverage.py 32  scope-revert guards
tests/unit/test_filing_content.py             27  paths, coverage, layers, references
tests/unit/test_accession_inventory.py        20  declared-type classification
tests/unit/test_historical_filing_regression.py 18  the real 1994 bytes + 4 mutations
tests/unit/test_migration_target_routing.py   24  defect D-13: target precedence and guards
tests/unit/test_graphic_coverage.py           22  graphic classification and its consequence
tests/integration/test_filing_content_persistence.py 18  LIVE: persist, zero-write rerun, digest

tests/unit/test_ten_q_regression.py           42  the three 10-Qs asserted, plus mutation proofs
tests/unit/test_table_ownership_regression.py 42  ownership census per filing
tests/unit/test_footnote_canonicalizer.py     36  stages 1-5, exclusion, audit, completeness
tests/unit/test_llm_boundary.py               31  content boundary, compiler, gateway
tests/unit/test_filing_discovery.py           30  overflow, master.gz reconciliation, era
tests/unit/test_database_isolation.py         30  disposable-target proof, fail-closed paths
tests/unit/test_table_parser.py               28  rows, headers, cell provenance, exact text
tests/unit/test_sec_identity.py               25  CIK, accession, URL construction
tests/unit/test_footnote_extractor.py         25  inventory, candidates, child blocks, headings
tests/unit/test_dera_normalize.py             25  version split, period derivation, natural key
tests/unit/test_table_ownership.py            24  tagged spans and the presentation linkbase
tests/unit/test_migrations.py                 23  structure, reversibility, range derivation,
                                                  2 LIVE tests
tests/architecture/test_aws_identity.py       20  no credential shape reaches the repository
tests/integration/test_canonicalization_persistence.py 19  LIVE: persist, rerun, reconcile
tests/unit/test_dera_validate.py              18  domain rules mirroring database constraints
tests/architecture/test_deterministic_extraction.py 17  no model, no network, no issuer branch
tests/unit/test_yaml_parser.py                16  safe parsing, identifier preservation, alias bomb
tests/unit/test_filing_fixtures.py            16  fixture manifest hashes, offline reproduction
tests/unit/test_dera_tsv.py                   16  quoting disabled, null tokens, exact conversion
tests/unit/test_dera_selection.py             16  package selection, members, dimensions
tests/integration/test_dera_load.py           13  LIVE: register, load, reconcile, rerun
tests/architecture/test_architecture.py       11  structural invariants from rules.md
tests/integration/test_ten_q_persistence.py   10  LIVE: per-quarter idempotency and digests
tests/architecture/test_ci_workflow.py        10  the workflow parsed, not grepped
tests/integration/test_dera_mirror.py          2  discovery plus storage plus ledger
```

The four files added by the closeout hardening are the last three architecture and integration
entries plus `test_ten_q_regression.py`. They assert results that already existed and that nothing
was checking — see "A measured result nobody asserted" below.

### The skips are gone

The two live migration tests that had never executed in this project now run and pass, and
`tests/integration/test_dera_load.py` joins them. Every test that needs a database resolves its
URL through `packages/persistence/engine`, and skips with an explicit reason when none is
reachable — a skip is reported as a skip and never counted as a pass.

### The skip gate

`make test-no-skips` sets `FINTEK_FORBID_SKIPS`, which a hook in `tests/conftest.py` reads. When
set, a run that skipped anything fails and names each skipped test with its reason. CI runs that
target, because CI provides a PostgreSQL service container: a skip there means a guard quietly
stopped being enforced, not that the environment lacks something.

This exists because a skip is invisible. It is a bare `s` in a progress line, and
"203 passed, 2 skipped" read as success for two sprints while the only two tests exercising the
live schema had never once executed. Every test target now passes `-ra`, so non-passing outcomes
are summarized with their reasons rather than being a character in a row of dots.

Proven to fire: adding a deliberately skipping test makes the gated run exit 1 and print the test
and its reason; the ungated run exits 0.

### Two databases, because destructive tests exist

`test_upgrade_then_downgrade_round_trips` runs `alembic downgrade base`, which DROPS EVERY
APPLICATION TABLE. Pointed at the application database it deleted 2,845 loaded facts on this
development host, silently, while `make check` reported green.

The first fix skipped the test when the target held data. That stopped the deletion and left the
test unrun — the other half of the same failure. The suite now uses two databases:

```
DATABASE_URL       fintek        the application database; NON-DESTRUCTIVE use only
TEST_DATABASE_URL  fintek_test   disposable; destructive tests drop every table in it
```

`packages/persistence/engine.assert_disposable` proves the second is not the first before any
destructive test body runs. It compares parsed host, port, socket path, and database name — string
comparison is insufficient, because `@localhost/fintek` and `@127.0.0.1:5432/fintek` are different
strings and the same database — and it excludes credentials on purpose, so a destructive run
cannot be authorized by connecting as a different user. It also requires the name to carry `test`
as a whole token and to mention nothing production-like.

There is **no fallback** to `DATABASE_URL`. A fallback works everywhere, quietly, until the day the
application database has something in it. A missing `TEST_DATABASE_URL` fails; a server that is
reachable but missing the test database fails with the command that fixes it. Only an unreachable
server skips.

The rule is `rules.md` section 3, TEST-DATABASE-ISOLATION-INVARIANT. Setup is
`docs/runbooks/test-database.md`. The guard itself has 30 tests in
`tests/unit/test_database_isolation.py`, each named after the specific way a weaker guard lets the
deletion happen anyway.

### The application-preservation gate

A session hook records the row counts of `issuer`, `filing`, and `xbrl_fact` before the suite and
compares them after. Any change fails the run, whether from a dropped table or from a fixture row
a test forgot to clean up. Always on — it needs no opt-in, because there is no situation in which
the suite should change the application database.

This is the check that would have caught 2,845 facts disappearing during the run that caused it,
rather than days later.

### An inter-test dependency the isolation work exposed

`test_filed_fact_cannot_be_updated` inserted its fixture using Apple's real CIK and accession,
both UNIQUE columns, so it failed the moment the application database held a real load. It had
only ever passed because the destructive test ran first and left every table empty.

Same lesson twice: **a test that has only ever run against an empty database has not been tested
against a database.**

### One execution, one set of counts

`make test-summary` used to invoke pytest itself. In CI that ran all 337 tests a second time
purely to print a number, and — worse — reported counts from a *different* execution than the one
the zero-skip gate had just enforced. Both `test` and `test-no-skips` now record their output to
`.pytest-last-run.log`, and `test-summary` reads it. There is still one definition of the test
command; only the reporting changed.

Redirect-then-`cat` rather than a pipe, so pytest's exit status is preserved exactly without
depending on `pipefail` or on which shell make selected.

### Markdown is linted, not reviewed

`tests/architecture/test_markdown_lint.py` enforces four things across every repository-owned
Markdown file: fences are balanced, no heading is trapped inside a code block, relative links
resolve, and no password-bearing database URL appears in prose.

A broken fence has no parse error. An unclosed block swallows every heading, link, and paragraph
after it, and the document renders on GitHub as one grey slab while looking fine in an editor.

**Nothing asserts what a document says.** The file was previously named for documentation and
pinned the README's headings and a 700-to-1,200-word budget; both were removed, along with two
tests that required named phrases to appear in `rules.md` and the AWS identity policy. A test that
pins prose turns editing prose into a test failure, and it caught nothing — the README rewrite
that broke it was correct and the test was wrong. Documentation truthfulness is a commit-time
obligation on the author under `rules.md` section 18. It is not testable, and the attempt cost
more than it returned.

Two design notes, each from a false result the check produced first:

- **Only unlabelled fences are checked for swallowed headings.** In a ` ```bash ` block, `# text`
  is a shell comment. Flagging those failed a runbook that was perfectly correct.
- **The file list comes from `git ls-files`, not a directory walk with a skip list.** A name-based
  skip list is a guess about what is not ours, and it was wrong: renaming `.venv` during a CI
  reproduction pulled a dependency's README into the scan and failed on a broken link inside it.

All four were proven to fire by introducing each defect into the README and observing the failure.

### Determinism is enforced, not assumed

`tests/architecture/test_deterministic_extraction.py` reads the imports and AST of
`footnote_extractor`, `footnote_canonicalizer`, and `table_parser` and fails on a model SDK, an
HTTP client, an AWS SDK, an endpoint literal, a credential name, or a call that would reach a
provider. It also enforces the ownership boundaries — the canonicalizer must not parse tables, the
extractor must not import grouping policy, the table parser must not convert filed text to a
number — and asserts that stage 6 through 11 grouping methods are not produced.

One narrow exception, by symbol: `packages.llm_gateway.parse_yaml` is the project's safe YAML
reader, not a model call, and reading the exclusion definition with it is correct where `yaml.load`
would open an arbitrary code path.

Three guards proven by mutation: adding `import boto3`, calling `parse_tables` from the
canonicalizer, and emitting `presentation_hierarchy` each fail the suite.

### Anti-vacuity

`test_architecture_suite_has_something_to_check` and `test_no_package_is_an_empty_stub` exist
because Sprint 1 created eighteen packages containing only a docstring, and two architecture
tests scanned those empty directories and passed while enforcing nothing. A green suite must
mean the invariants held, not that there was nothing to check.

Two further anti-vacuity results are recorded rather than assumed:

- **The append-only trigger test** ran `UPDATE ... WHERE false`, which matches zero rows against a
  `FOR EACH ROW` trigger and therefore could not fail. Rewritten, then proven by dropping the
  trigger (fails) and restoring it (passes).
- **The DERA idempotency test** was proven by mutation: removing the existing-key filter from the
  loader makes `test_a_rerun_inserts_nothing` fail with 8 rows in the database where 4 belong.

A test whose failure has never been observed is a claim, not a guard.

### A measured result nobody asserted

Sprint 4 measured all four filings but only the 10-K's note and attachment counts were written into
a test. CI proved the three 10-Qs' *table ownership* census while their canonical-footnote and
attached-child counts lived only in the sprint record. Nothing was wrong — the numbers were right —
but a number no test reads is a claim, and it would have drifted silently.

`tests/unit/test_ten_q_regression.py` and `tests/integration/test_ten_q_persistence.py` close that
gap. The pattern generalizes: **when a sprint records a measurement, the same commit must put it
somewhere a test can fail on it.**

## Complete-filing testing — Sprint 4.1

### Real filed bytes, not composed text

Five primary documents are committed fixtures and hash-verified against `manifest.yaml` on every
run: four FY2025 inline-XBRL filings and the 1994 PEM-armored submission. Sprint 3's policy
committed only derived fixtures; Sprint 4.1 changed it, and the reason is in that file.

**Five of this sprint's twelve defects were invisible to composed text.** A bare-form-only `PART`
pattern found zero Parts in every 10-Q. Statement headings requiring end-of-string missed every
`(Unaudited)` heading, so a 10-Q reported zero statements and zero footnotes while carrying five
and ten. The 1994 notes are unnumbered and underlined by a typewriter rule, so `Note N` matching
found none. Each produced a confident, silent, wrong result that a synthetic fixture would have
confirmed as correct.

Cost: 3.9 MiB raw, roughly 264 KiB after git compression.

### Coverage-ledger reconciliation

The load-bearing assertion is not a section count. `reconcile()` refuses to describe blocks it was
not given — a disposition list that does not cover the block list raises rather than reconciling
perfectly against itself — and then asserts every block carries exactly one disposition, no block
is owned by two units, and every exclusion states a reason.

```
2,878 blocks across five filings   0 unresolved   0 double-assigned   every exclusion reasoned
```

### Document-inventory reconciliation

Classification is asserted against the **filer's declared type**, and the two SEC listings are held
apart: the index document table lists what the issuer filed (16 for one 10-K), `index.json` lists
the folder (93, including SEC's own viewer output).

### No-write rerun

The idempotency proof is a second persistence pass writing **zero rows** — not a claim that the
upserts are conditional, but the observed consequence. Run against `fintek_test` before the
application database, and against the application database after.

### Layered completeness

Each layer is asserted independently, and the combination that matters most is asserted directly:
a filing that is `SUBMISSION_COMPLETE` and `DISCLOSURE_PARTIAL` at the same time. A test that
checked only "is it complete" could not distinguish that state from a defect.

### Mutation proofs

Thirteen, each removing or corrupting exactly one thing and asserting the guard notices: removed
Item, removed signature block, removed notes section, TOC substitution, hidden-XBRL duplication,
unresolved-disposition reachability, MD&A misclassified as a footnote, the Part-heading regression
this sprint actually hit, a missing historical note boundary, historical signature over-capture, a
bare rule that must not open a footnote, and a healthy-baseline control that prevents the rest from
passing vacuously.

### Architecture enforcement against scope revert

`test_complete_filing_coverage.py`. A scope assumption leaves no failing test behind — which is how
four sprints were built on one. These assert structurally where possible: the taxonomy is imported
and checked for required types rather than grepped; constraint names are read off the SQLAlchemy
metadata; `ParsedUnit`'s fields are checked against the era-specific provenance set. Prose matching
is used only where the artifact is prose, and then per paragraph with a retraction marker, so a
document may cite the retired claim while explaining it and may not reassert it.

### Migration-target routing, after defect D-13

A Sprint 4.1 test helper reached the application database with `alembic stamp base`, because
`env.py` resolved its target through `DATABASE_URL` and overrode the `sqlalchemy.url` the helper
had set. No row moved, so the preservation gate stayed green while the recorded revision and the
schema disagreed.

Three layers now apply, in this order:

```
1  precedence      packages.persistence.engine.migration_target_url() is the ONE resolver, and an
                   explicitly supplied target outranks DATABASE_URL
2  pre-execution   assert_safe_destructive_target() proves identity, name, host or socket, port,
                   the test token, and difference from the application database — and raises
                   BEFORE Alembic is called
3  post-execution  the preservation gate watches alembic_version alongside row counts
```

Layer 3 alone is a detector, not a guard: by the time it fires, a `downgrade base` has already
run. It is retained as a backstop.

**The revision-detection guard is proven non-vacuously without touching the application database.**
Clearing a real revision to demonstrate a guard is what caused the incident; the proof uses
synthetic baseline snapshots instead, plus a live assertion that the collector emits the key.

## One suite, two callers

The Makefile is the **single definition** of every validation command. CI invokes the same
targets rather than restating them, so the local pre-commit suite and GitHub Actions cannot
diverge. `rules.md` section 17 requires this reconciliation; before it existed, CI checked
`packages tests` while local validation checked `packages tests scripts migrations`.

| Target | Covers |
|---|---|
| `make fmt-check` / `make lint` | `packages tests scripts migrations` |
| `make typecheck` | `packages scripts migrations` |
| `make test-unit` / `test-integration` / `test-architecture` | the three layers separately, as CI runs them |
| `make migration-check` | offline Alembic generation, `base:head` and `head:base` |
| `make coverage` | the suite with the 85 percent gate |
| `make check` | everything above except coverage |

**`tests` is deliberately excluded from type checking.** The test suite reaches into SQLAlchemy
internals where `Model.__table__` is typed as `FromClause`, producing six errors that are typing
friction rather than defects. Adding blanket ignores to make them disappear would weaken the
check for the source code that matters. This is recorded rather than hidden.

Tools resolve from `./.venv/bin` when it exists and from `PATH` otherwise, so the same target
works locally and on a CI runner.

## Security scanning

Two scans, both enforcing, both reproducible locally with the identical command:

```
gitleaks git . --log-opts="--all --full-history" --redact --exit-code 1
gitleaks dir . --redact --exit-code 1
pip-audit --skip-editable
```

Gitleaks is a **pinned CLI binary, 8.30.1, verified by SHA-256 checksum** — not a GitHub Action.
The action was replaced after the first CI run, where it derived a commit range from the push
event, resolved it to the nonexistent parent of the root commit, scanned zero bytes, and failed.

What is scanned: **all reachable commits** (`--all --full-history`) **and the working tree**. Not
a commit range. `--redact` keeps any finding out of the log; `--exit-code 1` fails the job on a
finding. A "zero bytes scanned" result is treated as a failure to scan, never as a pass.

`pip-audit` is enforcing rather than advisory. `--skip-editable` excludes the local `fintek`
install, which is not on PyPI and was the reason the check was previously suppressed with
`|| true`.

## Layers

### Unit

IMPLEMENTED: CIK formatting, accession formatting, SEC URLs, rate limiter, throttle
classification, User-Agent validation, YAML safe parsing, boundary detection, hashing, object
store, DERA classification, DERA TSV parsing, fact normalization, domain validation, package
selection, dimension resolution, and load reporting.

PLANNED: fiscal periods, duration buckets, Q4 derivation, unit and scale normalization, metric
resolution, canonical grouping, citation validation, scope validation, budget enforcement.

### Integration

IMPLEMENTED: DERA mirror idempotency and provenance across discovery, storage, and ledger. The
DERA fact load end to end against a live PostgreSQL — registration, insertion, the load ledger,
idempotency on rerun, reconciliation, and refusal of a package whose bytes changed since
mirroring.

The load suite builds a small synthetic package rather than reading a mirrored one. A test that
depends on a 97 MB archive cannot run on a fresh clone, and the sprint committed to `pytest`
passing offline. The synthetic package has the same shape, so it exercises the same code path.

PLANNED: SEC fixture ingestion, parser execution per era, footnote extraction, summary model
adapter, validation pipeline, dataset publication, dashboard APIs, analysis session creation,
scoped retrieval.

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

The workflow itself is an architecture surface, in `tests/architecture/test_ci_workflow.py`. Every
check there reads the **parsed YAML** — the `uses:`, `with:`, and `permissions:` values GitHub acts
on — never the file's text: a comment promising `fetch-depth: 0` greps identically to the setting,
and only one of them clones any history.

```
test_no_official_action_runs_on_a_deprecated_node_runtime
test_official_actions_come_from_the_official_repositories
test_the_security_checkout_still_fetches_full_history
test_the_workflow_keeps_least_privilege_permissions
test_the_quality_job_keeps_its_database_and_isolation_gate
test_the_workflow_runs_the_makefile_rather_than_its_own_commands
test_ordinary_ci_acquires_no_aws_identity
```

The runtime floor is a floor, not an exact version: `actions/checkout` runs Node 24 from v5 and
`actions/setup-python` from v6. Pinning the exact current major would fail on the next legitimate
bump, which is a different problem from reintroducing a retired runtime.

### Migration

IMPLEMENTED for offline generation and for the disposable-database round trip. Still PLANNED:
reversal on a *populated* database, which needs a fixture dataset the round trip does not build.

**The offline range is derived, never named.** `make migration-check` generates
`upgrade base:head` and `downgrade head:base`. It used to generate `downgrade 0001_initial:base`,
which was correct while 0001 was the only revision and silently stopped covering anything new when
0002 arrived: Alembic renders only the revisions inside the range it is given, so the target kept
exiting 0 while producing 25 statements, none of which dropped an ownership column, constraint, or
index. The check reported a property it had stopped testing.

Four tests in `tests/unit/test_migrations.py` hold the corrected range:

```
test_migration_check_names_no_revision_id             the Makefile recipe contains no revision id
test_migration_check_downgrade_starts_at_the_current_head
test_every_revision_contributes_downgrade_sql         every revision head..base emits SQL
test_the_superseded_range_is_demonstrably_insufficient  the old range omits what the new one covers
```

The first reads the recipe out of the Makefile rather than restating the command, so a test cannot
pass while CI runs something else. The last is the non-vacuity proof: without it, `head:base`
passing would show only that some range works, not that the range it replaced was broken.

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
