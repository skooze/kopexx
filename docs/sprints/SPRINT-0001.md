# SPRINT-0001: Foundation, Governance, and the LLM Content Boundary

STATUS: COMPLETE
DATE: 2026-08-01

> **Forward note, added 2026-08-03. Nothing below this note has been edited.** Deliverables that
> survive: `sec_identity`, `configuration`, `sec_client`, `storage`, `observability`, the
> `llm_gateway` format machinery, and the governance documents. Deleted from the active tree on
> 2026-08-03: `packages/dera_notes`, `scripts/`, `metric_definitions/`, `prompts/footnote-summary/`,
> `docker-compose.yml`, and the footnote and financial documentation sets. No measurement below is
> disputed. Authoritative: `docs/adr/ADR-0017-delete-the-rejected-parser-and-application-persistence.md`.

## Objective

Establish durable project memory and the safety-critical primitives every later phase depends on:
SEC identity, rate control, storage, observability, DERA discovery, and the complete model
content-boundary control set. No ingestion at scale. No real model calls.

## Scope

In scope: repository scaffold, governance documents, ADRs, SEC identity library, SEC client
foundation, object storage, configuration validation, observability, DERA discovery and ledger,
LLM gateway, tests, CI, local stack.

Out of scope, deliberately: database schema and migrations, HTTP fetching, filing acquisition,
fact loading, footnote extraction, summarization, dashboard, Deep Analysis.

## Requirements addressed

Governance and project memory. SEC access and rate control. Issuer identity normalization. DERA
mirror discovery and resumability. The plain-text and YAML-only model content boundary, including
the centralized gateway, payload compiler, safe parser, boundary validator, token comparison
harness, and enforcement tests.

## Plan versus outcome

Planned and delivered: all of the above.

Planned and **not** delivered: the bulk DERA download itself, which requires the SEC HTTP client.
Discovery, classification, and the ledger are complete and tested; the download path raises a
clear not-implemented error rather than pretending to work. Carried to Sprint 2 as URGENT-01.

## Files created

Governance: `rules.md`, `roadmap.md`, `techspecs.md`, `CHANGELOG.md`, `README.md`.

ADRs, 14 files: `docs/adr/ADR-0001` through `ADR-0014`, plus `TEMPLATE.md`.

Packages, 55 Python modules:

```
packages/sec_identity/      cik.py accession.py urls.py errors.py __init__.py
packages/configuration/     settings.py user_agent.py errors.py __init__.py
packages/sec_client/        rate_limiter.py throttle.py errors.py __init__.py
packages/storage/           object_store.py hashing.py __init__.py
packages/observability/     logging.py correlation.py __init__.py
packages/dera_notes/        discovery.py ledger.py errors.py __init__.py
packages/llm_gateway/       gateway.py payload_compiler.py boundary_validator.py
                            yaml_serializer.py yaml_parser.py token_counter.py
                            cost_calculator.py capabilities.py errors.py __init__.py
                            providers/base.py providers/mock.py providers/__init__.py
plus 18 package __init__.py files for packages whose implementation is planned
```

Tests, 9 files: `tests/unit/` (7), `tests/integration/` (1), `tests/architecture/` (1), plus
`conftest.py` and 4 fixtures capturing real SEC 403 bodies, a directory listing, and a DERA
listing page.

Prompts, 7 files: `prompts/footnote-summary/v1.0.0/` (system.txt, user.yaml.jinja,
output-template.yaml, evaluation.yaml) and `prompts/deep-analysis/v1.0.0/` (system.txt,
request.yaml.jinja, output-template.yaml).

Metric definitions, 6 files: revenue, net income, operating cash flow, capital expenditures,
total debt, stock-based compensation.

Documentation, 49 markdown files plus 4 YAML and text specifications across `docs/architecture`,
`docs/sec`, `docs/financial`, `docs/footnotes`, `docs/llm`, `docs/deep-analysis`, `docs/api`,
`docs/testing`, `docs/operations`, and 10 runbooks.

Project: `pyproject.toml`, `Makefile`, `docker-compose.yml`, `.env.example`, `.gitignore`,
`.github/workflows/ci.yml`, `scripts/mirror_dera.py`.

## Files modified

Three files were modified after their initial write, each to fix a real defect found by testing:

- `packages/sec_client/rate_limiter.py` — epsilon fix for the infinite-loop defect below.
- `packages/storage/object_store.py` — reject absolute keys rather than silently reinterpreting.
- `packages/llm_gateway/yaml_serializer.py` — register representers for forced-style scalars.

`ruff format` reformatted 19 files and `ruff check --fix` corrected 15 lint findings across the
tree.

## Schema changes

None. No database schema exists yet.

## API changes

None. No API exists yet.

## Prompt changes

Initial versions created at v1.0.0 for footnote summarization and Deep Analysis. Both are `.txt`
and `.yaml`. Model-visible Markdown is prohibited and the prohibition is enforced by an
architecture test.

## Model changes

None. The only provider is the deterministic mock. No real model was invoked during this sprint.

## Tests added

104 tests.

```
tests/unit/test_sec_identity.py          16
tests/unit/test_configuration.py          6
tests/unit/test_sec_client.py             9
tests/unit/test_dera_notes.py             8
tests/unit/test_llm_boundary.py          26
tests/unit/test_yaml_parser.py           10
tests/unit/test_storage.py                6
tests/integration/test_dera_mirror.py     2
tests/architecture/test_architecture.py   8
```

Every test named in the sprint requirements exists and passes, including the twenty
serialization-enforcement tests and the architecture test asserting no provider SDK is imported
outside the provider adapter.

## Tests run and results

Commands executed and their observed output:

```
$ ./.venv/bin/ruff format --check packages tests
65 files already formatted

$ ./.venv/bin/ruff check packages tests
All checks passed!

$ ./.venv/bin/mypy packages --ignore-missing-imports
Success: no issues found in 55 source files

$ ./.venv/bin/python -m pytest tests
104 passed in 0.27s

$ ./.venv/bin/python -m pytest tests -q --cov=... --cov-report=term
TOTAL  1046  58  94%
```

Coverage by implemented package ranges from 79 percent (`sec_identity/accession.py`, where the
uncovered lines are malformed-input error branches) to 100 percent (`storage/hashing.py`,
`sec_client/errors.py`, `sec_identity/errors.py`).

The `mirror_dera.py` script was executed and observed to fail closed without `SEC_USER_AGENT`,
then to discover all six fixture packages correctly with it set, including the two irregular
2010 filenames.

## Benchmarks

None. Model benchmarking requires a real provider and is Phase 6 work, gated on ADR-0006.

Two measurements were taken and recorded in documentation:

- YAML 1.2 core schema leaves `yes`, `no`, `on`, `off` as strings and converts an unquoted
  `0000320193` to the integer `320193`.
- The `-xbrl.zip` bundle for Apple's 10-Q is 166,630 bytes against a measured mean complete
  submission of 11,082,089 bytes.

## Known issues

1. The rate limiter is in-process. Multi-process ingestion requires a Redis-backed bucket because
   the SEC limit is aggregate across machines. BLOCKING for Phase 4.
2. The SEC HTTP client does not exist, so `mirror_dera.py` cannot download. Discovery, ledger,
   and resumability are complete and tested. BLOCKING for URGENT-01.
3. Canonical grouping by role URI is verified on exactly one filing. BLOCKING for Phase 5.
4. Token estimation is a character-ratio heuristic, not billing-grade.
5. Provider catalog and pricing unverified. BLOCKING for any cost commitment.
6. Authentication is a local single-user implementation. BLOCKING for public deployment.

## Deferred work

Database schema and migrations, HTTP client, DERA TSV loading, and everything in Phases 1 through
10. All are recorded in `roadmap.md` with target sprints.

## Documentation updated

`rules.md`, `roadmap.md`, `techspecs.md`, `CHANGELOG.md`, `README.md`, 14 ADRs, 49 specification
documents, 10 runbooks, and this record. Every document carries an implementation status and no
planned behaviour is described as implemented.

## Roadmap changes

Phase 0 marked COMPLETE except the bulk DERA download. URGENT-01 marked IN_PROGRESS with Sprint 2
as target. Six known limitations recorded. Seven risks registered.

## ADRs created

ADR-0001 through ADR-0014. Three of them reverse an earlier decision and say so explicitly:
ADR-0004 (PostgreSQL replaces SQLite for the ingest ledger), ADR-0005 (13 canonical footnotes,
not 58 TextBlock facts), and ADR-0013 (plain text or YAML replaces JSON and native tool calling).

## Deployment notes

Nothing is deployable. There is no API, no database, and no infrastructure definition. The local
stack runs and the test suite passes.

## Rollback notes

No migrations and no deployed state, so rollback is `git revert`. The virtualenv is disposable and
rebuildable with `make install`.

## Next recommended sprint

**SPRINT-0002: DERA mirror execution and the database schema.**

Deliver the SEC HTTP client with the rate limiter and throttle classification already built,
execute URGENT-01 against the live listing, and create the PostgreSQL schema and first migration
covering issuers, listings, filings, canonical footnotes, source blocks, tables, summaries, jobs,
and the ingest ledger.

Sequenced this way because URGENT-01 has an external deadline and the schema is a prerequisite
for everything in Phase 1.
