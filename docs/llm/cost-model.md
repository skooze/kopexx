# LLM Cost Model

> **UPDATED 2026-08-03 BY PHASE 1. THE PRICE INPUTS ARE NOW REAL; EVERY COST FIGURE STILL IS NOT.**
>
> Official published input and output prices for all five approved candidates were read from the AWS
> Price List API, standard on-demand tier, effective 2026-07-01, and are recorded in
> `bedrock-capability-snapshot.yaml`. They are NOT repeated here, because a price copied into prose
> goes stale silently.
>
> **That changes one half of the arithmetic and not the other.** A cost is a price multiplied by a
> token count, and no filing has ever been sent to a model, so every token parameter below —
> `T_src`, `T_tbl`, `T_out`, `R_retry` — remains a placeholder and every derived figure remains
> unmeasured. The first real cost per filing is Phase 2.
>
> Total model spend by this project to date: **USD 0.00023**, seven one-word invocations under an
> authorized USD 1.00 ceiling. `packages/model_catalog.SpendLedger` is the enforcement, and it
> bounds the worst case BEFORE the call rather than reconciling after it.


> **RE-FOUNDED 2026-08-02 ON MEASURED EVIDENCE.** A representative corpus of **112 SEC issuers and
> 613 filings across six transport eras** was acquired and measured — dated Phase 0 evidence, not a
> permanent constant — and it refuted the assumptions the deterministic semantic parser rested on.
> The product is an orchestrator-driven, model-first SEC filing product: the backend acquires,
> preserves, transports, orchestrates and VALIDATES; a user-selected parsing model determines what
> a filing means. The user selects four models independently — parsing, image, summary, and
> analysis/chat — and **only the parsing model is required**, so a run may cost nothing beyond one
> parse. The current authorized input mode is `INTACT_SOURCE_ONLY`.
>
> **UPDATED 2026-08-03.** The deterministic content ontology and the local application database are
> no longer merely withdrawn — the parser, the persistence layer and the migrations are DELETED.
> **Every per-unit denominator this document once carried as MEASURED came from that parser**, on
> one issuer, and is withdrawn with it.
>
> **NO MODEL HAS BEEN INVOKED AND AWS IS NOT CONFIGURED.** Authoritative:
> `docs/adr/ADR-0016-corpus-first-model-first-architecture.md`,
> `docs/adr/ADR-0017-delete-the-rejected-parser-and-application-persistence.md` and `roadmap.md`.
>
> **SUPERSEDED 2026-08-03 BY PHASE 2, ADDITIVELY.** The statement above was true when it was
> written and is kept for that reason (`rules.md` section 21 rule 16). It is no longer true:
> AWS IS configured, a real Bedrock adapter EXISTS in `packages/llm_gateway/providers/bedrock.py`,
> and SEC filings HAVE been sent to real models — three preserved filings across five candidates
> under two prompt versions. See `docs/sprints/PHASE-0002-parser-experiments-and-review-ui.md`.
>
> **WHAT IS STILL TRUE.** No application database exists. No Redis exists. No summary artifact, no
> image artifact and no chat session exists — Phase 2 ran the PARSING stage only, and the
> orchestrator raises rather than running another. Nothing is deployed.

---

# CURRENT DIRECTION — AUTHORITATIVE

> **SUPERSEDED 2026-08-04, ADDITIVELY. THE THREE CLAIMS IMMEDIATELY BELOW ARE FALSE AND ARE KEPT
> UNEDITED**, because `rules.md` section 21 rule 16 forbids rewriting a past claim. They were true
> when written, before Phase 1.
>
> **THE DEFECT THIS NOTE EXISTS TO PREVENT IS A STALE BANNER OUTRANKING A CORRECT SECTION.** The
> sentence below sat under a heading reading AUTHORITATIVE through two phases that falsified it,
> while the measured figures lived eighty lines further down. A reader stops at the first sentence
> that claims authority, so a correction placed anywhere else is a correction nobody reaches.
>
> ```
> "NO MODEL HAS BEEN INVOKED"        falsified by Phase 1     7 one-word calls,   USD 0.00023
>                                    falsified by Phase 2     30 invocations,     USD 0.40711113
>                                    falsified by Phase 2.1   7 multipart runs,   USD 2.603827
> "NO PRICE IS KNOWN"                falsified by Phase 1, and re-verified by Phase 2.2 on
>                                    2026-08-04: all ten committed prices match the live Price
>                                    List API to the digit
> "EVERY PARAMETER IS A PLACEHOLDER" half true, and the half that stands is the important one. The
>                                    PRICE inputs are measured. The TOKEN parameters in the table
>                                    below are still placeholders, and each row says so
> ```
>
> **WHAT SURVIVES FROM IT AND IS STILL TRUE.** No corpus-scale total exists. Cost has been measured
> on three filings, three filings is not a denominator, and no figure in this document may be
> multiplied up to 613 filings or to 171,000.

RETAINED AS WRITTEN, 2026-08-03:

**NO MODEL HAS BEEN INVOKED. NO PRICE IS KNOWN. EVERY PARAMETER IN THIS DOCUMENT IS A PLACEHOLDER.**

No model price, context limit, or throughput figure in this repository has been verified against a
provider. Prices are discovered live in Phase 1 and the first real cost measurement is Phase 2.
Until then, no cost claim may be presented as known.

**This document supplies symbols and formulas. It supplies no total, and it contains no measured
figure of any kind.** The sections below the parameter table are working material, corrected
2026-08-03 for ADR-0017; the narrative of the two withdrawn estimates is retained as history and is
labelled as such where it appears.

## Cost is modelled per ROLE, not per footnote

The four roles are priced and metered separately, because they use different models, run at
different times, and are regenerated independently. **Only PARSING is required.** The other three
selectors may be left blank, and a run that leaves them blank incurs exactly zero for them — no
stage is invoked because it exists.

```
PARSING          one invocation per filing per parse attempt. The dominant input cost:
                 the complete relevant human-readable source set, sent intact.
IMAGE            only when the parsing model is text-only AND an image model is selected.
                 Zero when the parsing model is multimodal, and zero when the selector is blank.
SUMMARY          per summary artifact, when a summary model is selected. REGENERATION DOES NOT
                 REQUIRE REPARSING while the accepted parse is unchanged, so a resummarize costs
                 summary tokens only.
ANALYSIS/CHAT    per turn, metered against turn, token and session budgets, when selected.
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


IMPLEMENTATION STATUS: cost authorization, the pre-spend bound and the durable cumulative ceiling
are IMPLEMENTED. The corpus-scale extrapolation below remains PLANNED — Phase 2 measured three
filings, and three filings is not a denominator.
DECISION RECORD: `docs/adr/ADR-0006-model-selection-by-benchmark.md`

---

# WHAT PHASE 2.2 PRICED, AND THE BENCHMARK IT COULD NOT AFFORD — added 2026-08-04

**NO PROVIDER REQUEST WAS ISSUED BY THIS PHASE. MEASURED BEDROCK SPEND: `USD 0.00000000`.** Every
figure in this section is a DRY-RUN computation over verified prices and previously measured call
counts. Nothing here is a measurement of a run, because **the benchmark did not run** — it does not
fit the authorized ceiling, and running an arbitrary partial subset instead was not authorized. A
subset chosen to fit a budget measures the budget.

## Zero drift, which is what a cost model has to establish before it computes anything

Re-verified 2026-08-04, read-only, against the live AWS Price List API and the AWS model cards:

```
all ten committed prices             match the live Price List API TO THE DIGIT, effective
                                     2026-07-01
all five context and output limits   match the AWS model cards read 2026-08-04
```

The prices are still not repeated here; `bedrock-capability-snapshot.yaml` remains their single
home. What this establishes is narrow and load-bearing: the `USD 2.603827` Phase 2.1 measured was
computed against prices that are still current, so that arithmetic did not silently rot, and the
snapshot did not need replacing. **R-33 — the snapshot goes stale silently — was checked rather
than assumed for the first time.**

## The benchmark filing, and R-21 biting for the first time

Apple Inc., `AAPL`, CIK `0000320193`, form 10-Q, accession `0000320193-25-000008`, filed
2025-01-31, report period 2024-12-28, inline XBRL. 63 package members, of which 6 are
human-readable and total **915,890 characters**, plus 2 filed images. Preserved bytes: 9.9 MB.

Estimated intact input at **3.8 characters per token, an upper bound and not a tokenizer count**,
measured with the repository's own compatibility guard against the committed snapshot:

| model | context | estimated input | largest output that fits |
|---|---:|---:|---:|
| GPT OSS 120B | 128,000 | 243,507 | 0 — **INCOMPATIBLE** |
| NVIDIA Nemotron 3 Super 120B | 256,000 | 243,507 | 12,493 |
| Qwen3 235B A22B | 256,000 | 243,507 | 8,000 |
| Llama 4 Maverick | 1,000,000 | 251,507 | 8,000 |
| Qwen3 VL 235B | 256,000 | 251,507 | 4,493 |

The two multimodal rows carry 2 images charged at the **UNVERIFIED 4,000-tokens-per-image upper
bound** the pre-spend guard uses, which is why their input is 8,000 tokens higher.

**GPT OSS 120B COSTS EXACTLY ZERO ON THIS FILING, AND THAT IS THE POINT.** An incompatible pairing
is refused before invocation rather than truncated into affordability, so it never enters the
arithmetic below. This is R-21 — "no candidate model accepts a materially sized modern filing
intact" — producing a measured result for the first time. Phase 2 and Phase 2.1 could not touch it,
because by construction their shared benchmark could only contain filings that fit every candidate.

## The dry-run plan: per-call cost, at each candidate's OWN measured call count

Per-call cost is the estimated intact input at that candidate's verified price plus that
candidate's **own** measured Phase 2.1 mean output per call. No model's call count, output size or
repair rate is applied to another — the 5.6x spread in plan size across candidates on one filing is
the reason that rule exists.

| model | estimated input | USD per call | Phase 2.1 calls | USD at that count |
|---|---:|---:|---:|---:|
| GPT OSS 120B | 243,507 | — | — | INCOMPATIBLE |
| NVIDIA Nemotron 3 Super 120B | 243,507 | 0.03790 | 78 | 2.9564 |
| Qwen3 235B A22B | 243,507 | 0.05556 | 58 | 3.2228 |
| Llama 4 Maverick | 251,507 | 0.06086 | 14 | 0.8520 |
| Qwen3 VL 235B | 251,507 | 0.13496 | 47 | 6.3433 |
| **TOTAL, the four runnable candidates** | | | | **13.3745** |

Against **`USD 5.00` authorized**.

## The guardrail-bounded maximum, which is the number an authorization actually buys

Phase 2.2 added a part-explosion guardrail to `packages/orchestrator/multipart_service.py`: a soft
threshold at 64 logical parts and a hard ceiling at 100. At the hard ceiling, plus one plan, three
reconciliation cycles and six repairs, one run is 110 calls:

| model | calls | USD |
|---|---:|---:|
| NVIDIA Nemotron 3 Super 120B | 110 | 4.1693 |
| Qwen3 235B A22B | 110 | 6.1121 |
| Llama 4 Maverick | 110 | 6.6943 |
| Qwen3 VL 235B | 110 | 14.8460 |
| **TOTAL** | | **31.8218** |

**A CEILING IS NOT A FORECAST AND A FORECAST IS NOT A CEILING**, and both belong in an
authorization. `USD 13.3745` is what the measured behaviour of these four candidates predicts;
`USD 31.8218` is the most the code can spend before it refuses.

## What USD 5.00 buys, split equally across the four runnable candidates

| model | at USD 1.2500 | calls Phase 2.1 needed |
|---|---:|---:|
| NVIDIA Nemotron 3 Super 120B | 32 calls | 78 |
| Qwen3 235B A22B | 22 calls | 58 |
| Llama 4 Maverick | 20 calls | 14 |
| Qwen3 VL 235B | 9 calls | 47 |

**ONE OF FOUR WOULD FINISH.** The other three would hit the filing-run budget and PAUSE mid-parse,
which is the designed behaviour and which produces exactly the `INCOMPLETE_WORK` result the phase
exists to move past. A paused branch cannot reach the mechanical completeness gate, because that
gate requires no scheduled required job to remain nonterminal.

## Every figure above is a FLOOR

The Phase 2.2 prompts ask for more per part than the Phase 2.1 prompts did: a structured-table
contract over the filing's 18 substantive table elements, and two resolvable anchors per coverage
claim. That increases output per part AND increases the number of parts. **A hardened protocol is
more expensive than the one whose call counts these estimates borrow**, so treating the Phase 2.1
counts as a prediction understates rather than overstates.

## The cumulative ceiling binds first in any case

The durable journal stood at **`USD 3.25290926`** against `COST_CEILING_USD 5.00`, leaving roughly
`USD 1.75` before the configured repository ceiling refuses. Releasing the twelve proven unsettled
reservations recovers `USD 0.24197085`, bringing settled spend to `USD 3.01093841` and headroom to
roughly `USD 1.99`. Neither number changes the conclusion, and neither is authorization to spend.

---

# WHAT PHASE 2.1 CHANGES ABOUT COST — added 2026-08-03

**MULTIPART PARSING COSTS MORE PER FILING AND BUYS COVERAGE. THE SHAPE OF THE ARITHMETIC CHANGES,
NOT JUST THE NUMBER.**

Under the single-response protocol, one filing cost one call: one input charge for the intact
filing, one output charge for whatever came back. Under model-directed multipart, one filing costs
`1 + N + R` calls — one plan, N parts, R reconciliation and repair calls — **and every one of them
re-sends the intact filing and pays the full uncached input rate for it.**

```
single response   cost  =  price_in x T_src              +  price_out x T_out
multipart         cost  =  price_in x T_src x (1+N+R)    +  price_out x SUM(T_part)
```

**THE INPUT TERM IS THE ONE THAT GREW, AND IT GREW BY A FACTOR OF THE CALL COUNT.** There is no
prompt-caching relief: AWS documents prompt caching for Claude, GPT-5.6 and Amazon Nova, and for
none of the five approved candidates. See `prompt-caching-investigation.md`, which records the live
control-plane evidence, the documentation evidence, and what could not be verified.

## What was actually measured, and how little it is

**SEVEN RUNS, TWO FILINGS, FIVE CANDIDATES, `USD 2.603827`.** Provider-reported counts, not
estimates. Every request and response preserved.

### The five candidates on one filing — 3M CO 10-K405, `0000066740-96-000005`, 146,471 bytes

| model | calls | input tokens | output tokens | max single response | USD |
|---|---:|---:|---:|---:|---|
| GPT OSS 120B | 51 | 1,965,451 | 125,159 | 7,184 | 0.36991305 |
| NVIDIA Nemotron 3 Super 120B | 78 | 3,145,019 | 165,202 | 18,303 | 0.57913415 |
| Qwen3 235B A22B | 58 | 2,142,106 | 131,349 | 8,000 (cap) | 0.58685044 |
| Llama 4 Maverick | 14 | 520,442 | 7,153 | 909 | 0.13184449 |
| Qwen3 VL 235B | 47 | 902,097 | 29,432 | 5,754 | 0.55640053 |

### Both multimodal candidates on an image-bearing filing — Macy's 10-Q/A

| model | calls | input tokens | output tokens | USD |
|---|---:|---:|---:|---|
| Llama 4 Maverick | 16 | 330,276 | 7,628 | 0.08666540 |
| Qwen3 VL 235B | 20 | 408,042 | 28,856 | 0.29301922 |

### The shape of the arithmetic, now measured rather than predicted

**INPUT DOMINATES, AND BY HOW MUCH IS NOW A NUMBER.** For `GPT OSS 120B` on the 3M filing the input
side is `USD 0.29481765` and the output side `USD 0.07509540` — **79.7% of the spend is the intact
filing being re-sent**, 51 times, at roughly 38,538 tokens per call. Nemotron's is 81.5%.

**THE NUMBER OF CALLS IS A PROPERTY OF THE MODEL, NOT OF THE FILING.** The same 146,471 bytes
produced plans of 5, 12, 24, 27 and 28 parts, and runs of 14 to 102 tasks. A cost model that treats
"calls per filing" as a filing property is wrong by a factor of five before it starts.

**TWO FILINGS IS NOT A DENOMINATOR, AND SEVEN RUNS IS NOT A CORPUS.** Nothing here extrapolates to
613 filings, to a form string that has not run, or to a filing of a materially different size. Both
proof filings fit every candidate's context intact, so R-21 — whether a materially sized modern
filing does — is untouched by construction. **Repeat-run variability is also unmeasured**: no filing
was parsed twice by the same model, because a rerun is billable and none was authorized.

## The discounted tiers, verified but NOT enabled

Investigated 2026-08-04 from the AWS Price List API bulk file for `us-east-1`:

```
Standard     what every measurement above was billed at
Flex         exactly 50% of Standard, SYNCHRONOUS. Verified for gpt-oss-120b in us-east-1 at
             USD 0.000075/1K input and USD 0.0003/1K output. Four of the five candidates list it.
Batch        exactly 50% of Standard, ASYNCHRONOUS (24-168h job timeout), S3 JSONL input.
             us-east-1 is absent from Qwen3 235B A22B's batch region list.
Priority     +75% over Standard. Standard is the MIDDLE of three synchronous prices, not the floor.
Reserved     1- or 3-month capacity reservation. NOT supported on the candidate model cards read.
Provisioned  none of the five candidates appears on the supported-models table.
Throughput
```

At Flex rates the GPT OSS 120B run above would have cost `USD 0.184957` rather than `USD 0.369913`.
**NOTHING IS ENABLED.** Flex carries materially lower throughput limits, switching tiers mid-proof
would change what was being measured, and enabling it is a user decision that has not been made.

**A NOTE ON WHY PROMPT CACHING WOULD NOT HELP EVEN IF IT EXISTED.** `bedrock.py` places the
per-call brief FIRST and the intact filing after it, deliberately, so the instruction is readable
before the filing it concerns. Prefix caching matches a strict token prefix, so the invariant 40,000
tokens are not a shared prefix at all. Reordering is a semantic change requiring re-benchmarking and
explicit approval; it has not been made.

## What the ceilings do about it

Three, and the tightest refuses:

```
cumulative    everything this repository has ever authorized. Never resets.
phase         what the currently authorized task may spend against the same durable journal.
filing run    what ONE filing's parse may spend across every call it queues.
```

The filing-run ceiling exists because a multipart parse can queue a dozen billable calls off one
plan, and without it a single filing that planned ambitiously could consume the whole authorization
before another filing ran. A refusal PAUSES the branch with its reason visible; nothing is shrunk,
dropped or downgraded to fit, and nothing already produced is discarded.

Every provider attempt reserves its conservative worst case before the call and settles against
measured usage after it. **A failed attempt's reservation is not released** — and a retry takes a
second reservation.

The rationale that used to sit here, "that request was issued and cost money", does not hold for
every failure. Four attempts in this phase failed at CREDENTIAL RESOLUTION, before transport:
`input_tokens 0`, `latency_ms 0`, no `provider_request_id`, and no settlement entry. They hold
`USD 0.10396815` of ceiling for calls that never reached a provider. The MECHANISM is stated
above and is unchanged; the justification is narrower than the mechanism, and closing that gap is
open work rather than a claim.

> **CORRECTED 2026-08-04 BY PHASE 2.2, ADDITIVELY. THE FIGURE ABOVE IS TOO SMALL BY MORE THAN
> HALF, AND THE COUNT IS WRONG BY EIGHT.** The paragraph above is not edited — `rules.md` section
> 21 rule 16 — and the corrected accounting, read directly out of the durable journal, is:
>
> ```
> TWELVE task ids hold unsettled reservations totalling  USD 0.24197085
>
> ELEVEN are the SAME credential failure                 USD 0.22590990
>     TokenRetrievalError, token expired and refresh failed, each with attempts 1,
>     input_tokens 0, output_tokens 0, latency_ms 0, provider_request_id null, task
>     state FAILED, all taken between 02:19:29 and 02:23:00 on 2026-08-04. The four
>     named above are a SUBSET of these eleven.
>
> THE TWELFTH IS A DIFFERENT DEFECT                      USD 0.01606095
>     tsk_icujnsgypwpkxl6xxthsahrpya SUCCEEDED, with real usage of 38,361 input and
>     1,228 output tokens and a real provider request id. It carries TWO reservations
>     of USD 0.01606095 and ONE settlement releasing one of them: the task was
>     interrupted after reserving, resumed, and reserved again, and the journal settled
>     only the later entry.
> ```
>
> **THE TWO ARE DIFFERENT FAILURES AND MUST NOT BE COUNTED AS ONE.** Eleven are ceiling held for
> calls that never reached a provider. The twelfth is ceiling held by a call that DID reach one,
> succeeded, and was billed — a resume-after-reserve leak, and the only one of the twelve that a
> credential fix would not have prevented.
>
> **A RELEASE PATH NOW EXISTS, AND IT DEMANDS PROOF RATHER THAN A JUDGEMENT.**
> `packages/orchestrator/spend_journal.py` gains `release()` and `unsettled()`. A RELEASE entry
> carries `amount_usd 0` and `released_usd` equal to the reservation, so it contributes exactly the
> negative of the reservation to `sum(amount - released)` and no total needed different arithmetic.
> The journal stays append-only: nothing is edited and nothing is deleted.
>
> ```
> release() REFUSES without evidence text. A release with no recorded evidence is
> indistinguishable from un-charging a real failure.
>
> The executor releases ONLY on a failure the adapter PROVES was never transported.
> packages/llm_gateway/errors.py gains CredentialResolutionError carrying
> transport_attempted=False; ProviderError itself gains transport_attempted defaulting
> to TRUE. The asymmetry is deliberate: assuming a request was sent when it was not
> merely holds ceiling, while assuming it was not sent when it WAS releases money that
> was really spent.
> ```
>
> The unconditional sentence above — "a failed attempt's reservation is not released" — is
> therefore narrowed, not reversed. A failure that reached a provider is charged and stays charged.

---

# WHAT PHASE 2 ACTUALLY MEASURED — added 2026-08-03

**THE PRICE INPUTS WERE ALREADY REAL. THE TOKEN COUNTS NOW ARE TOO.** Phase 1 verified official
published prices; Phase 2 sent filings to models and recorded what the provider reported. The
per-filing figures, the per-model comparison and the measured spend are in
`../sprints/PHASE-0002-parser-experiments-and-review-ui.md` and `model-benchmark.md`, and they are
not repeated here — a number recorded twice drifts, and this document's job is the formula.

**WHAT IS NOW ENFORCED IN CODE, NOT MERELY SPECIFIED.**

```
the bound            packages/model_catalog.PriceInputs.cost, in Decimal, from the reviewed
                     snapshot. The worst case is computed from the largest input and output the
                     request can consume, never from an average.
the reservation      packages/orchestrator.SpendJournal.authorize charges the worst case BEFORE
                     the call and refuses when it would breach the cumulative ceiling.
the settlement       .settle replaces the reservation with the provider-reported usage.
durability           the journal is written to the evaluation store and re-derived at start-up. A
                     ceiling that resets when the process does is a per-process suggestion, and
                     this one does not.
failures are charged a billable request that failed still cost money. Charging only successes
                     would let a run of rejections walk past the ceiling.
no SDK retry         the provider client is configured for ONE total attempt. botocore retries by
                     default, and a retry inside the SDK is a second charge the journal never sees.
```

**THE ESTIMATE-VERSUS-MEASUREMENT GAP IS NOW DATA (R-24).** The pre-spend guard uses a character
ratio, which is an upper bound and not a count. Every invocation records the estimate beside the
provider-reported input tokens, so the size of that gap is measured per filing rather than
asserted. The comparison is in the benchmark document.

**STILL NOT MEASURED, AND NAMED SO NOBODY EXTRAPOLATES ANYWAY.**

```
image input tokens   Bedrock bills image input as input tokens and publishes no conversion. The
                     pre-spend bound charges a deliberately generous UNVERIFIED constant.
repeat-run variance  no filing was parsed twice by the same model. A rerun is billable and none
                     was authorized.
a filing that does   the shared benchmark could only contain filings that fit every candidate, so
   NOT fit           the cost of the 44 percent of primary documents above ~200k estimated tokens
                     remains unmeasured. That is R-21, and it is untouched.
corpus scale         three filings is not a denominator. Nothing here multiplies up to a corpus.
```

---

## Why the previous estimate was withdrawn — twice. HISTORICAL.

An earlier version of this architecture quoted roughly 8,500 US dollars for a full-corpus
summarization backfill. That figure was computed on the wrong unit of work: it assumed 58
summarization jobs for Apple's FY2025 10-K, where the correct footnote count is 13 (ADR-0005). The
unit was wrong by a factor of about 4.5, so the figure was withdrawn.

**It was then withdrawn a second time, in the other direction.** ADR-0016 corrected the product
scope from footnote-only to complete filing coverage. The deterministic pipeline then counted the
summarized surface of that same 10-K at **67 required summary units** rather than 13, of which 13
were footnotes. Any total extrapolated from footnote counts understates the real figure by roughly a
factor of five, for exactly the reason the first estimate overstated it: the wrong unit of work.

Both figures — 13 and 67 — were produced by the deterministic parser that ADR-0017 deleted, on one
issuer. **Neither is a parameter of this cost model.** They are retained here only because the
lesson is about the UNIT OF WORK, and that lesson survives the code: a total extrapolated from the
wrong denominator is confidently wrong in whichever direction the denominator is wrong.

This document supplies the formulas. It does not supply a total, because the parameters that
matter have not been measured yet and a number produced without them would repeat the same mistake
a third time.

## Parameters

**EVERY SYMBOL BELOW IS A PLACEHOLDER.** Not one is a measured cost input, and no row may be read as
a result. A placeholder is written as a named symbol, never as an invented number, and it is
resolved by Phase 1 discovery or Phase 2 measurement — never by inference from another document.

Where a row records a prior observation, that observation is dated context, not a value to compute
with. The unit and block counts this table once carried as MEASURED came from the deleted
deterministic parser on one issuer, so the whole per-unit denominator is now unknown: what a
"content unit" even is will be determined by what a parsing model returns.

| Symbol | Meaning | Status |
|---|---|---|
| `F` | Filings in the covered corpus | PLACEHOLDER. Prior estimate 171,000, interval 86,000 to 257,000, n=15 |
| `U_filing` | Required summary units per filing | PLACEHOLDER. No current denominator exists |
| `C_unit_count` | Leaf chunks per oversized unit | PLACEHOLDER |
| `T_intact` | Input tokens for the intact source set of one filing | PLACEHOLDER. The dominant parsing cost |
| `T_src` | Source tokens per content unit | PLACEHOLDER |
| `T_tbl` | Table tokens per content unit | PLACEHOLDER |
| `T_sys` | System prompt tokens | PLACEHOLDER. Estimable from a written prompt; none is written |
| `T_out` | Output tokens per summary | PLACEHOLDER |
| `T_parse_out` | Output tokens for one parsed artifact | PLACEHOLDER |
| `T_agg` | Output tokens per aggregate summary | PLACEHOLDER |
| `R_retry` | Retry rate on validation failure | PLACEHOLDER |
| `R_repair` | Repair-call rate | PLACEHOLDER |
| `P_in` | Input price per million tokens | PLACEHOLDER, provider catalog unverified |
| `P_out` | Output price per million tokens | PLACEHOLDER |
| `D_batch` | Batch discount | PLACEHOLDER |
| `D_flex` | Flex discount | PLACEHOLDER |

The one input that is not guesswork is filing SIZE, which is a property of the preserved bytes
rather than of any parse. Dated Phase 0 corpus evidence: 44 percent of primary documents exceed
~200,000 estimated tokens and 12 percent exceed ~1,000,000, at 3.0 characters per token. **Those are
character-ratio estimates, not provider tokenizer counts**, and `T_intact` is not settled until a
provider counts it.

## Formulas

**Parsing comes first and is priced per FILING, not per unit.** Under `INTACT_SOURCE_ONLY` the
complete relevant human-readable source set goes to the parsing model in one invocation, so there is
no unit decomposition on the input side and no chunking to model:

```
C_parse = (T_sys + T_intact) / 1e6 * P_in + T_parse_out / 1e6 * P_out
C_parse_effective = C_parse * (1 + R_retry)

An INCOMPATIBLE filing/model pairing costs 0. It is refused before invocation, not truncated
into affordability.
```

`T_intact` is not a modelled quantity — it is the size of preserved bytes, checked against a
discovered context limit before the call. A rerun of the same filing on the same model is a full
`C_parse` again; parsing is not incremental.

Everything below prices the OPTIONAL summary stage, whose unit decomposition depends on a parsed
artifact no model has yet produced. **Read it as a shape, not as a plan.**

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

Corpus backfill — **parsing is always in the total, summarization only when selected**:

```
C_backfill = F * ( C_parse_effective + selected_summary_share * E[U_filing] * C_effective )
```

```
DO NOT EXTRAPOLATE FILING COST FROM FOOTNOTE COUNTS.

E[U_filing] is the required-summary-unit count, not the footnote count. Using a footnote count
where U belongs reproduces the withdrawn estimate's defect with a different sign. There is at
present NO measured value for either, so no total may be computed from this line.
```

Monthly steady state:

```
C_monthly = new_filings_per_month
            * ( C_parse_effective + selected_summary_share * E[U_filing] * C_effective )
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

Caching is a prefix match. Every filing is a different document, so only the system prompt is
shared, and under `INTACT_SOURCE_ONLY` the shared prefix is a vanishing fraction of a request whose
bulk is the filing itself. **Cache savings are not modelled into the backfill budget.** Caching pays
on multi-pass work over the same filing — Deep Dive, and repeated summary regeneration against one
accepted parse.

## Batch packing

The binding constraint on a batch is usually the total payload size, not the request count. Batches
are packed **by measured bytes** with headroom, not by counting requests. Batch requests expire,
and expiry is silent, so a watchdog re-queues expired requests rather than leaving a hole that
looks like completion.

## Serialization savings — NOT MEASURED, NOT CLAIMED

**No serialization saving figure exists.** The harness that recorded token counts across plain text,
YAML, Markdown, JSON and XML was removed once ADR-0013 was decided;
`packages/llm_gateway/token_counter.py` now offers a character-ratio estimate and nothing else. No
percentage may be assumed in its place.

The sources of saving are still real on the SYNTHETIC side: keys are not repeated per record as they
are in JSON, prose is not escaped, and tag names are not repeated as they are in XML.

**The saving that used to be described as the largest — raw HTML and XBRL never reaching the model —
no longer applies to the parsing role and must not be counted.** Under `INTACT_SOURCE_ONLY` the
original artifact goes to the parsing model in SEC's own syntax, markup included, by design. That is
a cost the architecture accepts in exchange for not deciding in code what a filing means.

The production path selects plain text or YAML for synthetic content regardless, because the
boundary is a correctness and security constraint rather than an optimization.

## Cost accounting levels

Measured and published at every level, because a single per-filing number hides which content type
is expensive:

```
per source character            per preserved source byte
per input token                 per output token
per parsed filing               per run, under one parent run ID
per leaf chunk                  per summary unit
per filing                      per issuer history
```

Any finer breakdown — per Part, per Item, per footnote — is reported only in whatever terms the
accepted parse actually uses. **The accounting must not impose a unit the parse did not produce.**
Naming the levels in advance is how a universal filing taxonomy gets built by accident.

And separated by **kind of spend**, because these have different growth curves and different
optimizations:

| Kind | What drives it |
|---|---|
| Acquisition and preservation | No model cost at all. Recorded to show it is zero |
| Parsing | One invocation per filing per parse attempt; dominated by intact source size |
| Image analysis | Only when the parsing model is text-only and an image model is selected |
| Initial summarization | Optional stage; summary units × tokens per unit |
| Aggregate summarization | Grows with the depth of the hierarchy the parse returned |
| Validation retry | `R_retry`, `R_repair` |
| Deep Dive | Sessions × turns; unrelated to backfill |
| Reprocessing | Prompt version, model change, or a new source hash |

## Required scenarios

Once parameters are measured, publish: one typical 10-Q, one large 10-K, one issuer's full history,
the top 100 issuers, the top 500 issuers, the full covered universe, monthly steady state, one Deep
Dive session, and one follow-up turn. Each with a sensitivity analysis over `T_intact`, `T_out` and
`R_retry`, which are the parameters the total is most sensitive to.

Report a parser-only run separately from every combination that adds an optional stage. **A
parser-only run is a complete, valid run**, it is the cheapest configuration the product offers, and
a total that silently assumes all four models is not the total most runs will incur.

**The go/no-go rests on complete filing processing.** A unit-economics verdict computed over a
subset of a filing approves a program more expensive than the one it measured — which is the defect
both withdrawn estimates shared.

## Spend is bounded by identity, not only by code

A budget enforced only in application code is a budget a bug can exceed. The IAM identity used for
any real-model run is scoped to an explicit model allowlist and region, so a runaway loop is
refused by AWS rather than merely counted by Kopexx. See
`docs/security/aws-identity-and-secrets.md`.

## Non-negotiable

Cost optimization must not reduce **source coverage** or financial fidelity. Every human-readable
source range is represented in the accepted parsed artifact or explicitly marked unresolved, and
every footnote the accepted parse identifies stays an independent node and an independent required
summary target. Neither is a cost variable.

`INTACT_SOURCE_ONLY` is not a cost variable either. Truncation, semantic slicing, mechanical
multipart and visible-content projection are prohibited, and a lower token bill is not authorization
for any of them.

If the measured economics are unaffordable, the response is a decision about which issuers or which
periods to process, or which optional stages to run — never a decision to send part of a filing and
call the result complete.
