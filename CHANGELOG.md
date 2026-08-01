# Changelog

All notable changes to FinTek are recorded here. This is not a commit dump: it records
user-visible, architecture-level, data-model, and operational changes.

Format follows Keep a Changelog, with two additional sections that matter for this system:
`Data migrations` and `Operational changes`.

## [Unreleased]

### Added

Nothing since Sprint 1.

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
