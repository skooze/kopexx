# Operations

> **RE-FOUNDED 2026-08-03. NEEDS_REVISION.** The subjects of a large part of this document were
> deleted from the active tree: the DERA mirror and fact loader, the XBRL fact lake, deterministic
> footnote extraction and canonical grouping, the application persistence layer, its migrations and
> the local database stack. The product is orchestrator-driven and model-first — the selected
> parsing model owns semantic interpretation and the backend transports, preserves, validates and
> proves coverage against preserved bytes. What survives here is SEC transport, rate limiting,
> throttling, structured logging and object storage. The rest is withdrawn and marked, not silently
> carried forward. Authoritative:
> `docs/adr/ADR-0017-delete-the-rejected-parser-and-application-persistence.md`,
> `docs/adr/ADR-0016-corpus-first-model-first-architecture.md` and `roadmap.md`.
>
> **UPDATED 2026-08-03 BY PHASE 1.** AWS identity is verified and five models have answered a
> one-word test call. That is reachability, not operation: **nothing is deployed, no SEC filing has
> been sent to any model, and no provider adapter exists.** THAT SENTENCE IS SUPERSEDED — see the Phase 2 note below, which is authoritative. Every threshold below that is not marked
> IMPLEMENTED is a target, not a measurement. The verified capability evidence is
> `docs/llm/bedrock-capability-snapshot.yaml`; the procedure that produced it is
> `docs/runbooks/bedrock-capability-discovery.md`.
>
> **UPDATED 2026-08-03 BY PHASE 2, SUPERSEDING PART OF THE NOTE ABOVE.** Three clauses of the
> Phase 1 note have expired and are corrected here rather than edited away: a provider adapter now
> exists (`packages/llm_gateway/providers/bedrock.py`), there is a runnable application
> (`make review`), and the operator-facing procedure for it is IMPLEMENTED and written up below
> under [Running the parser-review application](#running-the-parser-review-application). The rest
> of the Phase 1 note stands: **nothing is deployed** — the application binds loopback on a
> developer's own machine — and every threshold in this document that is not marked IMPLEMENTED is
> still a target rather than a measurement. Phase 2 runs the PARSING STAGE ONLY; the image, summary
> and analysis roles are routed but raise `StageNotAuthorizedError` when invoked. Redis and the
> authoritative persistent store remain DEFERRED.

IMPLEMENTATION STATUS: PLANNED; structured logging IMPLEMENTED (Sprint 1); the parser-review
application IMPLEMENTED (Phase 2, 2026-08-03)

The scheduling, idempotency, metric and alert sets for parsing, summarization and persistence are
DEFERRED. They are redesigned from real model responses and accepted artifacts once Phase 2 has
produced any, rather than inherited from a pipeline that no longer exists.

## Running the parser-review application

IMPLEMENTED (Phase 2, 2026-08-03). One developer, one machine, one process, loopback. This is the
only thing in this document an operator can run today.

```bash
make review
```

The recipe is a single line that calls `packages.review_api.serve()`, which builds `Settings` from
the process environment, assembles the application and starts a threaded `http.server`. No
framework, no ASGI server, no bundler, no npm, no new runtime dependency — the repository's whole
runtime dependency list is two packages and the review UI added nothing to it. On
start-up the process prints its URL and its bind mode, and prints a second warning line whenever
the bind leaves loopback.

**EVERY INVALID CONFIGURATION FAILS AT START-UP, BEFORE ANYTHING GENERATES TRAFFIC OR SPENDS
MONEY.** `packages/review_api/app.py` is the only module that knows every part exists, so it is
where each package's own refusal surfaces: `ReviewSettings` refuses a non-loopback bind without a
secret, `LlmSettings` refuses a real provider without a region, `validate_user_agent` refuses a
User-Agent SEC would answer with a 403, the capability catalog refuses to run without a supplied
snapshot, and the prompt registry refuses a prompt whose bytes have moved. A configuration error is
one clear message at second zero rather than a run that fails halfway with money already spent.

### Environment

Everything `packages/configuration.ReviewSettings` reads. Every one has a default except the
development secret, which deliberately has none — an empty placeholder documents an unsafe design
as the expected one.

| Variable | Default | What it does |
|---|---|---|
| `REVIEW_BIND_HOST` | `127.0.0.1` | Listening interface. Anything outside `127.0.0.1`, `::1`, `localhost` is a non-loopback bind and demands the secret below. |
| `REVIEW_BIND_PORT` | `8765` | Listening port. |
| `REVIEW_DEV_SECRET` | unset | Development authentication secret, minimum 16 characters. Required for, and only for, a non-loopback bind. Belongs in ignored environment state, never in a tracked file. |
| `EVALUATION_ROOT` | `./var/evaluation-runs` | Where run evidence and the spend journal are written. Gitignored host state. |
| `PROMPT_DIRECTORY` | `./prompts/parser` | The versioned, SHA-256 hash-locked prompt registry. Editing a version that has been used fails. |
| `CAPABILITY_SNAPSHOT` | `./docs/llm/bedrock-capability-snapshot.yaml` | The reviewed capability evidence the four-role router reads. It is supplied, never discovered at runtime, and it is the single home of every model identifier, region, limit and price. |
| `CORPUS_MANIFEST` | `./var/research-corpus/meta/filings.json` | The preserved research corpus the search panel offers and the source inventory resolves bytes from. Both read the same manifest, so the two cannot describe different corpora. |
| `REVIEW_AUTHOR` | `local-developer` | The label recorded as the author of review-state transitions and comments. |
| `COST_CEILING_USD` | `5.00` | The CUMULATIVE authorized spend ceiling, in one place, passed to the durable journal and shown before any run. |
| `MAX_CONCURRENT_INVOCATIONS` | `1` | Billable invocations in flight at once. One by default: five expensive filings launched together multiply the worst case fivefold against the same ceiling. |
| `ALLOW_SEC_FETCH` | `true` | When `false`, the assembler is given a fetcher that REFUSES with the missing member named rather than skipping it. A silent skip would produce an incomplete source set that looked complete. |

Read from the same environment by `Settings.from_env`, outside `ReviewSettings` but load-bearing
for any review run:

| Variable | Default | What it does |
|---|---|---|
| `SEC_USER_AGENT` | unset, and required | Declared identity with a contact address. Validated at start-up because SEC answers a library-default User-Agent with a 403. |
| `STORAGE_ROOT` | `./var/objects` | The object store holding preserved filing bytes. |
| `LLM_PROVIDER` | `mock` | Which provider to invoke. See below; there is no fallback in either direction. |
| `AWS_REGION` | unset | Required by any provider other than the mock. No default, because a default is how a guessed region survives review. |

### Loopback is the default and binding beyond it is a deliberate act

The review UI reads preserved SEC filings, shows run evidence, and has a button that spends money
against a real AWS account. On loopback that is a single-user developer tool; on a LAN it is an
unauthenticated remote control for someone else's bill.

`ReviewSettings.__post_init__` refuses to construct a non-loopback configuration without
`REVIEW_DEV_SECRET`, so the unsafe combination cannot be reached by forgetting a flag. Beyond
loopback the application additionally enforces server-side sessions keyed by an opaque random
cookie, a CSRF token bound to the session on every state-changing request, no CORS headers at all,
and no AWS-shaped value in any response. It is still plain HTTP: prefer loopback plus an SSH
tunnel, which is what the start-up warning says.

### Reaching a real model is an explicit choice

DEFAULT: `LLM_PROVIDER=mock`, an in-process mock that needs no credentials, no network and no
region. A mock-configured instance never imports the adapter module and never needs the AWS SDK
installed at all.

Reaching a real model takes four things, and the fourth is deliberately not something set here:

```bash
pip install -e '.[aws]'
export LLM_PROVIDER=bedrock
export AWS_REGION=<a region the selected model was verified in>
```

The fourth is temporary credentials resolved and refreshed by the AWS SDK's own default provider
chain — a federated login on a workstation, a task role on a workload, an OIDC-assumed role in CI.

**No credential ever reaches this repository's code.** `packages/llm_gateway/providers/bedrock.py`
constructs its client with a region and nothing else. It does not accept an access key, a secret
key, a session token or a credential file path, does not read one from the environment itself, does
not cache one, and never writes one into an invocation record — `rules.md` section 3,
AWS-IDENTITY-AND-SECRETS-INVARIANT, and `docs/security/aws-identity-and-secrets.md`.

`boto3` is an OPTIONAL extra, so ordinary CI does not install it and "AWS-free CI" means the SDK is
absent rather than merely unused. There is no fallback in either direction: an unknown provider name
raises, and a misconfigured real provider fails at start-up rather than quietly running against the
mock and producing evidence of nothing.

Which region a run actually uses is DERIVED from the reviewed capability snapshot by
`packages/model_catalog/routing.py`. `AWS_REGION` is the preference; a route that has to cross
regions is DISCLOSED in the run, never silent.

### The cost ceiling is cumulative and survives the process

`packages/orchestrator/spend_journal.py` appends every reservation and every settlement to
`spend-journal.yaml` under `EVALUATION_ROOT` and recomputes the running total from that journal at
construction. The in-memory ledger in `packages/model_catalog` bounds one invocation; a ceiling that
restarted at zero with the server would be a per-process suggestion rather than a ceiling.

```
RESERVE BEFORE   the worst case at the job's estimated input tokens and configured output
                 ceiling is charged before the call is made
SETTLE AFTER     a settlement records both the reservation it replaces and the measured cost,
                 so the arithmetic is auditable rather than merely stated
FAILURES COUNT   a billable request that failed still cost money; charging only successes
                 would let a run of rejections walk past the ceiling
REFUSAL          an invocation whose bound would exceed the CUMULATIVE ceiling is refused
                 outright. Nothing is shrunk, dropped, truncated or downgraded to fit.
```

No cost per filing is known. The price INPUTS in the capability snapshot are verified; the token
counts they multiply are not, and the first measurement is pending.

### What a restart does, and what it deliberately does not

`EvaluationStore.mark_interrupted_jobs()` runs once at start-up. Every child job still in a
mid-flight execution state — `CREATED`, `SOURCE_READY`, `PREFLIGHT`, `QUEUED`, `RUNNING`,
`RESPONSE_RECEIVED`, `VALIDATING` — is moved to `INTERRUPTED`, given a failure message saying so,
and left there.

**NOTHING IS RE-INVOKED.** A job that was `RUNNING` when the process died may or may not have been
billed, and the only honest thing to do is say so and wait for a person. A rerun is billable and is
only ever started by an explicit user action; a process that merely came back up is not a user who
asked to spend money again. The background worker holds no state a restart would need — every
transition is written by the store before the next one begins.

### Where the evidence lives, and how to read it by hand

`EVALUATION_ROOT` (`./var/evaluation-runs` by default) is GITIGNORED HOST STATE. `var/` is ignored
wholesale, so nothing here is ever committed, and nothing here is backed up by Git.

**It is not the product database, and its existence is not permission to design one.** It holds no
schema, no ORM, no migration, no index, no query language and no Redis — a run directory, a job
directory, some exact bytes and two small manifests. The authoritative persistent store is designed
from measured artifacts in a later phase, not ahead of them.

Every write goes through `packages/storage`, which writes to a temporary path, flushes, fsyncs and
renames, so a reader never sees a half-written record. One object per event, because an append to a
shared log is not atomic across a crash and a torn last line is indistinguishable from an event that
never happened.

Keys map directly to paths, so the whole store is readable with `ls` and `cat`:

```
var/evaluation-runs/
  spend-journal.yaml                  cumulative ceiling, running total, every entry
  runs/<run_id>/
    run.yaml                          the parent run: issuer, selected roles, model labels
    events/00000001.txt               one append-only event per file, tab separated,
    events/00000002.txt               numbered in order; this is what the UI streams
    comments/<comment_id>.yaml        developer comments; data, never sent to a model
    jobs/<job_id>/
      job.yaml                        one filing: execution state, review state and its
                                      full append-only history, costs, source manifest
      evidence/
        source-set.yaml               assembled members, dispositions, hashes
        source-01.txt                 the EXACT bytes that were sent, preserved with the
        source-02.txt                 run rather than referenced by corpus path
        prompt.txt                    the hash-locked prompt version used
        request-instruction.txt       the compiled model-visible request content
        request-transport.json        the provider transport envelope, host state only
        response-visible.txt          the model's visible answer text
        response-reasoning.txt        reasoning content, kept separate from the answer
        response-transport.json       the provider response envelope, host state only
        validation.yaml               coverage, source-reference and numeric signals
```

Source members are numbered in the order they were sent, `.txt` for text and `.bin` for an image,
and `source-set.yaml` maps each filed document to its evidence name. The execution and review state
machines are independent by design: `job.yaml` carries both, and an artifact stays an EVALUATION
artifact until a person moves it. `ValidationStatus` has no `COMPLETE` member, deliberately —
nothing in this tree can assert a clean parse on the model's own say-so.

## Observability

### Logs

IMPLEMENTED (Sprint 1). Structured key-value records with a correlation identifier bound per unit
of work.

SECURITY-INVARIANT: filing text and model payload bodies are never logged. The formatter redacts
a fixed field set (`content`, `payload`, `request_body`, `response_body`, `text`, `prompt`,
`api_key`, `secret`, `authorization_token`, `access_token`, `password`). Payloads live in object
storage and are referenced by URI and hash.

A run's visible parent run identifier and each child filing job identifier are logged alongside the
correlation identifier, so an operator can join what the dashboard displays to what the logs
recorded.

IMPLEMENTED (Phase 2), same invariant, second instance: the review server SILENCES the standard
library's stderr access log rather than letting it run alongside. That log prints the full request
line, which carries the query string, which carries entity identifiers and search terms.
`packages/observability` is the single home for structured logging with centralized redaction, and
an unredacted second log is exactly what that rule exists to prevent. The append-only run event log
under `EVALUATION_ROOT` is progress evidence for one run, not a metrics system and not a substitute
for either.

### Metrics

Surviving subjects — transport, storage and model invocation:

```
SEC             request count by host and status, throttle events, cooldown entries,
                bytes transferred, limiter wait time
Storage         objects written, bytes stored, hash mismatches, re-acquisition avoided
                (source already held, so EDGAR was not called)
Acquisition     filings discovered, acquired, failed; retry rate
Model           tokens in and out, cost, latency, retries, batch expiry,
                boundary rejections by violation type and origin
Runs            parent runs started, child filing jobs by terminal state,
                evaluation artifacts produced, approved, rejected
Deep Analysis   sessions created, turns, scope rejections, budget exhaustions,
                citation validation failures
```

WITHDRAWN 2026-08-03, subject deleted: `Footnotes` (expected, extracted, orphaned, grouping-method
distribution, review backlog), `Serving` (query latency, cache hit rate, publication lag, dataset
version age), and the DERA half of ingest. `Summaries` is DEFERRED rather than withdrawn — the
summary role survives as an optional model role, and its metrics are defined when a summary artifact
first exists.

Coverage, citation and numeric validation are proved against the preserved source bytes. There is
no second parse to compare against and no metric here counts one.

### Traces

One trace per parent run, one span per child filing job, and one per Deep Analysis turn, with the
correlation identifier propagated into the model invocation record.

### SLOs

Surviving:

```
Dashboard read of a stored artifact   p95 under 500 ms, invoking no model
Deep Analysis first token             p95 under 8 s
Deep Analysis full response           p95 under 45 s
```

WITHDRAWN 2026-08-03: the chart-series latency target, the publication-lag target and
`Footnote coverage on processed — 100 percent`. The first two belonged to the deleted serving
layer. The third is superseded in kind, not relaxed: the invariant is that every human-readable
source range is represented in the accepted parsed artifact or explicitly marked unresolved, proved
against preserved bytes, and a filing that cannot prove it is `PARTIAL` or `REVIEW_REQUIRED` rather
than an SLO miss. A coverage SLO is defined once parse acceptance is measured.

### Alerts

Page: undeclared-automation 403; any boundary rejection outside development; a completed parse
marked complete whose coverage proof did not run.

Ticket: SEC cooldown more than once per hour; object-store hash mismatch; per-user quota
exhaustion spike; batch expiry above threshold; approval backlog of evaluation artifacts above
threshold.

WITHDRAWN 2026-08-03: dataset publication failure, footnote coverage below 100 percent, and the
DERA package-missing watch.

## Scheduling

Surviving jobs:

| Job | Cadence | Priority | Status |
|---|---|---|---|
| Issuer universe snapshot | daily | 1 | PLANNED |
| Filing discovery, incremental | hourly | 2 | PLANNED |
| Amendment discovery | daily | 3 | PLANNED |
| Historical backfill | continuous, lowest | 6 | PLANNED |

Queue priority, highest first: a user-requested issuer; newly filed reports; popular issuers;
recent history; historical backfill.

WITHDRAWN 2026-08-03, subject deleted: the DERA mirror check, the DERA load on arrival, the
freshness patch and dataset publication. DEFERRED: any parsing, summarization or reprocessing
schedule. Parsing is user-initiated from the dashboard for the beta — a parent run over one issuer
and timeframe — and a background parsing schedule is not designed until parse acceptance exists.

## Idempotency

Every job carries an idempotency key. A killed and resumed job produces no duplicates and no gaps.
Surviving keys:

```
filing_discovery      discovery:{cik}:{source}:{watermark}
filing_download       acquire:{accession}:{strategy}
deep_analysis_turn    turn:{session_id}:{turn_number}
```

A key collision means the work is already done or in flight, so the job returns the existing result
rather than repeating it. Raw source acquisition checks the object store before EDGAR, so a
re-requested filing costs no SEC request at all.

WITHDRAWN 2026-08-03: `dataset_download`, `xbrl_load`, `block_extraction`, `canonical_grouping`,
`metric_calculation`, `dataset_publication` and `embedding` — every one of them keyed on a deleted
subsystem. DEFERRED: the parse and summary keys. Both were keyed on a deterministic
`parser_version` and a footnote identifier; a model-first key has to name the model, the prompt
version, the input mode and the source hash, and it is written when the model contract is measured
rather than guessed now.

## Artifact lifecycle

A parsed artifact is an EVALUATION artifact until it is explicitly APPROVED. Only approved artifacts
become reusable. The operational consequences are stated here and implemented nowhere yet:

> **UPDATED 2026-08-03 BY PHASE 2.** "Implemented nowhere yet" was true when written and is now
> true only of the last two bullets. The review state machine — `EVALUATION`, `UNDER_REVIEW`,
> `APPROVED`, `REJECTED`, `SUPERSEDED`, `INVALIDATED` — is IMPLEMENTED in
> `packages/evaluation_store`, runs independently of the execution state machine, and records each
> transition with its timestamp, the configured author and an optional note in an append-only
> history that is never rewritten. Comments are stored per run and per child job. Redis and the
> authoritative persistent store are still DEFERRED, so no artifact is served, cached or reused
> anywhere: an approval is a recorded decision and nothing more.

- An evaluation artifact is never served as an accepted parse and never satisfies a cache read.
- Approval and rejection are recorded with the parent run identifier, the approver and the
  developer comments attached at the point of decision.
- Approved artifacts are cached in Redis with a **24-hour TTL** over an authoritative persistent
  store. The cache is a latency device: a miss re-reads the store, and an expiry never invokes a
  model. No Redis instance is configured.
- The authoritative store is DEFERRED. The previous one was deleted with the schema it described,
  and its replacement is designed from accepted artifacts rather than ahead of them.
