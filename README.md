# Kopexx

Kopexx pulls 10-K and 10-Q filings from SEC EDGAR, preserves the original documents exactly as SEC
published them, and then hands each filing **intact** to a language model you choose to work out
what it actually says. What comes back is checked against the preserved bytes before anyone sees
it. A second model you choose turns that into plain-language summaries. Browsing a finished result
never calls a model at all.

The reason to bother: a 10-K is a hundred pages of disclosure almost nobody reads in full.
Business, risk factors, legal proceedings, MD&A, controls, the statements, the notes behind them,
the exhibits, the certifications. Covering *all* of it — not the handful of sections something
finds interesting — is the whole idea.

**Under active development. Not usable yet. No model has ever been called.**

> **On the name.** The GitHub repo is `kopexx`. `FinTek` is the internal project name and the
> Python package namespace, so it turns up in paths and environment variables. Same project.

## The four models

You pick all four, independently, every time you run a job. Nothing is chosen for you and nothing
silently falls back to something else.

| Role | What it does |
|---|---|
| **Parsing** | Reads the intact filing and works out its structure |
| **Image** | Handles charts and images, but only if your parsing model can't see them itself |
| **Summary** | Turns an accepted parse into summaries |
| **Analysis / chat** | Answers questions about one company over one timeframe |

The candidates for the beta are GPT OSS 120B, NVIDIA Nemotron 3 Super 120B, Qwen3 235B A22B, Llama
4 Maverick and Qwen3 VL 235B. **None of them is configured or reachable right now**, and their
real IDs, limits and prices haven't been looked up yet.

## Why the model does the parsing

The first four sprints built the opposite: a deterministic parser that decided in code what a Part,
an Item, a footnote and a signature block were. It worked beautifully — on Apple, which was the
only company it had ever seen.

So a real corpus was acquired to check: **112 issuers, 613 filings, six transport eras, every
object hash-verified.** It disagreed. Filing packages run from 4 to 283 files. Malformed table
markup is normal before 2005. An entire era exposes no individual documents at all — only one big
submission file. 44 percent of primary documents are over roughly 200,000 estimated tokens, and the
largest is eight times the size of the Apple filing that had been treated as the worst case.

Every deterministic rule that fit Apple would have needed an exception per company per era, and
every exception is a place where a paragraph quietly disappears. So the model interprets, and the
backend proves the result against the original bytes. Full reasoning:
[ADR-0016](docs/adr/ADR-0016-corpus-first-model-first-architecture.md).

The old footnote work wasn't wasted — 43 canonical footnotes across four Apple filings, 117 of 117
child blocks attached correctly — but it's now a **benchmark for grading a model**, not the
definition of a correct parse.

## Nothing is sent in pieces

A filing either fits in your chosen parsing model, or that model can't be used for it. Full stop.

Nothing gets truncated, sliced, summarized-before-summarizing, or split into chunks, and no other
model gets quietly substituted. If it doesn't fit, you're told so — with the sizes and the limit —
and you pick a different model. That's the only honest way to promise nothing was dropped.

## Complete content, or an honest gap

Every human-readable range of a processed filing has to show up in the parse or be explicitly
marked unresolved. Every footnote the parse finds stays its own node with its own summary — never
merged into one lump called "Notes". If something can't be resolved, the filing reports `PARTIAL`
or `REVIEW_REQUIRED` rather than rounding itself up to complete.

The backend proves this against the preserved bytes. It doesn't take the model's word for it.

## Where the project actually is

| Phase | Status |
|---|---|
| **Phase 1** — representative filing corpus | **COMPLETE** |
| **Phase 1.5** — intact-source compatibility | **OPEN**, and it blocks Phase 2 |
| **Phase 2** — model contract and first real parsing experiments | **BLOCKED**, needs authorization |
| Phases 3–8 — orchestrator, images, summaries, UI, chat, persistence | not started |

**What exists today.** The SEC client with rate limiting and throttle classification; CIK,
accession and URL handling in one place; filing discovery; byte-exact acquisition with hashing and
provenance; the accession document inventory; the complete SEC DERA mirror (78 packages, 25.36 GiB,
all verified); the model gateway and its content boundary running against an in-process mock; and
the committed test fixtures and contracts.

**What does not exist.** Any orchestrator. Any parsed artifact. Any summary. Any UI. Any Deep Dive.
Any deployment. Any call to any model.

## Getting started

```bash
make install          # virtualenv and dependencies
cp .env.example .env  # then set SEC_USER_AGENT
make check            # format, lint, types, tests, migration reversibility
```

`make check` is the gate, and CI runs the same targets — the Makefile is the only place they're
defined, so the two can't drift apart.

`SEC_USER_AGENT` is required and startup fails without it. SEC wants a descriptive User-Agent with
a contact email on every request and denylists library defaults:

```
SEC_USER_AGENT="Kopexx Research you@example.com"
```

**No model credentials are needed, and none will work.** The default provider is an in-process mock
that exercises the whole gateway path offline.

### Running the full suite

```bash
make db-create-test          # disposable database for destructive migration tests
make db-create-integration   # disposable database for persistence integration tests
make db-upgrade-integration  # its schema
make test-no-skips           # fails if anything skips
make coverage                # with the 85% gate
```

Both database targets refuse to run unless they can prove the target is disposable and distinct.
Setup, including the one privileged step: [docs/runbooks/test-database.md](docs/runbooks/test-database.md).

## Databases

Three names, and **the application one deliberately doesn't exist**:

```
DATABASE_URL                    fintek                    not created; nothing reads or writes it
TEST_DATABASE_URL               fintek_test               migration tests drop every table in it
INTEGRATION_TEST_DATABASE_URL   fintek_integration_test   persistence tests load and clean it
```

Not hypothetical. The migration round-trip test once pointed at the application database, and
`make check` dropped every table and deleted 2,845 loaded facts while reporting green. A guard now
refuses to run anything destructive until it can prove the target is separate — comparing parsed
host, port, socket and database name, never the configured strings, because `@localhost/fintek` and
`@127.0.0.1:5432/fintek` are different strings and the same database.

The final schema is deliberately undesigned. It follows real model output, not the other way round
— guessing it early is exactly what produced the ontology that had to be withdrawn.

## Why AWS isn't set up

Because nothing needs it yet, and configuring it early would invite exactly the kind of
"it's-basically-working" claim this project has already had to unwind twice. Phase 1.5 is where
model availability, IDs, limits and prices get discovered for real, and it hasn't run.

When it does: Kopexx never handles a long-lived AWS key. Credentials come from federation or an
assumed role, always temporary. See [docs/security/aws-identity-and-secrets.md](docs/security/aws-identity-and-secrets.md).

## Layout

```
packages/            SEC identity and HTTP, storage, configuration, observability, the DERA
                     mirror and fact loader, filing discovery and acquisition, the model
                     gateway, the schema, and the demoted footnote/table benchmark packages
migrations/          Alembic
prompts/             versioned prompt files
metric_definitions/  curated concept priorities
scripts/             operational entry points
tests/               unit, integration, architecture, security
docs/                specs, ADRs, runbooks, sprint records
```

Packages get created when their code is written, not before.

---

The rules, what's built, what's next, and why each decision went the way it did:
[rules.md](rules.md), [roadmap.md](roadmap.md), [techspecs.md](techspecs.md).
