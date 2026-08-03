# LLM Cost Model

> **RE-FOUNDED 2026-08-02 ON MEASURED EVIDENCE.** A representative corpus of **112 SEC issuers and
> 613 filings across six transport eras** was acquired and measured — dated Phase 1 evidence, not a
> permanent constant — and it refuted the assumptions the deterministic semantic parser rested on.
> The product is an orchestrator-driven, model-first SEC filing product: the backend acquires,
> preserves, transports, orchestrates and VALIDATES; a user-selected parsing model determines what
> a filing means. The user selects four models independently — parsing, image, summary, and
> analysis/chat. The current authorized input mode is `INTACT_SOURCE_ONLY`. The deterministic
> content ontology, migration `0003` and the local application database are withdrawn. Sections
> below that describe the withdrawn design are historical.
>
> **NO MODEL HAS BEEN INVOKED AND AWS IS NOT CONFIGURED.** Authoritative:
> `docs/adr/ADR-0016-corpus-first-model-first-architecture.md` and `roadmap.md`.

---

# CURRENT DIRECTION — AUTHORITATIVE. Everything below this section is historical.

**NO MODEL HAS BEEN INVOKED. NO PRICE IS KNOWN. EVERY PARAMETER IN THIS DOCUMENT IS A PLACEHOLDER.**

No model price, context limit, or throughput figure in this repository has been verified against a
provider. Prices are discovered live in Phase 1.5 and the first real cost measurement is Phase 2.
Until then, no cost claim may be presented as known.

## Cost is modelled per ROLE, not per footnote

The four roles are priced and metered separately, because they use different models, run at
different times, and are regenerated independently.

```
PARSING          one invocation per filing per accepted parse. The dominant input cost:
                 the complete relevant human-readable source set, sent intact.
IMAGE            only when the parsing model is text-only. Zero when it is multimodal.
SUMMARY          per summary artifact. REGENERATION DOES NOT REQUIRE REPARSING while the
                 accepted parse is unchanged, so a resummarize costs summary tokens only.
ANALYSIS/CHAT    per turn, metered against turn, token and session budgets.
```

**NO FOOTNOTE-COUNT EXTRAPOLATION.** Estimating a complete filing's cost by multiplying a
per-footnote figure is prohibited. It was the model this repository used while it believed
footnotes were the product, and it understates a complete filing by an unknown and variable factor.
Complete-filing cost is estimated from the measured source set, and confirmed by measurement.

## Token figures are estimates until a provider says otherwise

Every token number produced before Phase 2 comes from a character ratio — the planning ratio is 3.0
characters per token — and must be labelled an ESTIMATE wherever it appears. It is not a provider
tokenizer count and must never be presented as one.

## Cost authorization

No billable invocation happens without an explicit authorization carrying a ceiling, and the
ceiling is checked **before** the call. Cost is previewed, authorized, then spent — never
reconciled afterwards.

An incompatible filing/model pairing costs nothing, because it is refused before invocation.


IMPLEMENTATION STATUS: PLANNED (measured in Sprint 5, which is an explicit go/no-go on unit economics)
DECISION RECORD: `docs/adr/ADR-0006-model-selection-by-benchmark.md`

## Why the previous estimate was withdrawn — twice

An earlier version of this architecture quoted roughly 8,500 US dollars for a full-corpus
summarization backfill. That figure was computed on the wrong unit of work: it assumed 58
summarization jobs for Apple's FY2025 10-K, where the correct footnote count is 13 (ADR-0005). The
unit was wrong by a factor of about 4.5, so the figure was withdrawn.

**It was then withdrawn a second time, in the other direction.** ADR-0016 corrected the product
scope from footnote-only to complete filing coverage. The summarized surface of that same 10-K is
not 13 units but **67 required summary units** — measured, not estimated — of which 13 are
footnotes. Any total extrapolated from footnote counts understates the real figure by roughly a
factor of five, for exactly the reason the first estimate overstated it: the wrong unit of work.

This document supplies the formulas. It does not supply a total, because the parameters that
matter have not been measured yet and a number produced without them would repeat the same mistake
a third time.

## Parameters

Symbols marked MEASURED are known. Symbols marked PLACEHOLDER must be measured before any cost
commitment. A placeholder is written as a named symbol, never as an invented number.

| Symbol | Meaning | Status |
|---|---|---|
| `F` | Filings in the covered corpus | ESTIMATE 171,000, interval 86,000 to 257,000, n=15 |
| `U_10K` | **Required summary units per 10-K** | MEASURED 67 on one filing; distribution PLACEHOLDER |
| `U_10Q` | **Required summary units per 10-Q** | MEASURED 41, 41, 41 on three filings; distribution PLACEHOLDER |
| `N_10K` | Canonical footnotes per 10-K | MEASURED 13 on one filing; distribution PLACEHOLDER |
| `N_10Q` | Canonical footnotes per 10-Q | MEASURED 10 on three filings; distribution PLACEHOLDER |
| `B_10K` | Human-readable source blocks per 10-K | MEASURED 983 on one filing |
| `B_10Q` | Human-readable source blocks per 10-Q | MEASURED 544, 341, 324 |
| `C_unit` | Leaf chunks per oversized unit | PLACEHOLDER |
| `T_src` | Source tokens per content unit | PLACEHOLDER |
| `T_tbl` | Table tokens per content unit | PLACEHOLDER |
| `T_sys` | System prompt tokens | MEASURABLE now, roughly 900 |
| `T_out` | Output tokens per summary | PLACEHOLDER, target 150 to 800 by complexity |
| `T_agg` | Output tokens per aggregate summary | PLACEHOLDER |
| `R_retry` | Retry rate on validation failure | PLACEHOLDER |
| `R_repair` | Repair-call rate | PLACEHOLDER |
| `P_in` | Input price per million tokens | PLACEHOLDER, provider catalog unverified |
| `P_out` | Output price per million tokens | PLACEHOLDER |
| `D_batch` | Batch discount | PLACEHOLDER |
| `D_flex` | Flex discount | PLACEHOLDER |

The block and unit counts above are the Sprint 4.1 backfill measurements and are recorded in
`docs/sprints/SPRINT-0004A.md`. They are the denominators the cost model was previously missing.

## Formulas

Input tokens for one content unit, or one leaf chunk of one:

```
T_in(unit) = T_sys + T_src + T_tbl + T_overhead_yaml
```

Cost for one unit, single attempt:

```
C_unit = (T_in / 1e6) * P_in * (1 - D_batch)
       + (T_out / 1e6) * P_out * (1 - D_batch)
```

Cost including retries and repairs:

```
C_effective = C_unit * (1 + R_retry + R_repair)
```

Cost for one **oversized** unit, which is chunked then aggregated:

```
C_oversized = C_units(leaf chunks) + C_aggregate
            = C_unit_chunk * C_unit_count * (1 + R_retry + R_repair)
            + ((T_sys + sum of accepted child summaries) / 1e6 * P_in + T_agg / 1e6 * P_out)
```

The aggregate is a second invocation, not free. A cost model that counted only the leaf chunks
would understate every large Item.

Cost for one filing — **over required units, not over footnotes**:

```
C_filing = sum over required units of C_effective(unit)
         ~ U_filing * C_effective
```

Corpus backfill:

```
C_backfill = sum over filings of C_filing
           ~ F * E[U_filing] * C_effective
```

```
DO NOT EXTRAPOLATE FILING COST FROM FOOTNOTE COUNTS.

E[U_filing] is the required-summary-unit count, not the footnote count. On the one filing where
both are measured they differ by a factor of about five. Using N where U belongs reproduces the
withdrawn estimate's defect with a different sign.
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

## Cost accounting levels

Measured and published at every level, because a single per-filing number hides which content type
is expensive:

```
per source character            per serialized byte
per input token                 per output token
per leaf chunk                  per canonical content unit
per footnote                    per Part
per Item                        per filing
per incorporated referenced document
per issuer history
```

And separated by **kind of spend**, because these have different growth curves and different
optimizations:

| Kind | What drives it |
|---|---|
| Extraction | Deterministic; no model cost at all. Recorded to show it is zero |
| Initial summarization | Required units × tokens per unit |
| Aggregate summarization | Parts, Items, and the filing root; grows with hierarchy depth |
| Validation retry | `R_retry`, `R_repair` |
| Deep Analysis | Sessions × turns; unrelated to backfill |
| Reprocessing | Prompt version, model change, or parser change altering source text |

## Required scenarios

Once parameters are measured, publish: one typical 10-Q, one large 10-K, one issuer's full
history, the top 100 issuers, the top 500 issuers, the full covered universe, monthly steady
state, one Deep Analysis session, and one follow-up turn. Each with a sensitivity analysis over
`T_src`, `T_out`, `C_unit` and `R_retry`, which are the parameters the total is most sensitive to.

**The go/no-go rests on complete filing processing**, not on the footnote subset. A unit economics
verdict computed over 13 of 67 units would approve a program five times more expensive than the
one it measured.

## Spend is bounded by identity, not only by code

A budget enforced only in application code is a budget a bug can exceed. The IAM identity used for
any real-model run is scoped to an explicit model allowlist and region, so a runaway loop is
refused by AWS rather than merely counted by Kopexx. See
`docs/security/aws-identity-and-secrets.md`.

## Non-negotiable

Cost optimization must not reduce **filing coverage**, footnote coverage, or financial fidelity.
Neither the complete-filing-coverage requirement nor the every-footnote requirement is a cost
variable.

If the measured economics are unaffordable, the response is a decision about which issuers or
which periods to process — never a decision to summarize part of a filing and call it complete.
