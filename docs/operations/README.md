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
> been sent to any model, and no provider adapter exists.** Every threshold below that is not marked
> IMPLEMENTED is a target, not a measurement. The verified capability evidence is
> `docs/llm/bedrock-capability-snapshot.yaml`; the procedure that produced it is
> `docs/runbooks/bedrock-capability-discovery.md`.

IMPLEMENTATION STATUS: PLANNED; structured logging IMPLEMENTED (Sprint 1)

The scheduling, idempotency, metric and alert sets for parsing, summarization and persistence are
DEFERRED. They are redesigned from real model responses and accepted artifacts once Phase 2 has
produced any, rather than inherited from a pipeline that no longer exists.

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

- An evaluation artifact is never served as an accepted parse and never satisfies a cache read.
- Approval and rejection are recorded with the parent run identifier, the approver and the
  developer comments attached at the point of decision.
- Approved artifacts are cached in Redis with a **24-hour TTL** over an authoritative persistent
  store. The cache is a latency device: a miss re-reads the store, and an expiry never invokes a
  model. No Redis instance is configured.
- The authoritative store is DEFERRED. The previous one was deleted with the schema it described,
  and its replacement is designed from accepted artifacts rather than ahead of them.
