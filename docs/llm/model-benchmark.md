# Summarization Model Benchmark

> **RE-FOUNDED 2026-08-02 ON MEASURED EVIDENCE.** A representative corpus of **112 SEC issuers and
> 613 filings across six transport eras** was acquired and measured — dated Phase 0 evidence, not a
> permanent constant — and it refuted the assumptions the deterministic semantic parser rested on.
> The product is an orchestrator-driven, model-first SEC filing product: the backend acquires,
> preserves, transports, orchestrates and VALIDATES; a user-selected parsing model determines what
> a filing means. The user selects four models independently — parsing, image, summary, and
> analysis/chat — and **only the parsing model is required**. The current authorized input mode is
> `INTACT_SOURCE_ONLY`. Sections below that describe the withdrawn design are historical.
>
> **UPDATED 2026-08-03.** The deterministic content ontology and the local application database are
> no longer merely withdrawn — the parser, the persistence layer and the migrations are DELETED, and
> no application database exists. **Grading a parsing model against a deterministic parse is now
> prohibited** (`rules.md` section 21 rule 15).
>
> **UPDATED 2026-08-03 BY PHASE 1.** AWS identity is verified and all five candidates have been
> reached. That is REACHABILITY, not a benchmark: seven one-word invocations proved transport,
> authorization and request format, and measured nothing about quality. **NO BENCHMARK HAS BEEN
> RUN.** The verified identifiers, regions, modalities, limits and prices are in
> `bedrock-capability-snapshot.yaml` and are not repeated here.
>
> **UPDATED 2026-08-03 BY PHASE 2. THE TWO NOTES ABOVE ARE SUPERSEDED, AND EXACTLY ONE OF THEM WAS
> ABOUT SOMETHING THAT CHANGED.** SEC filings HAVE now been sent to models, a shared cross-model
> benchmark HAS been run, and results ARE claimed — for three filings, under two prompt versions,
> against five candidates. The prohibition on grading a parsing model against a deterministic parse
> is UNCHANGED and was honoured: every check in this benchmark compares a response to the PRESERVED
> SOURCE BYTES, and no second parse exists to compare it to.
>
> **UPDATED 2026-08-03 BY PHASE 2.1. THE PHASE 2 RESULTS STAND AS HISTORY AND ARE NOT REWRITTEN.**
> They measured the SINGLE-RESPONSE protocol, and the protocol was the thing under test as much as
> the models were: three of the five candidates cap output at 8,000 tokens, four of that benchmark's
> five truncation failures were that cap, and the deepest parse produced was itself truncated. A
> MODEL-DIRECTED MULTIPART protocol now exists, and re-running the shared benchmark under it is what
> would make the two comparable.
>
> **THAT RE-RUN IS INCOMPLETE.** One candidate, `GPT OSS 120B`, produced a valid 24-part plan and
> four completed parts on the preserved 3M 10-K405; the AWS session then expired mid-run.
> Four candidates and the multimodal filing have not run. The partial evidence is in
> `docs/sprints/PHASE-0201-model-directed-multipart-parsing.md` section 3.
>
> **SUPERSEDED 2026-08-04, ADDITIVELY. THE RE-RUN FINISHED.** The note above is kept unedited
> (`rules.md` section 21 rule 16) and is no longer true: the credential event cleared, and all five
> candidates ran the multipart protocol on the 3M 10-K405 while both multimodal candidates also ran
> the image-bearing Macy's 10-Q/A — **seven runs, `USD 2.603827` measured**. Results are in
> `docs/sprints/PHASE-0201-model-directed-multipart-parsing.md` section 3. **Nothing in them ranks,
> scores, promotes or eliminates a candidate, and `table_count` is ZERO in all seven.**
>
> **UPDATED 2026-08-04 BY PHASE 2.2. NO MODEL WAS INVOKED IN THAT PHASE AT ALL.** It re-verified
> the committed capability evidence read-only, censused what else the account offers, and measured
> intact-source compatibility for a materially sized modern filing — which is the first result this
> document carries that a candidate **cannot** produce. See
> [PHASE 2.2](#phase-22--compatibility-a-census-and-still-no-benchmark-2026-08-04).
>
> **NOTHING HERE RANKS, SCORES, PROMOTES OR ELIMINATES A CANDIDATE, UNDER EITHER PROTOCOL.** All
> five remain equally available for user-directed testing, and a comparison drawn from one candidate
> is exactly the reasoning `rules.md` section 21 rule 14 forbids.
>
> Authoritative: `docs/adr/ADR-0016-corpus-first-model-first-architecture.md`,
> `docs/adr/ADR-0017-delete-the-rejected-parser-and-application-persistence.md`,
> `docs/adr/ADR-0019-parser-review-application-over-a-framework.md` and `roadmap.md`.

---

# PHASE 2.2 — Compatibility, a census, and still no benchmark (2026-08-04)

**NO MODEL WAS INVOKED. NO PROVIDER REQUEST WAS ISSUED. MEASURED SPEND: `USD 0.00000000`.** No
candidate was added to the approved set, none was removed, **and no parser was selected, ranked,
promoted or eliminated.** Everything below is either a read-only observation of the account and the
public price and documentation surfaces, or a compatibility computation the repository's own
pre-spend guard performs before any call.

## The first candidate this document records as INCOMPATIBLE

Measured against Apple Inc., CIK `0000320193`, form 10-Q, accession `0000320193-25-000008`, filed
2025-01-31, inline XBRL. Its 6 human-readable members total **915,890 characters** and it carries
2 filed images. Input is a **character-ratio estimate at 3.8 characters per token, an upper bound
and not a tokenizer count**; the two multimodal rows include 2 images at the **UNVERIFIED**
4,000-tokens-per-image bound the guard uses.

| model | context | estimated input | largest output that fits | result |
|---|---:|---:|---:|---|
| GPT OSS 120B | 128,000 | 243,507 | 0 | **INCOMPATIBLE** |
| NVIDIA Nemotron 3 Super 120B | 256,000 | 243,507 | 12,493 | fits |
| Qwen3 235B A22B | 256,000 | 243,507 | 8,000 | fits |
| Llama 4 Maverick | 1,000,000 | 251,507 | 8,000 | fits |
| Qwen3 VL 235B | 256,000 | 251,507 | 4,493 | fits |

**`GPT OSS 120B` CANNOT RECEIVE THIS FILING AT ALL, AND NOT MARGINALLY** — the source set is
roughly 1.9x its entire context window, and no output request makes that fit. Under
`INTACT_SOURCE_ONLY` that is a RESULT and is recorded as an exact blocker: nothing is truncated,
sliced, or swapped to another model.

**TWO CANDIDATES FIT ONLY BY SHRINKING THE ANSWER.** Nemotron's own output cap is 32,000 and it
fits at 12,493; Qwen3 VL's is 8,000 and it fits at 4,493, leaving 493 tokens of headroom — inside
the error bar of a character-ratio estimate.

This is **R-21** — "no candidate model accepts a materially sized modern filing intact" — producing
evidence for the first time. Phase 2 and Phase 2.1 could not touch it: by construction their shared
benchmark could only contain filings that fit every candidate.

## What the read-only census found

Run 2026-08-04 in `us-east-1` under a temporary federated role, control plane and public price and
documentation surfaces only. No `bedrock-runtime` call, no resource created.

```
119   foundation models visible to this account in us-east-1
 88   of them emit text
 88   AUTHORIZED, entitlement AVAILABLE — nothing is blocked in this account
 63   system-defined inference profiles, across two geographies, us. and global.
```

**THE FIVE APPROVED CANDIDATES ARE UNCHANGED.** Present, ACTIVE, same inference types, same
modalities, same access status. `Qwen3 235B A22B` is still absent from `us-east-1` and still
present in `us-west-2`, exactly as the snapshot records, and `Llama 4 Maverick` still cannot be
invoked by bare model id.

## Zero drift on every committed value

```
all ten committed prices              match the live Price List API TO THE DIGIT, effective
                                      2026-07-01
all five context and output limits    match the AWS model cards read 2026-08-04
```

**The capability snapshot did not need replacing**, and no value in it was edited. This is the
first time R-33 — the snapshot goes stale silently — has been checked rather than assumed. The
prices themselves are not repeated here; `bedrock-capability-snapshot.yaml` is their single home.

## Three candidates the census identified, and did NOT run

**IDENTIFIED, DOCUMENTED, NOT ADDED, NOT INVOKED, NOT COMPARED.** They are recorded here so that
the decision is ready if it is ever taken; they are not approved candidates and no result of any
kind exists for them. If one is ever adopted, its identifiers, limits and prices move into
`bedrock-capability-snapshot.yaml` and are deleted from here, because a capability recorded twice
drifts.

```
1  Amazon Nova 2 Lite
   model id       amazon.nova-2-lite-v1:0
   invoked via    us.amazon.nova-2-lite-v1:0 — an inference PROFILE is REQUIRED
   region         seen in the us-east-1 census; the profile is a us. geography route
   price          0.00033 in / 0.00275 out per 1k standard
                  0.000165 in / 0.001375 out per 1k flex; cache read 0.000144375
   limits         1,000,000 context, 64,000 max output, text + image + video
   why noted      the only model in the account combining a context that holds this filing with
                  room to spare AND an output limit 8x three of the five candidates. It is also
                  the only relevant model that publishes a prompt cache rate at all.
   risk           output is priced at 8.3x its input, so a 64K response costs USD 0.176. An
                  inference profile is a data-residency decision, not only a throughput one.
   dry-run cost   one Apple run at 12 calls: USD 1.15

2  Llama 4 Scout
   model id       meta.llama4-scout-17b-instruct-v1:0
   invoked via    us.meta.llama4-scout-17b-instruct-v1:0
   region         seen in the us-east-1 census
   price          0.00017 in / 0.00066 out per 1k; no flex published, batch at 50 percent
   limits         10,000,000 context, 8,000 max output, text + image
   why noted      removes the INPUT problem for every filing in the 613-filing corpus, including
                  the 12.9 MB JPMorgan 10-K that fits nothing else. Cheaper than Maverick in both
                  directions, and a known transport path — it is Maverick's sibling.
   risk           8,000 output, so the part count stays high; against THIS filing it adds little
                  that Maverick's 1M context does not already give
   dry-run cost   one Apple run at 14 calls: USD 0.58

3  Mistral Large 3
   model id       mistral.mistral-large-3-675b-instruct
   invoked via    ON_DEMAND, no profile
   region         seen in the us-east-1 census
   price          0.0005 in / 0.0015 out per 1k; flex at 50 percent
   limits         256,000 context, 32,000 max output, text + image
   why noted      largest parameter count in the account, multimodal, no profile and therefore no
                  data-residency decision, and a 32K output limit matching the best of the five
   risk           256K context means it fits only by shrinking the answer, the same trade as
                  Nemotron; 3.3x Nemotron's input price
   dry-run cost   one Apple run at 20 calls: USD 2.50
```

Also observed and recorded because a later reader will otherwise look for them: the
**1M-context / 128K-output combination exists only in the Claude family**, which is priced under a
different service code; `Llama 4 Scout` at 10M is the only model documented above 1M anywhere on
Bedrock; and `GLM 5` at 200K context / 128K output is the largest output limit outside Claude on an
ordinary on-demand path and is **INCOMPATIBLE** with this filing on the same arithmetic that
excludes `GPT OSS 120B`.

## A LARGER OUTPUT LIMIT IS A COST FACT, NOT A QUALITY FACT

This is the sentence that has to be read before any of the three entries above is acted on.

```
A larger output limit lets the model return more per call, which lets a plan use fewer parts,
which lowers the number of times the intact filing is re-sent, which lowers cost.

It says NOTHING about whether the parse is correct. Not whether a node's title, type, boundary
or period is right. Not whether a table was read. Not whether a region of the filing was
represented at all.
```

Correctness is a human judgement made in the review UI, and `review_history` is empty on all seven
Phase 2.1 runs. Choosing a model because its output limit is bigger would be selecting a parser on
a transport property — the shape of reasoning `rules.md` section 21 rule 14 exists to stop.

## What Phase 2.2 did not measure

```
NOTHING ABOUT ANY MODEL'S BEHAVIOUR. No request was issued, so no parse, no table, no citation
and no cost of any run was observed in this phase.

REPEAT-RUN VARIABILITY. R-23, still untouched. No filing has been parsed twice by the same model
under either protocol.

WHETHER THE FOUR COMPATIBLE CANDIDATES CAN ACTUALLY PARSE THIS FILING. The benchmark did not
run: at their own measured Phase 2.1 call counts it costs USD 13.3745 against USD 5.00
authorized. The arithmetic is in `cost-model.md`.
```

---

# PHASE 2 — THE FIRST SHARED CROSS-MODEL BENCHMARK (2026-08-03)

**THREE FILINGS IS NOT A CORPUS, AND NOTHING HERE GENERALISES.** The Phase 2 benchmark was
deliberately small: a shared set that every candidate could receive INTACT, so the comparison is
between models rather than between what each model happened to be given. `rules.md` section 21
rule 14 forbids generalising a corpus conclusion from one issuer; the same logic forbids
generalising a model conclusion from three filings, and this document does not.

## What was measured, and what could not be

```
MEASURED     request accepted; response received; exact response bytes; valid YAML; visible answer
             separated from reasoning content; output truncation; node count; table count;
             model-selected type vocabulary; source-reference count; references RESOLVED against
             the preserved bytes, and how; ambiguous and unresolved references; artifacts cited;
             declared unresolved content; image coverage; generic numeric signals; latency;
             provider-reported input and output tokens; measured cost.

NOT MEASURED repeat-run variability — no filing was parsed twice by the same model, because a
             rerun is billable and none was authorized. That is R-23 and it is untouched.

             Behaviour on a filing that does NOT fit — by construction the shared set could not
             contain one. That is R-21 and it is untouched.

             Parse ACCURACY. Nothing here says a parse is correct. What it says is that a citation
             resolves in the source or does not, and that a reported number occurs in the source or
             does not. Correctness is a human judgement made in the review UI.
```

## The selection constraint, stated plainly

The binding constraint was the **smallest verified output limit**, not the smallest context. Every
candidate's context comfortably held every benchmark filing. Three of the five have an 8,000-token
output cap, and a complete structured parse of even a small filing can exceed it — which turned out
to be the single most discriminating fact the benchmark found.

## Results

### Prompt version 1

**B1 — Walmart 10-K 1995, pre-1996 SGML, complete submission**  
`0000104169-95-000004`

| model | region | in | out | cap | stop | ms | USD | verdict | nodes | tables | refs resolved | types | numbers in source |
|---|---|---:|---:|---:|---|---:|---:|---|---:|---:|---|---:|---|
| GPT OSS 120B | us-east-1 | 23,091 | 4,250 | 15,913 | `end_turn` | 71,500 | 0.00601365 | PARTIAL | 27 | 1 | 20/25 | 7 | 19/19 |
| NVIDIA Nemotron 3 Super 120B | us-east-1 | 27,919 | 5,857 | 15,913 | `end_turn` | 50,009 | 0.00799490 | UNPARSEABLE (html_markup) | 0 | 0 | — | 0 | — |
| Qwen3 235B A22B | us-west-2 | 26,617 | 8,000 | 8,000 | `max_tokens` | 91,673 | 0.01289574 | UNPARSEABLE (xml_tag) | 0 | 0 | — | 0 | — |
| Llama 4 Maverick | us-east-1 | 22,983 | 688 | 8,000 | `end_turn` | 4,746 | 0.00618328 | UNPARSEABLE (markdown_fence, inline_backtick, yaml_preamble, yaml_postamble) | 0 | 0 | — | 0 | — |
| Qwen3 VL 235B | us-east-1 | 26,616 | 8,000 | 8,000 | `max_tokens` | 137,251 | 0.03538648 | UNPARSEABLE (xml_tag, markdown_fence, inline_backtick, yaml_preamble) | 0 | 0 | — | 0 | — |

**B2 — Macy's 10-Q/A 2025, inline XBRL, image-bearing**  
`0000794367-25-000156`

| model | region | in | out | cap | stop | ms | USD | verdict | nodes | tables | refs resolved | types | numbers in source |
|---|---|---:|---:|---:|---|---:|---:|---|---:|---:|---|---:|---|
| GPT OSS 120B | us-east-1 | 19,385 | 9,676 | 10,661 | `end_turn` | 40,798 | 0.00871335 | PARTIAL | 34 | 0 | 40/42 | 20 | 19/19 |
| NVIDIA Nemotron 3 Super 120B | us-east-1 | 22,368 | 6,469 | 10,661 | `end_turn` | 111,125 | 0.00756005 | UNPARSEABLE (xbrl_tag, html_markup) | 0 | 0 | — | 0 | — |
| Qwen3 235B A22B | us-west-2 | 21,446 | 5,711 | 8,000 | `end_turn` | 82,179 | 0.00974380 | REVIEW_REQUIRED | 31 | 4 | 31/31 | 26 | 15/15 |
| Llama 4 Maverick | us-east-1 | 20,009 | 1,103 | 8,000 | `end_turn` | 5,202 | 0.00587207 | UNPARSEABLE (markdown_fence, inline_backtick, yaml_preamble, yaml_postamble) | 0 | 0 | — | 0 | — |
| Qwen3 VL 235B | us-east-1 | 21,576 | 1,722 | 8,000 | `end_turn` | 43,192 | 0.01601580 | UNPARSEABLE (markdown_fence, inline_backtick, yaml_preamble, yaml_postamble) | 0 | 0 | — | 0 | — |

**B3 — 3M 10-K405 1996, Item-405 form, complete submission**  
`0000066740-96-000005`

| model | region | in | out | cap | stop | ms | USD | verdict | nodes | tables | refs resolved | types | numbers in source |
|---|---|---:|---:|---:|---|---:|---:|---|---:|---:|---|---:|---|
| GPT OSS 120B | us-east-1 | 35,607 | 5,375 | 16,000 | `end_turn` | 14,835 | 0.00856605 | PARTIAL | 31 | 4 | 29/31 | 4 | 30/31 |
| NVIDIA Nemotron 3 Super 120B | us-east-1 | 41,014 | 7,547 | 24,044 | `end_turn` | 80,093 | 0.01105765 | UNPARSEABLE (xml_tag) | 0 | 0 | — | 0 | — |
| Qwen3 235B A22B | us-west-2 | 39,615 | 8,000 | 8,000 | `max_tokens` | 144,304 | 0.01575530 | UNPARSEABLE | 0 | 0 | — | 0 | — |
| Llama 4 Maverick | us-east-1 | 35,495 | 1,047 | 8,000 | `end_turn` | 6,468 | 0.00953439 | UNPARSEABLE (markdown_fence, inline_backtick, yaml_preamble, yaml_postamble) | 0 | 0 | — | 0 | — |
| Qwen3 VL 235B | us-east-1 | 39,614 | 8,000 | 8,000 | `max_tokens` | 144,740 | 0.04227542 | UNPARSEABLE (xml_tag, markdown_fence, inline_backtick, yaml_preamble) | 0 | 0 | — | 0 | — |


### Prompt version 2

**B1 — Walmart 10-K 1995, pre-1996 SGML, complete submission**  
`0000104169-95-000004`

| model | region | in | out | cap | stop | ms | USD | verdict | nodes | tables | refs resolved | types | numbers in source |
|---|---|---:|---:|---:|---|---:|---:|---|---:|---:|---|---:|---|
| GPT OSS 120B | us-east-1 | 23,323 | 4,650 | 16,000 | `end_turn` | 28,141 | 0.00628845 | PARTIAL | 24 | 4 | 24/24 | 5 | 10/10 |
| NVIDIA Nemotron 3 Super 120B | us-east-1 | 28,154 | 6,512 | 16,086 | `end_turn` | 76,496 | 0.00845590 | UNPARSEABLE (html_markup) | 0 | 0 | — | 0 | — |
| Qwen3 235B A22B | us-west-2 | 26,849 | 8,000 | 8,000 | `max_tokens` | 170,556 | 0.01294678 | UNPARSEABLE (html_markup) | 0 | 0 | — | 0 | — |
| Llama 4 Maverick | us-east-1 | 23,216 | 645 | 8,000 | `end_turn` | 4,023 | 0.00619749 | PARTIAL | 5 | 0 | 4/5 | 5 | 5/5 |
| Qwen3 VL 235B | us-east-1 | 26,848 | 5,294 | 8,000 | `end_turn` | 85,995 | 0.02831148 | REVIEW_REQUIRED | 26 | 2 | 26/26 | 23 | 4/4 |

**B2 — Macy's 10-Q/A 2025, inline XBRL, image-bearing**  
`0000794367-25-000156`

| model | region | in | out | cap | stop | ms | USD | verdict | nodes | tables | refs resolved | types | numbers in source |
|---|---|---:|---:|---:|---|---:|---:|---|---:|---:|---|---:|---|
| GPT OSS 120B | us-east-1 | 19,617 | 2,469 | 10,834 | `end_turn` | 15,948 | 0.00442395 | PARTIAL | 9 | 1 | 8/9 | 7 | 4/4 |
| NVIDIA Nemotron 3 Super 120B | us-east-1 | 22,603 | 10,834 | 10,834 | `max_tokens` | 122,937 | 0.01043255 | UNPARSEABLE (xbrl_tag, html_markup) | 0 | 0 | — | 0 | — |
| Qwen3 235B A22B | us-west-2 | 21,678 | 2,441 | 8,000 | `end_turn` | 31,871 | 0.00691724 | PARTIAL | 9 | 0 | 17/17 | 5 | 6/6 |
| Llama 4 Maverick | us-east-1 | 20,242 | 1,376 | 8,000 | `end_turn` | 6,798 | 0.00619280 | PARTIAL | 6 | 0 | 1/6 | 4 | 5/5 |
| Qwen3 VL 235B | us-east-1 | 21,808 | 1,590 | 8,000 | `end_turn` | 25,209 | 0.01578764 | REVIEW_REQUIRED | 7 | 0 | 7/7 | 5 | 2/2 |

**B3 — 3M 10-K405 1996, Item-405 form, complete submission**  
`0000066740-96-000005`

| model | region | in | out | cap | stop | ms | USD | verdict | nodes | tables | refs resolved | types | numbers in source |
|---|---|---:|---:|---:|---|---:|---:|---|---:|---:|---|---:|---|
| GPT OSS 120B | us-east-1 | 35,839 | 4,033 | 16,000 | `end_turn` | 13,534 | 0.00779565 | PARTIAL | 25 | 0 | 21/23 | 4 | 11/11 |
| NVIDIA Nemotron 3 Super 120B | us-east-1 | 41,249 | 24,217 | 24,217 | `max_tokens` | 311,241 | 0.02192840 | UNPARSEABLE (yaml_preamble) | 0 | 0 | — | 0 | — |
| Qwen3 235B A22B | us-west-2 | 39,847 | 8,000 | 8,000 | `max_tokens` | 79,015 | 0.01580634 | PARTIAL | 73 | 0 | 69/72 | 68 | 24/24 |
| Llama 4 Maverick | us-east-1 | 35,728 | 1,119 | 8,000 | `end_turn` | 7,068 | 0.00966015 | PARTIAL | 7 | 0 | 7/7 | 7 | 13/13 |
| Qwen3 VL 235B | us-east-1 | 39,846 | 8,000 | 8,000 | `max_tokens` | 151,531 | 0.04239838 | UNPARSEABLE | 0 | 0 | — | 0 | — |


### Estimate versus provider count (R-24)

| model | filing | estimated input | measured input | estimate / measured |
|---|---|---:|---:|---:|
| GPT OSS 120B | B3 | 40,361 | 35,839 | 1.13 |
| GPT OSS 120B | B1 | 26,809 | 23,323 | 1.15 |
| GPT OSS 120B | B2 | 18,056 | 19,617 | 0.92 |
| Llama 4 Maverick | B3 | 40,361 | 35,728 | 1.13 |
| Llama 4 Maverick | B1 | 26,809 | 23,216 | 1.15 |
| Llama 4 Maverick | B2 | 22,003 | 20,242 | 1.09 |
| NVIDIA Nemotron 3 Super 120B | B3 | 40,361 | 41,249 | 0.98 |
| NVIDIA Nemotron 3 Super 120B | B1 | 26,809 | 28,154 | 0.95 |
| NVIDIA Nemotron 3 Super 120B | B2 | 18,056 | 22,603 | 0.80 |
| Qwen3 235B A22B | B3 | 40,361 | 39,847 | 1.01 |
| Qwen3 235B A22B | B1 | 26,809 | 26,849 | 1.00 |
| Qwen3 235B A22B | B2 | 18,056 | 21,678 | 0.83 |
| Qwen3 VL 235B | B3 | 40,361 | 39,846 | 1.01 |
| Qwen3 VL 235B | B1 | 26,809 | 26,848 | 1.00 |
| Qwen3 VL 235B | B2 | 22,003 | 21,808 | 1.01 |

### Totals

- child jobs: **30**
- measured Bedrock spend: **USD 0.40711113**
- prompt v1: 15 invocations, **4 produced a readable parse**, USD 0.20356793
- prompt v2: 15 invocations, **10 produced a readable parse**, USD 0.20354320

## Prompt versions

Two versions were used, and the second exists for an objective format defect rather than to
improve any model's score. `rules.md` and the Phase 2 brief permit a new version when the YAML is
invalid; they prohibit tuning until each model looks successful. Both versions and every result
they produced are preserved. The manifest is `../../prompts/parser/versions.yaml`.

## Where the evidence lives

Every run is open in the parser-review UI by its parent run identifier. For each child job the
evaluation store holds the exact prompt bytes, the exact instruction, the exact submitted source
artifacts, the provider transport envelopes in both directions, the exact visible response, the
reasoning content when the model produced any, the validation record, and the cost. None of it is
tracked by git; it is host state under the ignored `var/evaluation-runs/`.

---

# WHAT PHASE 2 SET OUT TO MEASURE — retained as the specification the run was made against

## The candidates

GPT OSS 120B, NVIDIA Nemotron 3 Super 120B, Qwen3 235B A22B, Llama 4 Maverick, Qwen3 VL 235B.

**All five were mapped, reached and priced on 2026-08-03.** Model IDs, versions, regions,
modalities, context and output limits, supported request formats and prices were DISCOVERED LIVE
and are recorded in `bedrock-capability-snapshot.yaml`. **No identifier in this repository is
trusted until discovery returns it, and none is hardcoded anywhere.**

Three facts from that discovery shape what Phase 2 can attempt:

```
context windows differ by 8x across the five, 128K to 1M, and output limits by 4x, 8K to 32K
one candidate cannot be invoked by model id at all and requires a cross-region inference profile
one candidate is not offered in the primary region, though its own model card says it is
```

Against dated Phase 0 evidence that 44 percent of primary corpus documents exceed ~200,000
estimated tokens, the context spread is the difference between a model that can take an intact
filing and one that cannot. That is measured now instead of assumed.

## What Phase 2 measures, per role

Benchmarks are per ROLE. A model good at parsing is not thereby the right summary model, and the
user selects each independently anyway.

```
PARSING       whether the provider accepts the intact artifact at all
              source coverage against preserved bytes
              citation fidelity — does every cited offset resolve
              numeric fidelity — does every reported number appear verbatim
              omission detection — what disappeared silently
              input tokens, output tokens, latency, cost
              variability across models, and across reruns of the SAME model
IMAGE         description usefulness, correct linkage to the source object
SUMMARY       grounding in the accepted parse, citation fidelity, cost
ANALYSIS      answer grounding, scope adherence, per-turn cost
```

## The corpus samples Phase 2 must use

Materially different, not five filings from one issuer — that is the mistake this whole correction
exists to undo:

```
historical plain-text or SGML      early HTML                pre-inline-XBRL
modern inline-XBRL                 small-business form       transition form
amendment                          young issuer              mature issuer
image-bearing filing               a large filing compatible with at least one available model
```

## The output contract is provisional

The parser request and response contracts are provisional until real responses reshape them. Raw
text or exactly one unfenced YAML 1.2 document, with the original-source exception for the intact
artifact. **The artifact format follows what the models actually return**, not the reverse.

## There is no oracle, and grading against one is prohibited

An earlier version of this section named the deterministic Apple parse — 43 canonical footnotes,
117 of 117 attachments, the table-ownership census — a **recall floor for grading a parsing model**.
That is withdrawn. The code is deleted and the practice is now forbidden: `rules.md` section 21
rule 15 and ADR-0017 section 3.

Grading a model against a deterministic parse makes the deterministic interpretation authoritative
again through the back door, which is exactly what ADR-0016 withdrew. It also generalizes one
issuer, one filing agent and two of six transport eras onto a corpus of 112 issuers, 75 SIC
industries and six eras — and a benchmark that is wrong about breadth is worse than none, because it
produces a number and a number gets believed.

**A parse is validated against the PRESERVED SOURCE BYTES, never against a second parse.** That
control needs no oracle, and it is stronger, because it does not require another interpretation to
be correct first.


IMPLEMENTATION STATUS: PLANNED — the first measurement is Phase 2
DECISION RECORD: `docs/adr/ADR-0006-model-selection-by-benchmark.md`
GATES: not yet written. The footnote-summary evaluation gates were deleted with the prompt they
       scored; real gates are derived from observed model behaviour.
DEEP ANALYSIS MODEL: `docs/llm/analysis-model-benchmark.md` — separate task, separate gates

## Principle

No model is selected until measured on a representative footnote corpus. The strongest available
model is not automatically right for a bounded, highly structured task; that is an empirical
question about numeric fidelity and instruction following.

Among models passing every gate, the **cheapest** is selected.

---

## Identity and budget preconditions

The benchmark runs under a least-privilege identity holding only the Bedrock actions and model
resources it needs. Broad administrator access to ease model discovery is prohibited; discovery is
a one-time convenience and the permission outlives it.

**DISCLOSED: Phase 1 discovery ran under an IAM Identity Center `AdministratorAccess` role**, the
identity supplied for that task. It was a one-time manual discovery producing a document, not a
running capability, and no CI job holds an AWS role. The requirement above is unchanged and binds
before any repeatable or automated invocation path. ADR-0018 section 7.

Permissions are separated for model discovery, standard-summary invocation, Deep Analysis
invocation, request/response object access, and cost metadata. **Deep Analysis and standard
summarization must be separately measurable and separately restrictable** even while sharing one
account — they have different cost and abuse profiles, and one permission covering both makes each
invisible inside the other.

Every run requires a hard invocation budget, a hard dollar budget, an explicit model allowlist, an
explicit region, a manual start, and no automatic retry that can exceed the budget. The workflow
that runs it is gated and cannot trigger implicitly on a push. A pull request from an untrusted
fork receives no role capable of invoking a billable model.

See `docs/security/aws-identity-and-secrets.md`.

## Two benchmarks, not one

The full corpus below is a serious measurement program: 120 gold-labelled footnotes, two
annotators, three-way splits, Wilson intervals. It is the right gate before spending real money
across ~170,000 filings. It is the **wrong** gate before summarizing a single footnote, because
it must be built in full before the pipeline produces anything at all.

The evaluation is therefore split.

### Tier 1 — Slice smoke benchmark (Sprint 5)

> **Corrected in Sprint 4.1 (ADR-0016).** This corpus was 15 canonical footnotes. That measures
> one content type and would have produced unit economics for roughly a fifth of the real
> summarized surface: Apple's FY2025 10-K has **67 required summary units**, of which 13 are
> footnotes. A cost figure extrapolated from the footnote subset would have been wrong in the same
> direction, and for the same reason, as the withdrawn 58-TextBlock estimate.

```
PURPOSE     Prove the pipeline end to end across the CONTENT TAXONOMY and measure real cost
            per content unit and per filing.
CORPUS      A stratified sample of required summary units from the vertical-slice filings,
            spanning every stratum below. Not fewer than 20 units, and the footnote stratum is
            never fewer than the 2 hard cases named below.
LABELS      Figures, units, scales, periods, and signs extracted from the filed source
            programmatically, then reviewed once by a human. Not full gold labels.
CANDIDATES  At least 2, spanning 2 capability tiers.
```

**Required strata.** Every one must appear; none may be the whole corpus.

```
cover-page metadata            Business (Item 1)
Risk Factors (Item 1A)         MD&A (Item 7)
market risk (Item 7A)          legal proceedings (Item 3)
cybersecurity (Item 1C)        controls and procedures (Item 9A)
a financial statement          a routine one-paragraph footnote
a complex table-heavy footnote a human-readable exhibit
a certification                a signature block
a historical filing section    an oversized unit requiring hierarchical chunking
```

**Footnotes must neither disappear from the benchmark nor constitute it.** They are the hardest
stratum and keep the two deliberately hard cases the original corpus named: the largest note and a
routine one-paragraph note.

Gates for tier 1 — deliberately narrower than production gates, because a smoke corpus cannot
establish a rate to three decimal places:

```
structured_output_validity    == 1.0     every response parses as one YAML 1.2 document
unit_omission_rate            == 0.0     every required unit in the corpus produces a summary
footnote_omission_rate        == 0.0     13 footnotes in, 13 summaries out, independently
chunk_coverage                == 1.0     every leaf chunk of an oversized unit is summarized
aggregate_lineage_validity    == 1.0     every aggregate cites only accepted child summaries
numeric_fidelity              == 1.0     any error on a corpus this size is a real defect
unit_and_scale_fidelity       == 1.0
citation_resolvability        == 1.0     every cited id exists and belongs to that unit or an
                                         approved child
qualitative_source_grounding  == 1.0     every narrative claim traces to a supplied block
boundary_violations           == 0       no prohibited format in either direction
recommendations_or_forecasts  == 0       no advice, no price prediction
```

Tier 1 also **measures and publishes**, replacing the placeholders in `docs/llm/cost-model.md`:
`T_src`, `T_tbl`, `T_out`, `R_retry`, observed `P_in` and `P_out`, and cost per source character,
per input token, per leaf chunk, per content unit, per footnote, per Part, per Item, per filing,
and extrapolated per issuer history.

**Passing tier 1 does not select a production model.** It proves the pipeline works, establishes
real unit economics, and produces the go/no-go the project currently lacks. A tier-1 result is
always reported as provisional.

### Tier 2 — Full pre-backfill benchmark

Everything below. Required before any multi-issuer backfill and before any cost commitment.
Its corpus is built incrementally from Sprint 5 onward rather than in one block, so it is ready
when breadth work begins.

---

## Full corpus construction

Minimum 120 canonical footnotes, stratified across three dimensions simultaneously so that a model
cannot pass by being good at one industry or one era.

Industries: software, industrial, retail, bank, insurer, REIT, utility, biotechnology,
acquisition-heavy.

Content types, stratified independently of footnote type: cover page, Business, Risk Factors,
Legal Proceedings, MD&A, market risk, controls and procedures, cybersecurity, other information,
financial statements, financial schedules, exhibits, certifications, signatures, and incorporated
references.

Footnote types: significant accounting policies, revenue recognition, debt, credit facilities,
derivatives and hedging, fair-value hierarchy, income taxes, valuation allowances, stock-based
compensation, pensions, leases, segment reporting, variable interest entities, noncontrolling
interests, litigation and contingencies, impairments, restructuring, going concern, subsequent
events.

Eras: inline XBRL 2019 onward, standalone XBRL 2009 to 2018, HTML without XBRL 2001 to 2008, plain
text before 2001.

Edge cases: very short routine notes, exceptionally large notes, poorly formatted HTML, amendment
partial content, notes with no tables, notes with many tables.

## Splits

```
development   40 percent   prompt iteration
validation    30 percent   model comparison
held-out      30 percent   final gate; used ONCE per candidate
```

The held-out split is not used during prompt development. A prompt tuned against the gate has
measured nothing.

## Gold labels

Each fixture carries a human-produced reference: the correct financial relationships, the correct
important facts with unit, scale, sign, and period, the correct period changes, and the correct
classification. Produced by one annotator and reviewed by a second, with disagreements resolved
and recorded rather than averaged.

Gold labels are versioned. A label found wrong is corrected and the affected scores recomputed,
never quietly patched.

## Scored dimensions

```
content_unit_coverage            canonical_footnote_coverage  omission_rate
chunk_coverage                   aggregate_lineage_validity   unsupported_claim_rate
numeric_fidelity                 date_fidelity                period_fidelity
unit_fidelity                    scale_fidelity               sign_fidelity
citation_precision               citation_recall              financial_relationship_accuracy
material_change_accuracy         accounting_policy_accuracy   risk_identification_recall
qualitative_source_grounding     structured_output_validity   hallucination_rate
concision                        readability                  latency_p50 / latency_p95
retry_rate                       cost_per_content_unit        cost_per_footnote
cost_per_item                    cost_per_filing              human_review_rate
```

## Production gates

A candidate must pass **every** gate. Failing one disqualifies it regardless of the others.

```
numeric_fidelity              >= 0.995
structured_output_validity    >= 0.99
citation_accuracy             >= 0.95
footnote_omission_rate        == 0.0
unsupported_claim_rate        <= 0.01
unit_fidelity                 == 1.0
sign_fidelity                 == 1.0
scale_fidelity                == 1.0
period_fidelity               >= 0.99
```

Unit, sign, and scale gates are exactly 1.0 because each failure is an order-of-magnitude or
directional error in a financial figure, and there is no acceptable rate for that.

## Statistical confidence

Report Wilson score intervals for every rate. A gate is passed only when the **lower bound** of
the interval clears it, so a small sample cannot pass a model by luck. If the interval is too wide
to decide, the corpus is too small and is extended rather than the gate relaxed.

## Serialization comparison

Historical. The harness that recorded token counts across plain text, YAML, Markdown, JSON and XML
was removed once ADR-0013 was decided; `packages/llm_gateway/token_counter.py` now offers a
character-ratio estimate only. The production path selects plain text or YAML regardless of any such
result, because the boundary is a correctness constraint and never was an optimization.

## Result storage

Results are committed alongside the fixtures: model identifier, region, prompt version, schema
version, corpus version, gold-label version, per-dimension scores with intervals, cost, latency
distribution, and the run timestamp. A result whose inputs are not fully identified is not a
result.

## Promotion and rollback

Promotion requires passing every gate on the held-out split and a cost comparison against the
incumbent. Rollback is activating the previous model identifier in configuration; summaries
produced by the regressed model are superseded, never deleted, because they are the evidence for
the post-mortem.

## Regression cadence

Re-run on every prompt version change, every candidate model addition, and on a schedule to detect
provider-side drift behind a stable model identifier.
