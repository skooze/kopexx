# Changelog

All notable changes to FinTek are recorded here. This is not a commit dump: it records
user-visible, architecture-level, data-model, and operational changes.

Format follows Keep a Changelog, with two additional sections that matter for this system:
`Data migrations` and `Operational changes`.

## [Unreleased]

### Added

Nothing since Sprint 2.

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
