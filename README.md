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

**Under active development. Not usable yet.** Real filings have now been sent to real models, and
there is a local review UI for reading a parse beside the filing it came from. That is a long way
from a product: nothing is deployed, there is no database, and no summary or chat capability
exists.

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
4 Maverick and Qwen3 VL 235B. As of 2026-08-03 all five are mapped to real provider models,
reachable, and priced — see
[the capability snapshot](docs/llm/bedrock-capability-snapshot.yaml), which is the only place those
facts are written down.

Two of the five can actually read an image, and both proved it by reading one rather than by having
a checkbox on a product page. Their context windows differ by a factor of eight, which matters when
44 percent of the filings measured are over roughly 200,000 estimated tokens.

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

The old footnote work produced a real measurement — 43 canonical footnotes across four Apple
filings, 117 of 117 child blocks attached correctly — and the code that produced it has now been
**deleted**, not kept as a benchmark. Grading a model against a deterministic parse would quietly
make the deterministic answer authoritative again, and a yardstick built from one company can't
speak for the other 111. What a parse is checked against is the preserved source bytes.
[ADR-0017](docs/adr/ADR-0017-delete-the-rejected-parser-and-application-persistence.md).

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
| **Phase 0** — representative filing corpus | **COMPLETE** |
| **Phase 0.5** — repository cleanup and corpus reverification | **COMPLETE** |
| **Phase 1** — secure AWS access and model-capability verification | **COMPLETE** 2026-08-03 |
| **Phase 2** — parser experiments *and* the review UI, built together | **COMPLETE** 2026-08-03 |
| **Phase 2.1** — model-directed multipart parsing | **COMPLETE** 2026-08-04 |
| **Phase 2.2** — source inventory, completeness ledger, Bedrock deep dive | **COMPLETE** 2026-08-04, except the benchmark run, which is **blocked** |
| Phases 3–8 — optional model stages, persistence, beta UI, Deep Dive | not started |

**What exists today.** Nineteen small packages. The nine from before — SEC identity, the
rate-limited SEC client, configuration, structured logging, object storage, filing discovery,
byte-exact acquisition, the model gateway and the capability catalog — plus seven from Phase 2:
durable evaluation storage, mechanical source-set assembly, output validation against the preserved
bytes, hash-locked prompt versions, the orchestrator, and the review API and its pages. The model
gateway now has a real Bedrock adapter, and the capability catalog now has the four-role router it
was missing. Phase 2.1 added the model-directed multipart protocol; Phase 2.2 added two more, a
mechanical inventory of a filing and a completeness ledger measured against it.

**How much of a filing did the parse actually cover?** Until Phase 2.2 nothing could answer that. A
citation rate counts the model's own citations — a paragraph it never mentioned never entered the
count — so a parse that quietly skipped half a filing and cited the other half accurately looked
exactly like one that read all of it. There is now a count of the filing itself: every visible span,
every table, every filed image, measured from the preserved bytes before any model is asked
anything. Each one ends up covered, unresolved, excluded by a person, or **silently omitted** — and
that last number is the whole point. Nothing in it decides what a table or a paragraph *means*.

**One of the five models cannot read a modern Apple 10-Q at all.** Not "not well" — at all. The
filing is roughly twice what fits in GPT OSS 120B's context, so it is refused with the sizes and the
limit, which is the promise on the tin. Two of the other four fit only by asking for a shorter
answer than they are capable of, and the remaining two fit only at exactly their maximum. A shorter
answer means more calls, and every call re-sends the whole filing. Running the four that can take it
costs about `USD 13.37` against `USD 5.00` authorized, so **the benchmark has not been run** and no
model was invoked in this phase at all.

**And a UI you can actually open.** `make review` starts it on `127.0.0.1`. Pick a company, pick a
parsing model, choose a protocol, see what it would cost, run it, and read the parse beside the
filing — raw, parsed, or both at once, with every citation checked against the original bytes.

**One filing's parse no longer has to fit one model response.** Three of the five candidates cap
output at 8,000 tokens, and Phase 2 measured what that costs: the deepest parse it produced was
itself cut off with no way to finish. So a filing can now be parsed the way a person would read
it — the model looks at the whole thing, says how it divides, and then produces one part at a
time, with the complete filing in front of it every single time. If a part turns out too big, the
model splits it. If a response gets cut off, that response is kept as evidence and the model is
asked how to divide the part instead — never to "carry on", which is a thing no model can
actually do reliably. At the end the backend puts the pieces in the order the model gave them,
under the titles the model chose, and changes nothing.

**What does not exist.** Any database. Any cache. Any summary. Any Deep Dive. Any deployment. Any
image or chat capability — Phase 2 and Phase 2.1 both ran the parsing stage only, and the
orchestrator refuses to run another. You can mark a parse approved; that records a judgement and
nothing else happens. **No parser has been picked.** All five are still on the table, and the
single-response protocol still runs, so the two can be compared rather than assumed about. **And no
completeness figure exists for any model on any filing yet**, because the run that would produce one
is the one waiting on a budget decision.

**What was deleted on 2026-08-03.** The deterministic footnote and table parser, the 24-table
PostgreSQL schema and its migrations, the DERA mirror and fact loader, the accession document
classifier, and every script and specification that served them. Not deprecated, not moved to an
`oracle/` directory — deleted. Git history is the archive.

## Getting started

```bash
make install          # virtualenv and dependencies
cp .env.example .env  # then set SEC_USER_AGENT
make check            # format, lint, types, tests
make review           # the parser-review UI on http://127.0.0.1:8765
```

`make review` works out of the box with no credentials: the default provider is an in-process mock
that exercises the whole path offline. It binds to loopback, and it refuses to bind anywhere else
without a development secret — an unauthenticated review UI on a network is a remote control for
someone else's bill.

To reach a real model you need `pip install -e '.[aws]'`, `LLM_PROVIDER=bedrock`, an `AWS_REGION`,
and temporary credentials from your own federated login. There is no key to paste anywhere.

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
make test-no-skips   # fails if anything skips
make coverage        # with the 85% gate
```

**Nothing needs setting up first.** No database, no network, no credentials — the suite has no
environmental precondition at all, which is why a skip in it has no legitimate cause.

## Databases

**There aren't any.** The application database was never recreated after it was dropped, and the
schema, the ORM, the migrations and every test that opened a connection have now been deleted too.
Nothing in this repository can reach a database.

That isn't an oversight. The 24-table schema was designed before a single model had ever parsed a
filing, and it encoded an interpretation no model had produced. The next one gets designed from
artifacts real models actually return — and once there is something worth keeping, approved
artifacts go to durable storage with a 24-hour Redis cache in front of them, never the other way
round.

## AWS

Kopexx never handles a long-lived AWS key. Credentials come from federation or an assumed role,
always temporary, resolved by the SDK's own provider chain — see
[docs/security/aws-identity-and-secrets.md](docs/security/aws-identity-and-secrets.md).

Phase 1 used that to find out what the five candidate models actually are: real identifiers, which
regions they answer in, what they cost, how much context they take, and whether the ones advertised
as multimodal can really read a picture. Seven test calls, twenty-three hundredths of a cent, no
filing content. How to redo it:
[the discovery runbook](docs/runbooks/bedrock-capability-discovery.md). Why the output is a dated
document rather than a provider adapter:
[ADR-0018](docs/adr/ADR-0018-verified-capability-snapshot-over-a-provider-adapter.md).

**The test suite still needs no AWS access, and neither does CI.** That is deliberate: a test that
quietly needs a cloud credential is a test that skips everywhere it isn't there.

## Layout

```
packages/   SEC identity and HTTP, storage, configuration, observability, filing discovery
            and acquisition, the model gateway and its Bedrock adapter, the capability catalog
            and router, evaluation storage, source transport, coverage validation, prompt
            versions, the orchestrator, the review API and pages, the multipart protocol, the
            mechanical source inventory and the completeness ledger. Nineteen of them.
prompts/    versioned prompt files, locked by hash
tests/      unit, integration, architecture, fixtures
docs/       specs, ADRs, runbooks, sprint records
var/        gitignored: preserved SEC objects, the 613-filing research corpus, the DERA mirror,
            and evaluation-run evidence
```

**No JavaScript build step, and no npm.** The review UI is rendered in Python and served by the
standard library. Its stylesheet and its one small script are Python constants. Adding a framework
and a bundler would have been several dependencies bought for routing.

Packages get created when their code is written, not before.

---

The rules, what's built, what's next, and why each decision went the way it did:
[rules.md](rules.md), [roadmap.md](roadmap.md), [techspecs.md](techspecs.md).
