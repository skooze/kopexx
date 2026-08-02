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

**Under active development. Not usable yet.**

> **On the name.** The GitHub repo is `kopexx`. `FinTek` is the internal project name and the
> Python package namespace, so it turns up in paths, the database name, and environment variables.
> Same project.

## Status

**Sprint 4 of 7.** Four Apple filings have been through every layer that exists: discovered,
fetched, hashed, loaded, reconciled, and split into footnotes. Nothing has been summarized yet and
nothing is deployed.

The plumbing:

- SEC HTTP client — rate limiting, throttle classification (SEC signals a block with a 403 and an
  HTML body, not a 429), and assertions that reject a directory listing served as a filing
- CIK, accession, and URL normalization, in exactly one place
- Object storage with content hashing; configuration validated at startup; structured logging
- The model gateway and its content boundary, running against an in-process mock
- A 24-table PostgreSQL schema, applied to a live database

The data, all of it real:

- The complete SEC DERA Financial Statement and Notes mirror — **78 packages, 25.36 GiB**, every
  one hash- and CRC-verified. The monthly packages SEC deletes after twelve months were pulled
  first
- **134** Apple filings discovered back to 1994, reconciled gap-free against SEC's quarterly
  index. Four preserved in full, with provenance
- **2,845** facts loaded across those four, each load checked nine ways before it counts

And the part the project exists for:

- **43 canonical footnotes** across the four filings
- **117 of 117** child disclosure blocks attached to the right parent. Zero orphans
- Every attachment records its method, its confidence, the evidence, and the candidates it beat
- No model participates in any of it. Every decision is a string comparison or a count

Still missing: summarization, the dashboard, Deep Analysis. Those are Sprints 5 through 7 in
[roadmap.md](roadmap.md), which runs one company through every layer before widening to more.

## Getting started

```bash
make install          # virtualenv and dependencies
cp .env.example .env  # then set SEC_USER_AGENT
make check            # format, lint, types, tests, migration reversibility
```

`make check` is the gate, and CI runs the same targets. The Makefile is the only place they are
defined, so the two cannot drift apart.

`SEC_USER_AGENT` is required — startup fails without it. SEC wants a descriptive User-Agent with a
contact email on every request, and denylists library defaults like `python-requests/2.31.0`:

```
SEC_USER_AGENT="Kopexx Research you@example.com"
```

No model credentials are needed. The default provider is an in-process mock that exercises the
whole gateway path offline.

Most of the suite runs without a database and skips what needs one, with a reason. For everything:

```bash
make db-upgrade         # schema
make db-create-test     # the disposable database destructive tests use
make test-no-skips      # fails if anything skips
```

Two things worth running by hand:

```bash
python scripts/load_dera_partition.py 0000320193-25-000079
python scripts/mirror_dera.py --dry-run
```

The loader exits non-zero unless all nine reconciliation checks pass. Running it twice inserts
nothing the second time.

## Databases

Two, deliberately:

```
DATABASE_URL       fintek        the application database, holds loaded facts
TEST_DATABASE_URL  fintek_test   disposable; migration tests drop every table in it
```

They have to be different, and a guard refuses to run destructive tests until it can prove they
are — comparing parsed host, port, socket, and database name rather than the configured strings.
`@localhost/fintek` and `@127.0.0.1:5432/fintek` are different strings and the same database.

Not hypothetical. The migration round-trip test once pointed at the application database, and
`make check` dropped every table and deleted 2,845 loaded facts while reporting green. Setup and
the full story: [docs/runbooks/test-database.md](docs/runbooks/test-database.md).

Locally, PostgreSQL uses peer authentication over the Unix socket — the kernel vouches for the
connecting user, the role has no password verifier, and `DATABASE_URL` is a role name and a socket
path with nothing secret in it. That works only because client and server share a host.

CI is different on purpose: a disposable password written openly into the workflow, for a
container that lives one job and holds public SEC data.

Neither is a deployment answer. How a deployed database authenticates is still undecided.

## Layout

```
packages/            thirteen libraries: SEC identity and HTTP, storage, configuration,
                     observability, the DERA mirror and fact loader, filing discovery and
                     acquisition, footnote extraction and canonicalization, table parsing,
                     the model gateway, and the database schema
migrations/          Alembic
prompts/             versioned prompt files
metric_definitions/  curated concept priorities and footnote exclusions
scripts/             operational entry points
tests/               unit, integration, and architecture
docs/                specs, ADRs, runbooks, sprint records
```

Packages get created when their code is written, not before. Reserved names, and the sprint each
one is due in, are in [techspecs.md](techspecs.md) section 2.

## Design constraints

A handful of things are load-bearing. Changing any of them breaks assumptions somewhere else.

**Every canonical footnote gets a stored summary.** Not the material ones, not a merged one. A
filing with incomplete coverage displays as incomplete rather than getting rounded up — the count
is computed, never assumed.

**Ordinary dashboard reads never invoke a model.** Searching, opening a filing, changing a
timeframe, expanding a footnote: all served from stored data. Summarization is a batch job that
runs offline.

Deep Analysis is the one place a model answers a live question, and it is hemmed in on purpose —
bound to one company and one corpus for the life of the session, metered against turn, token, and
cost budgets. The client sends a session ID and a message. Scope is loaded server-side, so a
tampered request cannot widen it.

**Filed documents and deterministic facts are the source of truth.** Summaries index the filings;
they are not evidence. Any number a user sees traces back to a specific accession, concept, and
period.

Filed facts are immutable. A restatement appends a new row, and a trigger rejects any attempt to
update an old one.

Most of these have tests in `tests/architecture/` that fail if they stop being true.

---

Everything else — the rules, what is built, what is next, and why each decision went the way it
did — lives in [rules.md](rules.md), [roadmap.md](roadmap.md), and [techspecs.md](techspecs.md).
