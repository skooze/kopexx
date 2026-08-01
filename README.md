# Kopexx

Kopexx pulls 10-K and 10-Q filings from SEC EDGAR, extracts the financial data and the notes to
the financial statements, and writes a plain-language summary of every footnote. The summaries
are generated offline and stored, so browsing the dashboard doesn't call a model. There's also an
optional Deep Analysis mode: a chat session locked to one issuer and one set of filings, for when
you want to dig into something specific.

Most of a 10-K is footnotes — the explanations behind the numbers, the accounting policy choices,
the debt covenants, the contingencies. They're the tedious part to read and the hard part to skim.
Summarizing all of them, rather than the handful a model finds interesting, is the point.

**This is under active development and not usable yet.** Filing ingestion, footnote extraction,
summarization, the dashboard, and Deep Analysis are specified but not built. See below for what
actually exists.

## Status

Sprint 2 is complete, plus an alignment review and a CI repair. Sprint 3 hasn't started.

What's implemented:

- SEC HTTP client with rate limiting and throttle classification
- CIK, accession, and URL normalization
- Object storage with hashing, filesystem backend
- Configuration with startup validation
- Structured logging
- A complete local mirror of the SEC DERA Financial Statement and Notes datasets — 78 packages,
  25.36 GiB, hash- and CRC-verified
- The LLM gateway and content boundary, with a mock provider
- A 24-table PostgreSQL schema and its initial migration

What's next, in [Sprints 3–7](roadmap.md): retrieve one issuer's filings and build reproducible
fixtures, extract canonical footnotes, run real-model summarization and measure what it costs,
build the read API and dashboard, then filing-scoped Deep Analysis. The idea is to get one company
working end to end before widening to the full issuer universe — see
[ADR-0015](docs/adr/ADR-0015-thread-first-delivery-sequence.md).

What doesn't exist: **no SEC filing has been retrieved yet.** No footnotes extracted, no summaries
generated, no dashboard, no Deep Analysis, nothing deployed. The migration hasn't been applied to
a live database — that's the first task in Sprint 3.

Current local validation:

```
143 tests passing, 2 skipped
92.94% coverage on the implemented packages (85% gate)
mypy clean across 45 source files
ruff format and lint clean
```

The two skips are live-PostgreSQL migration tests; they skip with an explicit reason when no
database is reachable. Everything else runs without one. CI is green on `main`.

## Getting started

```bash
make install          # virtualenv and dependencies
cp .env.example .env  # then set SEC_USER_AGENT
make check            # format, lint, types, tests, migration reversibility
```

`make check` is the gate. It's the same set of commands CI runs — the Makefile is the only place
they're defined, so the two can't drift.

You don't need Docker or a database for the test suite. If you want the local stack (Postgres,
MinIO, Redis) for migration work, `make up` starts it; that needs the Docker Compose plugin
installed.

No model credentials are needed either. The default provider is an in-process mock that exercises
the full gateway path offline.

`SEC_USER_AGENT` is required and startup fails without it. SEC wants a descriptive User-Agent with
a contact email on every request, and it denylists library defaults like `python-requests/2.31.0`.
Set something like:

```
SEC_USER_AGENT="Kopexx Research you@example.com"
```

Details on SEC's access rules and throttling behavior are in
[docs/sec/access-policy.md](docs/sec/access-policy.md).

To check the DERA mirror without downloading anything:

```bash
python scripts/mirror_dera.py --dry-run
```

## Layout

```
packages/            eight implemented libraries: SEC identity and HTTP,
                     storage, configuration, observability, DERA discovery,
                     the LLM gateway, and the database schema
migrations/          Alembic
prompts/             versioned prompt files, .txt and .yaml
metric_definitions/  curated concept priorities and footnote exclusions
scripts/             operational entry points
tests/               unit, integration, and architecture
docs/                specs, ADRs, runbooks, sprint records
```

Packages are created when their code is written, not ahead of it. Reserved names and their target
sprints are listed in [techspecs.md](techspecs.md), section 2.

## Design constraints

A few things are load-bearing, and changing them will break assumptions elsewhere.

**Every canonical footnote gets a stored summary.** Not the material ones, not a merged summary —
every one. Filings with incomplete coverage are shown as incomplete rather than rounded up.
[docs/footnotes/completeness.md](docs/footnotes/completeness.md)

**Normal dashboard reads don't invoke a model.** Searching, opening a filing, changing a
timeframe, expanding a footnote — all served from stored data. Summarization is an offline batch
job. [docs/dashboard/ux-specification.md](docs/dashboard/ux-specification.md)

**Deep Analysis is scoped and metered.** A session is bound to one issuer and one corpus for its
lifetime. The client sends a session ID and a message; scope and budgets are loaded server-side.
[docs/deep-analysis/product.md](docs/deep-analysis/product.md) and
[security.md](docs/deep-analysis/security.md)

**Model-visible content is plain text or one unfenced YAML 1.2 document.** No JSON, Markdown, XML,
or native tool schemas in either direction. Transport JSON and browser API JSON are outside this
boundary and fine. [docs/llm/content-boundary.md](docs/llm/content-boundary.md) and
[ADR-0013](docs/adr/ADR-0013-plain-text-or-yaml-llm-boundary.md)

**Filed SEC documents and deterministic facts are the source of truth.** Summaries are an index
into the filings, not evidence. Any number shown to a user traces back to a specific accession,
concept, and period. See `rules.md`, section 2.

Some of these are enforced by tests in `tests/architecture/`.

## Documentation

- [rules.md](rules.md) — coding standards, architecture rules, and the invariants that block a
  sprint from being marked complete
- [roadmap.md](roadmap.md) — what's built, what's next, and in what order
- [techspecs.md](techspecs.md) — what the code does today, component by component
- [CHANGELOG.md](CHANGELOG.md) — what changed and why
- [docs/adr/](docs/adr/) — 15 decision records with the reasoning and the rejected alternatives
- [docs/sprints/](docs/sprints/) — what each sprint actually delivered, including what didn't work
- [docs/runbooks/](docs/runbooks/) — operational procedures

## Contributing

Read [CLAUDE.md](CLAUDE.md) and [rules.md](rules.md) first. The short version: search for an
existing implementation before writing a new one, don't reimplement CIK, accession, fiscal, or
cost logic outside its owning package, keep prompt text out of application code, run `make check`
before proposing anything, and update the docs in the same change as the code.

If you add a new validation command, put it in the Makefile so CI picks it up too.
