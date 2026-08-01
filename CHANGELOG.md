# Changelog

All notable changes to FinTek are recorded here. This is not a commit dump: it records
user-visible, architecture-level, data-model, and operational changes.

Format follows Keep a Changelog, with two additional sections that matter for this system:
`Data migrations` and `Operational changes`.

## [Unreleased]

Two entries: the Sprint 2 alignment review (committed as `275db19`), and the CI repair that
followed the first GitHub Actions run.

---

### CI repair — not yet committed

The repository's first Actions run failed in both jobs. Neither failure was caused by the commit
that triggered it; both were latent defects that had never executed because the workflow triggers
on push to `main`, the branch was `master`, and no remote existed.

#### Fixed

- **`pip install -e ".[dev]"` could never succeed.** Setuptools flat-layout auto-discovery aborts
  with `Multiple top-level packages discovered` because the repository root holds `prompts`,
  `artifacts`, `migrations`, `metric_definitions`, `docs`, and `tests` alongside `packages`.
  `pyproject.toml` now declares explicit discovery, `include = ["packages*"]`, plus an explicit
  `[build-system]`. Verified: editable install succeeds in a clean virtualenv, all nine
  subpackages import, and none of the six non-package directories is packaged.
- **Three runtime dependencies were undeclared.** `sqlalchemy`, `alembic`, and `psycopg[binary]`
  are imported by `packages/persistence`, `migrations/`, and the migration tests but were absent
  from `[project].dependencies`. The install failure had masked this: fixing discovery alone would
  have moved the failure to the test step with `ModuleNotFoundError: sqlalchemy`. Proven by
  simulating the CI dependency set before declaring them.
- **Gitleaks had never scanned anything.** The action derived a commit range from the push event,
  which on a first push resolved to `<root>^` — the parent of the root commit, which cannot exist.
  It errored having scanned `~0 bytes` and failed the job. Replaced with a pinned CLI binary
  (8.30.1, SHA-256 verified) invoked over **all reachable commits** and **the working tree**,
  never an event-derived range. Checkout now uses `fetch-depth: 0`; it was `1`, which cannot be
  scanned for history at all.
- **CI validated narrower paths than local validation.** CI checked `packages tests` while local
  validation checked `packages tests scripts migrations`. The Makefile is now the single
  definition of every command and CI invokes those targets, so the two cannot drift. `rules.md`
  section 17 required this reconciliation.
- **The dependency scan was silently suppressed.** `pip-audit --strict || true` swallowed every
  result. `--strict` errors on `fintek` itself, which is an editable local install and not on
  PyPI; `--skip-editable` is the correct exclusion. The gate is now enforcing. Verified: exits 0
  on the current dependency set and exits 1 against a deliberately vulnerable pin.

#### Added

- `docs/runbooks/ci-failure.md` — reproducing each failure locally, and what not to do about it.
- `make migration-check` — offline Alembic upgrade and downgrade, now part of `make check`.
- A CI step asserting the installed distribution actually imports.
- `workflow_dispatch` trigger, and an explicit least-privilege `permissions: contents: read`.

#### Changed

- Type checking covers `packages scripts migrations`, 45 source files. `tests` is excluded
  deliberately and the reason is recorded: it reaches into SQLAlchemy internals where
  `Model.__table__` is typed as `FromClause`, and blanket ignores would weaken the check for the
  source that matters.
- `CLAUDE.md`, `techspecs.md`, `README.md`, `docs/testing/strategy.md`, and
  `docs/architecture/deployment.md` updated. The recorded warnings that CI cannot install the
  project, that gitleaks cannot run locally, and that CI omits `scripts` and `migrations` are
  removed **because they are no longer true**. The `master` branch warning is removed because the
  branch is now `main`.

---

### Sprint 2 alignment review — committed as `275db19`

A product-alignment audit against the fifteen core product requirements, a Git governance
amendment, and the resulting planning corrections. No feature code was added.

### Added

- `rules.md` sections 15 to 20: the COMMIT-AUTHORIZATION, PRE-COMMIT-VALIDATION, TEST-DISCOVERY,
  DOCUMENTATION-SYNCHRONIZATION, and GIT-SAFETY invariants, plus Sprint Completion and Git. No
  agent may create or push Git history without explicit per-operation user approval;
  `--dangerously-skip-permissions` and pre-approved tool-permission entries grant no Git
  authority. The former section 15 is renumbered to 21.
- `CLAUDE.md`: loaded automatically each session, requiring `rules.md` to be read and restating
  the commit and push authorization requirement.
- `docs/adr/ADR-0015-thread-first-delivery-sequence.md`: prove one vertical thread through every
  layer before widening any layer.
- `docs/dashboard/ux-specification.md`: the product surface, including the states previously
  unspecified — partial coverage, low confidence, refused out-of-scope requests, budget
  exhaustion, and session restoration.
- `docs/llm/analysis-model-benchmark.md`: the Deep Analysis model benchmark, which did not exist.
  Multi-turn retention, evidence grounding, and an adversarial scope-escape subset with
  zero-tolerance security gates. The deterministic detector is measured separately from the model.
- `docs/footnotes/period-comparison.md`: same-footnote comparison across periods, keyed on a
  stable topic key rather than a note number, which is not stable across filings.
- `metric_definitions/item_disclosure_exclusions.yaml`: the Item 408 and Item 1C exclusion list
  that canonicalization stage 2 reads. It was referenced by the algorithm and did not exist.
- `docs/sprints/SPRINT-0003.md`: the Sprint 3 plan, including a decided fixture strategy.
- `footnote_source_block`: per-attachment grouping audit columns — `grouping_method`,
  `grouping_confidence`, `grouping_evidence`, `competing_candidates`, `extraction_run_id`,
  `grouping_parser_version`, `grouping_decided_at`.
- `filing`: `completeness_confidence` and `reconciliation_status`.
- API: `/issuers/{cik}/footnote-topics` and `/issuers/{cik}/footnote-topics/{topic_key}`.
  Error code `UNSUPPORTED_FILTER`.
- Architecture tests: anti-vacuity guard, no-empty-stub guard, and a single-home guard for
  model-visible prompts. Migration tests for the attachment audit and completeness design.

### Changed

- `roadmap.md` rewritten into the thread-first sequence. Sprints 3 to 7 contain every dependency
  of the vertical slice; breadth work moves to Stage 2. Provider catalog verification, model
  selection, and cost measurement move from Phase 6 to Sprint 5, which is now an explicit
  go/no-go on unit economics. The zero-LLM dashboard test lands with the first read endpoint in
  Sprint 6 rather than at sprint 22.
- `docs/llm/model-benchmark.md` split into a tier-1 smoke benchmark of 15 footnotes in Sprint 5
  and the full tier-2 120-fixture program before backfill. A tier-1 pass is provisional and does
  not select a production model.
- `docs/footnotes/completeness.md`: eleven of thirteen counters documented as derived rather than
  stored, with their derivations. Storing a derivable count creates a second source of truth.
- `docs/footnotes/canonicalization-algorithm.md`: the grouping audit record is recorded on the
  child block, because stages 3 and 6 to 10 decide per child.
- ADR-0008 and ADR-0009 moved from ACCEPTED to PROVISIONAL. Both were decided in Sprint 1 with
  nothing deployable and their implementation phase roughly twenty sprints away.
- `rules.md` section 5: `bedrock.py` and `deep_analysis/scope.py` marked RESERVED rather than
  presented as implemented single-home owners.
- Current test counts corrected to 143 in `README.md`, `docs/testing/strategy.md`,
  `docs/architecture/deployment.md`, and `techspecs.md`. **Historical counts in
  `docs/sprints/SPRINT-0001.md` and the 0.1.0 entry below are left unchanged, because they are
  accurate records of what was true then.**
- `techspecs.md` section 3.6 corrected: it described the DERA download as PLANNED while
  section 2 recorded it as executed.

### Removed

- Eighteen packages containing only a docstring: `deep_analysis`, `domain`, `fact_lake`,
  `filing_acquisition`, `filing_discovery`, `filing_parser`, `financial_metrics`, `fiscal`,
  `footnote_canonicalizer`, `footnote_extractor`, `issuer_registry`, `metric_definitions`,
  `retrieval`, `summarization`, `table_parser`, `testing_support`, `validation`, `xbrl`. They
  reserved names up to twenty sprints ahead of their code and caused two architecture tests to
  pass while scanning nothing. Reserved names now live in `techspecs.md` section 2 with a status
  column, and an architecture test prevents the pattern returning.
- Empty `apps/` and `infrastructure/` directory trees, untracked by Git.
- `docs/deep-analysis/system-prompt.txt`, a byte-identical duplicate of
  `prompts/deep-analysis/v1.0.0/system.txt`. Two homes for one model-visible artifact drift, and
  only `prompts/` was scanned by the architecture tests.

### Data migrations

- `0001_initial_control_plane_schema.py` regenerated in place, adding nine columns. **The
  migration has never been applied to any database** — verified by connection refused on
  `127.0.0.1:5432` — so amending it is safe and avoids applying a known-incomplete schema to the
  live PostgreSQL that Sprint 3 creates. Offline upgrade DDL grew from 653 to 676 lines;
  downgrade remains 66 lines and symmetric.

### Fixed

- The roadmap's central contradiction: Phase 1 promised a vertical slice at sprints 3 to 5 while
  its dependencies were scheduled at sprints 8 to 33, and the sprint breakdown silently dropped
  the dashboard and Deep Analysis deliverables. The slice was described and scheduled nowhere.
- `classification=changed` was exposed by the API with nothing defining or computing it. It is
  now specified, and rejected with `UNSUPPORTED_FILTER` until the backing data exists.

## [0.2.0] — Sprint 2 — 2026-08-01

Discharges URGENT-01 and establishes the database schema.

### Added

- `packages/sec_client.client`: the SEC HTTP client. Built on the Sprint 1 limiter and throttle
  classifier. Streams to disk while hashing, and rejects rather than stores an HTML error page, a
  directory listing, wrong ZIP magic bytes, a body shorter than its declared Content-Length, a ZIP
  with no members, or a ZIP whose member fails CRC. Writes to a temporary path and renames only
  after every assertion passes.
- `scripts/mirror_dera.py`: the live DERA mirror, with size probe, dry run, monthly-only, and full
  modes. Produces a manifest and reconciles discovered against persisted.
- `packages/persistence`: the PostgreSQL control-plane schema. 24 tables, 36 indexes, 93
  constraints.
- `migrations/versions/0001_initial_control_plane_schema.py`: the initial migration, including a
  BEFORE UPDATE trigger on `xbrl_fact` that enforces append-only at the database level.
- `scripts/generate_initial_migration.py`: deterministic migration generation from model metadata,
  used because Alembic autogenerate requires a live database and this environment has none.
- 33 tests: 15 for the HTTP client, 14 for migrations, 4 for YAML library identity and alias
  bounding.

### Changed

- Roadmap URGENT-01 moved to COMPLETE with completion evidence. Risk R-01 CLOSED.
- Phase 0 marked COMPLETE.

### Fixed

- **Unbounded YAML alias expansion.** The Sprint 1 parser enforced size, depth, collection, and
  scalar limits AFTER parsing, which is useless against alias expansion because the allocation
  happens during parsing. Measured: a five-line document with nine anchors each referencing the
  previous nine expanded to 59,049 leaf nodes; two further levels exhaust memory. A pre-parse
  anchor and alias budget now rejects it. Found by the Sprint 2 YAML verification, not by review.

### Security

- YAML alias bomb protection, as above.
- The append-only guarantee on filed facts moved from a code comment to a database trigger, so it
  holds against a direct SQL session rather than only against application code.
- `llm_invocation` carries a check constraint restricting content format to plain_text or yaml,
  putting the LLM serialization invariant in the schema.

### Data migrations

- `0001_initial_control_plane_schema`. Verified by offline DDL generation in both directions.
  **Not yet applied to a live database**; see known issues.

### Operational changes

- **The DERA mirror is complete.** 78 of 78 discoverable packages held locally, 25.36 GiB, zero
  failures. The twelve monthly packages with no quarterly consolidation were secured first.
  `docs/runbooks/dera-mirror.md` records the run and the idempotency proof.

### Documentation

- ADR-0013 now pins the YAML parser (ruamel.yaml 0.19.1, YAML 1.2 core, pure safe mode) and
  documents the alias bound with its measurement.
- `techspecs.md`, `roadmap.md`, `docs/data-dictionary/README.md`, `docs/sec/dera-notes.md`, and
  `docs/runbooks/dera-mirror.md` synchronized with the implementation.

## [0.1.0] — Sprint 1 — 2026-08-01

The foundation sprint. Establishes durable project memory, the SEC-safety-critical primitives,
and the complete LLM content-boundary control set. No ingestion at scale and no real model calls.

### Added

- Repository scaffold: 25 domain packages, application shells, versioned prompt directories,
  test layout, and documentation tree.
- Governance documents: `rules.md`, `roadmap.md`, `techspecs.md`, `CHANGELOG.md`, `README.md`.
- 14 architecture decision records, ADR-0001 through ADR-0014.
- `packages/sec_identity`: CIK normalization, accession normalization, and SEC URL construction.
  The single home for these transforms, enforced by an architecture test.
- `packages/configuration`: eager settings validation, including SEC User-Agent validation that
  fails closed on a missing, generic, or emailless value.
- `packages/sec_client`: token-bucket rate limiting with separate global and full-text-search
  buckets, HTML 403 classification distinguishing a rate block from a configuration defect,
  reference-identifier extraction, directory-listing detection, and a typed error hierarchy
  carrying explicit retry classification.
- `packages/storage`: object-store abstraction with a filesystem backend, atomic writes, path
  traversal rejection, and SHA-256 hashing.
- `packages/observability`: structured logging with correlation identifiers and mandatory
  redaction of payload and secret fields.
- `packages/dera_notes`: package discovery by scraping the authoritative listing, classification
  handling the irregular 2010 filename suffixes, and a resumable mirror ledger.
- `packages/llm_gateway`: the complete model content boundary. Payload compiler, plain-text and
  YAML 1.2 serializers, hardened safe parser, boundary validator covering twenty prohibited
  constructs, token counter with a cross-serialization comparison harness, cost calculator that
  raises on an unpriced model, provider interface, and a deterministic mock provider.
- Six curated metric definitions: revenue, net income, operating cash flow, capital expenditures,
  total debt, and stock-based compensation.
- Production prompt files for footnote summarization and Deep Analysis, in `.txt` and `.yaml`
  only. Model-visible Markdown is prohibited and the prohibition is tested.
- Nine operational runbooks.
- 49 specification documents.
- 104 tests: 81 unit, 2 integration, 8 architecture, plus fixtures capturing real SEC 403 bodies
  and a directory listing.
- Docker Compose stack, Makefile, CI workflow, and environment template.

### Changed

- **The canonical footnote unit was corrected.** An earlier design counted 58 XBRL TextBlock
  facts as Apple's FY2025 footnote count. Direct verification shows 71 renderer reports, 16 in
  the Notes category, and **13 actual footnotes**. The three Notes-category entries that are not
  footnotes are Item 408 and Item 1C disclosures. This is a 4.5-fold correction to the unit of
  work and therefore to summarization cost. Recorded in ADR-0005.
- **The ingest ledger moved from SQLite to PostgreSQL.** The earlier reasoning was correct about
  DuckDB being unsuitable for concurrent upserts but did not follow through: PostgreSQL is
  already present and handles ten writes per second trivially. One fewer datastore. Recorded in
  ADR-0004.
- **The prior cost estimate was withdrawn.** It was computed on the wrong unit of work. Formulas
  and named placeholders replace it until parameters are measured. Recorded in ADR-0006.
- **The model content boundary replaced JSON and native tool calling.** The earlier design used a
  JSON summary schema, JSON Schema validation, and six native tools. All three are prohibited at
  the model boundary. Recorded in ADR-0013.

### Fixed

- Token bucket infinite loop. `tokens >= 1.0` compared exactly; after sleeping the computed delay
  the refill could land a fraction below 1.0 in binary floating point, so `acquire` spun forever
  on ever-smaller deltas. Found by the test suite hanging rather than by review. A nanotoken
  epsilon fixes it.
- Object store silently reinterpreted an absolute key as relative. It now rejects, because a
  caller passing `/etc/passwd` has a defect that should surface.
- YAML serializer could not represent forced-style scalars under the safe dumper. Explicit
  representers registered rather than falling back to round-trip mode.

### Security

- SEC User-Agent validation fails closed, preventing traffic that would certainly be blocked.
- Object keys cannot escape the store root.
- Log records redact payload bodies, prompts, and secrets.
- Model-visible content is validated in both directions against twenty prohibited constructs.
- Native tool calling is refused before any provider work.
- The YAML parser rejects duplicate keys, custom tags, and arbitrary object construction, and
  enforces limits on input size, nesting depth, collection size, scalar length, and document
  count.
- Budgets are enforced before invocation, never after.

### Data migrations

None. No database schema exists yet; it is Sprint 2.

### Operational changes

- `docs/runbooks/dera-mirror.md` records the rolling twelve-month retention window on monthly
  DERA packages. This is the only task in the project with an external deadline.
- Local development requires no model credentials. The mock provider exercises the full gateway
  path offline.

### Documentation

- All 49 specification documents carry an implementation status. Planned behaviour is never
  described as implemented.
