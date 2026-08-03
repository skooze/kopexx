# PHASE 2 — Intact-filing parser experiments and the parser-review UI

STATUS: COMPLETE
DATE: 2026-08-03
BASELINE: `6976cc5` (Phase 1)
DECISION RECORD: [ADR-0019](../adr/ADR-0019-parser-review-application-over-a-framework.md)
BUILDS ON: [ADR-0016](../adr/ADR-0016-corpus-first-model-first-architecture.md),
[ADR-0017](../adr/ADR-0017-delete-the-rejected-parser-and-application-persistence.md),
[ADR-0018](../adr/ADR-0018-verified-capability-snapshot-over-a-provider-adapter.md)

---

## What this phase was for

Phase 1 established that five candidate models were reachable and nothing else. Seven one-word
invocations proved transport and authorization; no filing had ever been sent to any of them.

Phase 2 had to answer a different question — can any of them actually read a filing — and
`roadmap.md` 2b says why it could not be answered from a terminal:

```
a parsed artifact cannot be evaluated without looking at it beside the filing it came from
```

So the first experiments and the first review surface were built together. Everything in this
record exists to make one page possible: a preserved SEC filing on the left, a model's structure on
the right, and every citation between them checked against the original bytes.

---

## 1. What was built

Seven new packages, two extended, and **no new runtime dependency**.

```
packages/evaluation_store     parent runs, child filing jobs, exact request and response evidence,
                              an append-only event log, developer comments, and two INDEPENDENT
                              state machines. Not the product database and holds no schema.
packages/source_transport     mechanical source-set assembly: local inventory first, hash
                              re-verified, only missing members fetched, transport dispositions
                              from byte evidence, lossless decoding, intact-source compatibility.
packages/coverage_validation  an elastic reader that preserves unknown model fields, source-
                              reference resolution against the preserved bytes, generic numeric
                              signals. No COMPLETE verdict exists.
packages/prompt_registry      versioned prompts locked by SHA-256. A used version cannot be edited.
packages/orchestrator         preflight, a DURABLE cumulative spend journal, parser-only execution,
                              the local filing catalog, and a bounded in-process worker.
packages/review_api           the review HTTP application on the standard library.
packages/review_web           server-rendered pages, escaping, and two asset constants.

packages/filing_acquisition   + documents.py, the NON-CLASSIFYING filed-document lister, and
                              member_fetch.py
packages/model_catalog        + routing.py, the four-role router that completes the package
packages/llm_gateway          + providers/bedrock.py, the Converse adapter; OriginalSourceBlock;
                              provenance admission; Decimal cost; strict_response=False
packages/storage              + list_keys, and put_bytes now fsyncs before the atomic rename
```

**The runtime dependency list is still `ruamel.yaml` and `httpx`.** `boto3` was added as an
OPTIONAL extra, which is what now makes "ordinary CI is AWS-free" mean the SDK is not installed at
all rather than merely unused. The review UI added nothing: it is served by `http.server`, rendered
in Python, and its stylesheet and single script are module constants. There is no web framework, no
ASGI server, no bundler and no npm.

---

## 2. Benchmark selection, and the evidence for it

The binding constraint was the **smallest verified context of the five candidates**. A shared
cross-model benchmark is only shared if one source set can go to every candidate intact, so the
selection was made against the smallest window, not the largest.

Three preserved filings were selected from the 613-filing research corpus.

```
B1  Walmart Inc.   10-K       1995-04-27  E1_pre1996_text_sgml   cik 0000104169
    0000104169-95-000004      complete submission, 94,979 bytes
    Five filed documents, NONE individually addressable on EDGAR. The complete submission IS the
    complete relevant human-readable source set, and is sent intact.

B2  Macy's, Inc.   10-Q/A     2025-09-12  E6_2022_current        cik 0000794367
    0000794367-25-000156      18 package files, one filed GIF
    Members ARE individually addressable. Four filed text documents plus one image go to the
    model; the flat submission is a duplicate; three XBRL artifacts and seven SEC renderer
    artifacts are dispositioned and reported.

B3  3M CO          10-K405    1996-03-11  E2_1996_2004_early_html cik 0000066740
    0000066740-96-000005      complete submission, 146,471 bytes
    Eight filed documents, none addressable. An Item-405 nonstandard form.
```

Between them: three transport eras, annual and quarterly, standard / Item-405 / amendment,
image-bearing and text-only, addressable and non-addressable member sets. Every object was already
preserved locally; **the benchmark generated no SEC traffic for B1 and B3 at all**, and B2's
individually addressable members were fetched once and preserved.

**WHY NOT A MODERN 10-K.** There is not one that fits. Dated Phase 0 evidence measured 0 of 21
current-era filings in the compatibility dataset fitting a 256,000-token window, and 44 percent of
all primary documents exceeding roughly 200,000 estimated tokens. That is R-21 and it remains
OPEN — this phase measured what a model does with a filing that fits, not what happens to the
filings that do not.

---

## 3. Two defects this phase found, and what found them

### The inline-XBRL primary document was silently dropped

Inline XBRL is XHTML. The primary document of a modern filing opens with an XML declaration and
carries XBRL and XLink namespaces on its `html` root — and the machine-artifact rule, which
correctly identifies an XBRL linkbase, matched it before the HTML-root check ran.

Measured on accession `0000794367-25-000156`: **the 10-Q/A itself was dispositioned MACHINE_ONLY
and excluded from the source set.** Three certification exhibits and an image were submitted. The
coverage counts reconciled — against what had been submitted. Nothing anywhere said the filing had
not been sent.

It was found by reading a disposition table, not by an assertion. The HTML-root check now runs
first, and `tests/unit/test_source_transport.py` locks it with the exact namespace combination.

### The SDK retried underneath the cost ceiling

botocore retries on its own by default, and a Converse call is billable from the moment it is
issued. An SDK-level retry is a second charge that `RetryBudget` never counts and the durable spend
journal never records — the ceiling would have been enforced against a number smaller than the
bill.

Found while diagnosing a read timeout: the SDK's default read timeout is 60 seconds, and the first
real parse of a preserved filing took 158. The client is now constructed with an explicit
configuration — one total attempt, a 900-second read timeout — and
`tests/architecture/test_phase2_boundaries.py` fails the build if either moves.

The timeout half of that change was not precautionary. The slowest measured invocation in this
benchmark ran for **311 seconds** — a 41,249-token input producing 24,217 output tokens — which is
more than five times the default. Under the default that response would have been lost after it had
already been billed, and the SDK would then have silently retried and billed it again.

### A third, found by the benchmark itself

The content-boundary validator could not tell markup that IS the serialization from the same
characters inside a quoted YAML scalar. A parser response is REQUIRED to quote filings verbatim,
and filings are SGML, HTML or inline XBRL — so under the old rule **no response quoting a pre-2001
filing could ever pass**, which is the entire corpus era this product exists to cover. A model
returned a well-formed YAML document whose source quotes carried the filing's own tags, and it was
refused for `html_markup`.

A document that PARSES as one YAML 1.2 mapping is now accepted as one unfenced YAML document, and
only SERIALIZATION violations still apply to it. JSON is a YAML subset, so the JSON detectors stay,
as do the fence, native-tool and structural checks. Mutation tests prove a JSON response, a fenced
response and a genuinely markup response are all still refused.

### And eleven more

The test authors found eleven further defects and reported each rather than working around it. The
most consequential: every modern filing reported its own complete submission as content that never
reached the model; source-reference offsets were emitted in three coordinate systems while the
review UI treated them as one; a zero offset was dropped from a URL because `0 == False`; a
hash-invalid held member was never re-acquired although three docstrings promised it was; and the
adapter crashed with `AttributeError` on `metrics: null`, losing an already-billed response outside
its own error boundary.

Two more were found by reading the execution path after the tests were green: **a retry was a
second billable call taking only one reservation**, and **the source set was reassembled at
execution without checking that it still matched the one that had been costed**. Both are now
refused rather than reconciled.

---

## 4. Measured results

`EVERY TOKEN FIGURE IN SECTIONS 2 AND 3 IS A CHARACTER-RATIO ESTIMATE. Every figure in this
section is a PROVIDER-REPORTED COUNT.` That distinction is the point of the phase.

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

---

## 5. What this phase did NOT do

```
no application database          no Redis            no cache of any kind
no summary artifact              no image artifact   no chat session
no separate image-model call     no bulk backfill    no reusable approved artifact
no breadth across 22 forms       nothing deployed    no final artifact contract
```

An APPROVED artifact records a judgement and activates nothing. No search consults the evaluation
store, no cache is populated, and the reuse gate stays closed until Phase 4 designs it from
artifacts that by then will exist.

The orchestrator refuses to run a summary or analysis stage rather than silently skipping one:
`StageNotAuthorizedError` names the stage and the reason.

---

## 6. Risks

| ID | Movement |
|---|---|
| R-09 | Unit economics were unknown. **First measured per-filing figures now exist** for three filings across five candidates. Still a sample of three. |
| R-21 | No candidate accepts a materially sized modern filing intact. **OPEN and unchanged.** Nothing in this phase tested a filing that does not fit, because by construction the shared benchmark could not contain one. |
| R-23 | Repeat-run variability. **NOT MEASURED.** No filing was parsed twice by the same model; a rerun is billable and none was authorized. |
| R-24 | Character-ratio token estimates are unfit for a compatibility gate. **NOW QUANTIFIED** rather than asserted: every invocation records the estimate beside the provider count. |
| R-33 | The capability snapshot goes stale silently. **OPEN.** Phase 2 read it and did not regenerate it. |
| R-34 | Discovery ran under a broad administrator role. **OPEN.** A least-privilege Bedrock policy is still required before any repeatable or automated invocation. |

---

## 6a. What the results say

**Prompt version 2 more than doubled the readable-parse rate, from 4 of 15 to 10 of 15, and it did
it without changing a single semantic requirement.** Both corrections were format-only: quote a
scalar that contains a colon, and do not wrap the document in a code fence. That is worth stating
plainly, because it means most of what looked like model incapability in the version-1 pass was a
serialisation problem.

**The binding constraint was the OUTPUT limit, not the context.** Every candidate held every
benchmark filing comfortably. Three of the five cap output at 8,000 tokens, and four of the five
truncation failures in this benchmark are that cap. The largest parse produced — 73 nodes with
69 of 72 references resolved — was itself truncated at 8,000.

**Per candidate, under prompt version 2:**

```
GPT OSS 120B         3 of 3 readable, and 6 of 6 across BOTH prompt versions. The only candidate
                     that never once failed to produce a parseable document. Node counts 24 to 34,
                     reference resolution 24/24, 8/9, 21/23. Never truncated.
Qwen3 VL 235B        2 of 3, and the two cleanest verdicts in the benchmark: REVIEW_REQUIRED with
                     26 of 26 and 7 of 7 references resolved, no unresolved content declared. The
                     third truncated at its 8,000-token cap. Roughly four times the cost of the
                     cheapest candidate.
Qwen3 235B A22B      2 of 3, including the DEEPEST parse of the benchmark — 73 nodes, 69 of 72
                     references resolved — which was itself truncated at 8,000 tokens. The third
                     truncated with nothing usable. Runs cross-region.
Llama 4 Maverick     3 of 3 readable, and by far the SHALLOWEST: 5, 6 and 7 nodes against 24 to 73
                     from the others, on 645 to 1,376 output tokens. Also the fastest and among
                     the cheapest. Format-compliant and thin.
NVIDIA Nemotron      0 of 6. It never produced valid YAML under either prompt version, and failed
  3 Super 120B       differently each time: unquoted scalars carrying the filing's own colons and
                     tags under version 1, a nested mapping flattened onto one line under version
                     2. A third prompt version teaching it YAML indentation was considered and
                     refused as tuning for one model.
```

**The character-ratio token estimate was close, and once it was close in the WRONG DIRECTION.**
Estimate-to-measured ratios ran 0.83 to 1.01. A ratio below 1.0 means the pre-spend guard
UNDER-counted, which is the unsafe direction for a check that runs before the money is spent — and
it happened on the modern inline-XBRL filing, where markup density is highest. R-24 is no longer a
suspicion; it is a measured 17 percent under-count in the worst observed case.

## 7. The decision this phase stops at

Phase 2's authorized completion point is a product decision that belongs to the user, not to this
record:

```
Which parser and prompt version should advance to breadth validation across all 22 substantive
10-K/10-Q-family form strings?
```

Nothing selects a winner automatically. The evidence is in section 4, every run is open in the
review UI by its parent run identifier, and the exact request and response bytes for all of it are
preserved.

### The recommendation, and the tension it does not resolve

**On this evidence, GPT OSS 120B with `parser-complete-filing@2`.** It is the only candidate that
produced a readable parse on every filing under both prompt versions — 6 of 6 — it never truncated,
its reference resolution is consistently high, and it is among the cheapest. For a breadth run
whose whole purpose is to find out what happens across 22 form strings, a parser that reliably
returns a readable document is worth more than one that occasionally returns a better one.

**The tension is that the format leader is the size-constrained one.** GPT OSS 120B has the
SMALLEST verified context of the five at 128,000 tokens, and dated Phase 0 evidence puts 44 percent
of measured primary documents above roughly 200,000 estimated tokens. Every filing in this
benchmark fitted it; a breadth run across 22 form strings will contain filings that do not. The
candidate with a 1,000,000-token context — Llama 4 Maverick — produced the shallowest parses in the
benchmark by a wide margin, five to seven nodes where others produced twenty-four to seventy-three.

So the choice is not simply "which parser is best". It is whether breadth validation should first
establish behaviour on filings that FIT, using the most reliable parser, or should immediately
confront the filings that do not, using the only parser that could hold them. That is a product
decision, and it is the one this phase stops at.
