# Operations

IMPLEMENTATION STATUS: PLANNED (Phase 7 onward); structured logging IMPLEMENTED (Sprint 1)

## Observability

### Logs

Structured key-value records with a correlation identifier bound per unit of work.

SECURITY-INVARIANT: filing text and model payload bodies are never logged. The formatter redacts
a fixed field set (`content`, `payload`, `request_body`, `response_body`, `text`, `prompt`,
`api_key`, `secret`, `authorization_token`, `access_token`, `password`). Payloads live in object
storage and are referenced by URI and hash.

### Metrics

```
SEC             request count by host and status, throttle events, cooldown entries,
                bytes transferred, limiter wait time
Ingest          filings discovered, acquired, parsed, failed; queue depth; retry rate
Footnotes       per filing: expected, extracted, orphaned; grouping method distribution;
                confidence distribution; review backlog
Summaries       created, accepted, failed, requiring review; per-filing coverage ratio
Model           tokens in and out, cost, latency, retries, batch expiry,
                boundary rejections by violation type and origin
Serving         query latency, cache hit rate, publication lag, dataset version age
Deep Analysis   sessions created, turns, scope rejections, budget exhaustions,
                citation validation failures
```

### Traces

One trace per filing through the pipeline, and one per Deep Analysis turn, with the correlation
identifier propagated into the model invocation record.

### SLOs

```
Dashboard ticker query          p95 under 500 ms
Chart series query              p95 under 800 ms
Deep Analysis first token       p95 under 8 s
Deep Analysis full response     p95 under 45 s
Publication lag after ingest    under 24 h
Footnote coverage on processed  100 percent, alert on any deviation
```

### Alerts

Page: undeclared-automation 403; dataset publication failure; footnote coverage below 100 percent
on a filing marked complete; any boundary rejection outside development.

Ticket: SEC cooldown more than once per hour; DERA package missing past its expected window; review
backlog above threshold; batch expiry above threshold; per-user quota exhaustion spike.

## Scheduling

| Job | Cadence | Priority |
|---|---|---|
| Issuer universe snapshot | daily | 1 |
| Filing discovery, incremental | hourly | 2 |
| Amendment discovery | daily | 3 |
| DERA mirror check | daily | 1 |
| DERA load on new package | on arrival | 2 |
| Freshness patch for new filings | hourly | 2 |
| Summarization batch | nightly | 3 |
| Dataset publication | after load | 2 |
| Model or prompt reprocessing | on demand | 5 |
| Historical backfill | continuous, lowest | 6 |

Queue priority, highest first: a user-requested missing ticker; newly filed reports; popular
issuers; recent history; historical backfill; reprocessing.

## Idempotency

Every job carries an idempotency key. A killed and resumed job produces no duplicates and no gaps.

```
dataset_download      dera:{filename}:{sha256}
filing_discovery      discovery:{cik}:{source}:{watermark}
filing_download       acquire:{accession}:{strategy}
filing_parse          parse:{accession}:{parser_version}:{source_sha256}
xbrl_load             facts:{accession}:{source_dataset}
block_extraction      blocks:{accession}:{parser_version}
canonical_grouping    group:{accession}:{grouping_version}
footnote_summary      summary:{accession}:{footnote_id}:{source_sha256}:{prompt_version}:{model_id}
numeric_validation    validate:{summary_id}
metric_calculation    metric:{cik}:{metric_id}:{period}:{formula_version}
embedding             embed:{source_id}:{embedding_model}
dataset_publication   publish:{dataset_version}
deep_analysis_turn    turn:{session_id}:{turn_number}
```

A key collision means the work is already done or in flight, so the job returns the existing
result rather than repeating it. Note the summary key includes the source hash, the prompt
version, and the model, so a prompt change produces new work while a re-run does not.
