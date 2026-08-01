# LLM Cost Model

IMPLEMENTATION STATUS: PLANNED (measured in Sprint 5, which is an explicit go/no-go on unit economics)
DECISION RECORD: `docs/adr/ADR-0006-model-selection-by-benchmark.md`

## Why the previous estimate was withdrawn

An earlier version of this architecture quoted roughly 8,500 US dollars for a full-corpus
summarization backfill. That figure was computed on the wrong unit of work: it assumed 58
summarization jobs for Apple's FY2025 10-K, where the correct number is 13 (ADR-0005). The unit
was wrong by a factor of about 4.5, so the figure is not usable and is not carried forward.

This document supplies the formulas. It does not supply a total, because the parameters that
matter have not been measured yet and a number produced without them would repeat the same
mistake in a different direction.

## Parameters

Symbols marked MEASURED are known. Symbols marked PLACEHOLDER must be measured before any cost
commitment. A placeholder is written as a named symbol, never as an invented number.

| Symbol | Meaning | Status |
|---|---|---|
| `F` | Filings in the covered corpus | ESTIMATE 171,000, interval 86,000 to 257,000, n=15 |
| `N_10K` | Canonical footnotes per 10-K | MEASURED 13 on one filing; distribution PLACEHOLDER |
| `N_10Q` | Canonical footnotes per 10-Q | PLACEHOLDER |
| `T_src` | Source tokens per canonical footnote | PLACEHOLDER |
| `T_tbl` | Table tokens per canonical footnote | PLACEHOLDER |
| `T_sys` | System prompt tokens | MEASURABLE now, roughly 900 |
| `T_out` | Output tokens per summary | PLACEHOLDER, target 150 to 800 by complexity |
| `R_retry` | Retry rate on validation failure | PLACEHOLDER |
| `R_repair` | Repair-call rate | PLACEHOLDER |
| `P_in` | Input price per million tokens | PLACEHOLDER, provider catalog unverified |
| `P_out` | Output price per million tokens | PLACEHOLDER |
| `D_batch` | Batch discount | PLACEHOLDER |
| `D_flex` | Flex discount | PLACEHOLDER |

## Formulas

Input tokens for one footnote:

```
T_in(footnote) = T_sys + T_src + T_tbl + T_overhead_yaml
```

Cost for one footnote, single attempt:

```
C_footnote = (T_in / 1e6) * P_in * (1 - D_batch)
           + (T_out / 1e6) * P_out * (1 - D_batch)
```

Cost including retries and repairs:

```
C_effective = C_footnote * (1 + R_retry + R_repair)
```

Cost for one filing:

```
C_filing = N_footnotes(filing) * C_effective
```

Corpus backfill:

```
C_backfill = sum over filings of C_filing
           ~ F * E[N_footnotes] * C_effective
```

Monthly steady state:

```
C_monthly = new_filings_per_month * E[N_footnotes] * C_effective
```

Deep Analysis, per session:

```
C_session = sum over turns of
              ((T_sys + T_scope + T_memory + T_evidence + T_question) / 1e6 * P_in
               + T_answer / 1e6 * P_out)
```

A follow-up turn is cheaper than the first because scope and memory are already compact and only
incremental evidence is retrieved.

## Prompt caching does not rescue the backfill

Caching is a prefix match. Every one of roughly 170,000 filings is a different document, so only
the system prompt is shared. The cacheable prefix is on the order of one percent of a typical
request. **Cache savings are not modelled into the backfill budget.** Caching pays on multi-pass
work over the same filing, which is Deep Analysis, not summarization.

## Batch packing

The binding constraint on a batch is usually the total payload size, not the request count. Batches
are packed **by measured bytes** with headroom, not by counting requests. Batch requests expire,
and expiry is silent, so a watchdog re-queues expired requests rather than leaving a hole that
looks like completion.

## Serialization savings

Recorded per benchmark fixture by the harness in `packages/llm_gateway/token_counter.py`:

```
serialization_comparison:
  plain_text_tokens: 0
  yaml_tokens: 0
  markdown_tokens: 0
  json_tokens: 0
  xml_tokens: 0
  selected_format: yaml
  selected_tokens: 0
```

Savings are computed from measurement, not from an assumed percentage. Sources of saving: keys are
not repeated per record as they are in JSON; prose is not escaped; tag names are not repeated as
they are in XML; raw HTML and XBRL never reach the model at all, which is the largest single
saving and the one that would be invisible if only JSON and YAML were compared.

The production path selects plain text or YAML regardless of the measurement, because the boundary
is a correctness and security constraint. The measurement exists to quantify the benefit and to
detect regression.

## Required scenarios

Once parameters are measured, publish: one typical 10-Q, one large 10-K, one issuer's full
history, the top 100 issuers, the top 500 issuers, the full covered universe, monthly steady
state, one Deep Analysis session, and one follow-up turn. Each with a sensitivity analysis over
`T_src`, `T_out`, and `R_retry`, which are the parameters the total is most sensitive to.

## Non-negotiable

Cost optimization must not reduce footnote coverage or financial fidelity. The every-footnote
requirement is not a cost variable.
