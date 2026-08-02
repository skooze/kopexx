# Kopexx

Kopexx pulls 10-K and 10-Q filings from SEC EDGAR, extracts the financial data and the notes to
the financial statements, and writes a plain-language summary of every footnote. Summaries are
generated offline and stored, so browsing the dashboard never calls a model. A separate Deep
Analysis mode opens a chat session locked to one company and one set of filings, for digging into
something specific.

The reason to bother: most of a 10-K is footnotes. The statements themselves are a page or two;
the rest explains the accounting policy choices, the debt covenants, the tax positions, the
contingencies. That is the part worth reading and the part nobody has time to skim. Summarizing
all of them — not the handful a model finds interesting — is the whole idea.

**This is under active development and not usable yet.** See below for what exists.

> **On the name.** The GitHub repository is `kopexx`. `FinTek` is the internal project name and
> the Python package namespace, so it appears in paths, the database name, and environment
> variables. Same project; `Kopexx` is the public one.

## Status

Sprint 3 is complete. Filings are retrieved and preserved with provenance, and their numeric facts
are loaded into PostgreSQL and reconciled against the source.

What works:

- SEC HTTP client with rate limiting, throttle classification, and content assertions
- CIK, accession, and URL normalization
- Object storage with content hashing
- Configuration with startup validation, and structured logging
- A complete local mirror of the SEC DERA Financial Statement and Notes datasets — 78 packages,
  25.36 GiB, hash- and CRC-verified
- The model gateway and its content boundary, with a mock provider
- A 24-table PostgreSQL schema, applied and verified against a live database
- Filing discovery and inline-XBRL acquisition — 134 Apple filings discovered back to 1994,
  reconciled gap-free against SEC's quarterly index; four preserved in full
- A DERA fact loader: package selection, parsing, normalization, validation, idempotent
  insertion, and reconciliation. 2,845 facts loaded across those four filings

What does not exist yet: **canonical footnote extraction, summarization, the dashboard, and Deep
Analysis.** No footnote has been extracted, no summary generated, nothing deployed. Those are
Sprints 4 through 7 in [roadmap.md](roadmap.md), which takes one company through every layer
before widening to more.

Current local validation:

```
337 tests passing, 0 skipped
93% coverage on the implemented packages (85% gate)
mypy clean across 65 source files
ruff format and lint clean
```

## Getting started

```bash
make install          # virtualenv and dependencies
cp .env.example .env  # then set SEC_USER_AGENT
make check            # format, lint, types, tests, migration reversibility
```

`make check` is the gate. CI runs the same targets — the Makefile is the only place they are
defined, so the two cannot drift.

`SEC_USER_AGENT` is required and startup fails without it. SEC wants a descriptive User-Agent with
a contact email on every request and denylists library defaults like `python-requests/2.31.0`:

```
SEC_USER_AGENT="Kopexx Research you@example.com"
```

No model credentials are needed. The default provider is an in-process mock that exercises the
full gateway path offline.

Most of the suite needs no database and skips the parts that do, with a reason. To run everything:

```bash
make db-upgrade         # schema
make db-create-test     # the disposable database destructive tests use
make test-no-skips      # fails if anything skips
```

To load a filing's facts, or to check the DERA mirror without downloading anything:

```bash
python scripts/load_dera_partition.py 0000320193-25-000079
python scripts/mirror_dera.py --dry-run
```

The loader exits non-zero unless all nine reconciliation checks pass, and re-running it inserts
nothing.

## Databases

Two, on purpose:

```
DATABASE_URL       fintek        the application database, holds loaded facts
TEST_DATABASE_URL  fintek_test   disposable; migration tests drop every table in it
```

They must be different, and a guard refuses to run destructive tests unless it can prove they are
— comparing parsed host, port, socket, and database name, not the configured strings. This is not
hypothetical: the migration round-trip test once ran against the application database, and
`make check` deleted 2,845 loaded facts while reporting green. Setup and details in
[docs/runbooks/test-database.md](docs/runbooks/test-database.md).

**On the local development host**, PostgreSQL uses peer authentication over the Unix socket: the
kernel vouches for the connecting user, the role has no password verifier, and `DATABASE_URL` is a
role name and a socket path with nothing secret in it. That works only because client and server
share a host.

**CI is different, deliberately.** Its PostgreSQL service uses a fixed, disposable password
written openly in the workflow — the container lives for one job and holds public SEC data.

Neither is a deployment answer. How a deployed database authenticates is undecided.

## Layout

```
packages/            ten libraries: SEC identity and HTTP, storage, configuration,
                     observability, the DERA mirror and fact loader, filing discovery
                     and acquisition, the model gateway, and the database schema
migrations/          Alembic
prompts/             versioned prompt files
metric_definitions/  curated concept priorities and footnote exclusions
scripts/             operational entry points
tests/               unit, integration, and architecture
docs/                specs, ADRs, runbooks, sprint records
```

Packages are created when their code is written, not ahead of it. Reserved names and their target
sprints are in [techspecs.md](techspecs.md), section 2.

## Design constraints

A few things are load-bearing; changing them breaks assumptions elsewhere.

**Every canonical footnote gets a stored summary** — not the material ones, not a merged one.
Filings with incomplete coverage are shown as incomplete rather than rounded up.

**Ordinary dashboard reads never invoke a model.** Searching, opening a filing, expanding a
footnote — all served from stored data. Summarization is an offline batch job.

**Deep Analysis is scoped and metered.** A session is bound to one company and one corpus for its
lifetime. The client sends a session ID and a message; scope and budgets are loaded server-side.

**Filed documents and deterministic facts are the source of truth.** Summaries index the filings;
they are not evidence. Any number shown to a user traces back to a specific accession, concept,
and period.

**Filed facts are immutable.** A restatement appends a new observation; a database trigger rejects
any attempt to update one.

Several of these are enforced by tests in `tests/architecture/`.

## Documentation

- [rules.md](rules.md) — coding standards, architecture rules, and the invariants that block a
  sprint from completing
- [roadmap.md](roadmap.md) — what is built, what is next, and in what order
- [techspecs.md](techspecs.md) — what the code does today, component by component
- [CHANGELOG.md](CHANGELOG.md) — what changed and why
- [docs/adr/](docs/adr/) — decision records, with the reasoning and the rejected alternatives
- [docs/sprints/](docs/sprints/) — what each sprint delivered, including what did not work
- [docs/runbooks/](docs/runbooks/) — operational procedures

## Contributing

Read [CLAUDE.md](CLAUDE.md) and [rules.md](rules.md) first. The short version: look for an
existing implementation before writing a new one, do not reimplement CIK, accession, or fiscal
logic outside its owning package, keep prompt text out of application code, run `make check`
before proposing anything, and update the docs in the same change as the code.

If you add a validation command, put it in the Makefile so CI picks it up too.
