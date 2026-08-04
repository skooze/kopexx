# PHASE 2.1 — Model-directed multipart filing parsing

STATUS: IMPLEMENTED AND PUBLISHED. THE FIVE-MODEL PROOF IS BLOCKED ON AN EXTERNAL CREDENTIAL EVENT.
DATE: 2026-08-03
BASELINE: `be446fe` (Phase 2)
DECISION RECORD: [ADR-0020](../adr/ADR-0020-model-directed-multipart-parsing.md)
BUILDS ON: [ADR-0016](../adr/ADR-0016-corpus-first-model-first-architecture.md),
[ADR-0019](../adr/ADR-0019-parser-review-application-over-a-framework.md)

---

## What this phase was for

Phase 2 sent a complete filing intact and then expected the complete parsed artifact back in **one
provider response**. Thirty preserved invocations measured what that assumption costs:

```
three of the five candidates cap output at 8,000 tokens
four of the benchmark's five truncation failures were that cap
the DEEPEST parse produced — 73 nodes, 69 of 72 source references resolved — was itself
    truncated at 8,000 tokens, with no way to finish it
```

Every candidate held every benchmark filing comfortably in its CONTEXT. The binding constraint was
never the input; it was the output, and it was a constraint on a **response**, not on a **parse**.

That assumption is withdrawn. One logical filing parse may use many provider responses.

---

## 1. What was built

One new package, four extended, and **no new runtime dependency**.

```
packages/multipart                 the model-directed envelopes (plan, part, replan, amendment),
                                   their generic structural validation, safe carriage of a
                                   model-created identifier, and mechanical assembly

packages/evaluation_store          + tasks.py, durable task records with dependencies, billable
                                     identity, attempts and evidence
                                   + queue_states.py, a THIRD state machine — never derived from
                                     the execution or review machines
                                   + task persistence, a fingerprinted read cache, restart
                                     interruption, resume, cancellation, per-task evidence

packages/orchestrator              + multipart_service.py, the scheduler and executor
                                   + briefs.py, the synthetic YAML brief for one invocation
                                   + sizing.py, the cap, the target and the headroom between them
                                   + a three-ceiling spend journal: cumulative, phase, filing run

packages/review_api                + nine routes for the multipart surface
packages/review_web                + multipart_view.py, hierarchy, per-call review, assembled index

packages/coverage_validation       + a supplied envelope, so a PART is not judged as a whole filing
packages/llm_gateway               + eight identifier keys that must be quoted, one boundary
                                     narrowing (section 5 below)
packages/model_catalog             + emits_reasoning_before_answer, from measured Phase 2 evidence
packages/storage                   + fingerprint(), so a parsed manifest can be cached safely

prompts/parser/                    six new IMMUTABLE families; the two single-response versions
                                   are untouched
```

---

## 2. The protocol

```
intact filing
  ->  model-created parse plan
  ->  model-created parts
  ->  model-created subparts when needed
  ->  model-created reconciliation
  ->  mechanically assembled filing parse
  ->  human review
```

Ten task types, one of which is billable only when a model is actually invoked:

```
SOURCE_PREFLIGHT   PLAN_PARSE   PARSE_PART   PLAN_SUBPARTS   PARSE_SUBPART
REPLAN_TRUNCATED_PART   RECONCILE_PARSE   GAP_REPAIR   FORMAT_REPAIR
VALIDATE_ASSEMBLY   READY_FOR_REVIEW
```

Fourteen durable queue states, with `TRUNCATED` terminal by construction so a truncated attempt can
never be reopened, and `FAILED` and `INTERRUPTED` reopening only through an explicit user action
that takes a new reservation.

**Three things the backend never does.** It never decides what a part is. It never asks a model to
continue an interrupted response. It never sends a slice of a filing.

---

## 3. What the five real models actually did

**COMPLETE. ALL FIVE CANDIDATES RAN THE MULTIPART PROTOCOL AGAINST A PRESERVED FILING, AND BOTH
MULTIMODAL CANDIDATES ALSO RAN AN IMAGE-BEARING ONE.** Seven runs, `USD 2.603827` of measured
Bedrock spend, every request and every response preserved.

```
PRIMARY      3M CO  10-K405  1996-03-11   CIK 0000066740   0000066740-96-000005
             146,471 bytes, one non-addressable complete submission, sent intact on every call

MULTIMODAL   Macy's, Inc.  10-Q/A  2025-09-12   CIK 0000794367   0000794367-25-000156
             includes m-20250802_g1.gif, 24,744 bytes,
             sha256 a2ebf882cc994767ee862dd6c7b786cf0c3476702ae7afcd5f9c7ae45ce9cc63
```

**NO SEC TRAFFIC WAS GENERATED.** Every run used `ALLOW_SEC_FETCH=false` and every source member
resolved from local preserved storage.

### The five candidates on the 3M filing

| model | region | plan parts | tasks | assembly | parts terminal | nodes | references | USD |
|---|---|---:|---:|---|---|---:|---|---|
| GPT OSS 120B | us-east-1 | 24 | 51 | RECONCILIATION_UNRESOLVED | 47/47 | 214 | 352/364 | 0.36991305 |
| NVIDIA Nemotron 3 Super 120B | us-east-1 | 28 | 102 | INCOMPLETE_WORK | 67/79 | 180 | 212/229 | 0.57913415 |
| Qwen3 235B A22B | us-west-2 | 12 | 58 | INCOMPLETE_WORK | 36/44 | 119 | 114/120 | 0.58685044 |
| Llama 4 Maverick | us-east-1 | 5 | 14 | RECONCILIATION_UNRESOLVED | 11/11 | 24 | 23/24 | 0.13184449 |
| Qwen3 VL 235B | us-east-1 | 27 | 47 | INCOMPLETE_WORK | 20/45 | 71 | 116/120 | 0.55640053 |

**EVERY CANDIDATE PRODUCED A SCHEDULABLE PLAN AND NAMED EVERY PART ITSELF.** The backend supplied
no part identifier, title, type, boundary or ordering in any of the seven runs. Plan sizes for one
identical filing ranged from 5 parts to 28 — a 5.6x spread, from the same bytes, on the same day.

**A STATUS IS NOT A SCORE.** `INCOMPLETE_WORK` means scheduled work did not reach a terminal state;
`RECONCILIATION_UNRESOLVED` means the last reconciliation returned `plan_complete: false`. Neither
is a judgement about parse quality, and the difference between two rows above is not evidence that
one model parsed better than another. Every run carries `human_review_required: true` and
`review_state: EVALUATION`. **No parser has been selected, ranked or promoted.**

### Each candidate exercised a different path, which is what the proof was for

```
GPT OSS 120B        THE RECONCILIATION LOOP. Three cycles, every one returning plan_complete:
                    false, closing on the orchestrator's cycle limit rather than on the model
                    being satisfied. Cycle 1 named five missing items and asked for four
                    replacement parts; cycle 3 asked for ten more. 10 model-created subparts.
                    Zero unreadable responses, zero truncation, 51 of 51 tasks SUCCEEDED.

Nemotron 3 Super    THE FORMAT-REPAIR PATH. 20 unreadable responses out of 67 part calls, most
                    from a colon-space inside an unquoted plain scalar -- "State of
                    Incorporation: Delaware". 20 repair tasks, 8 attempted, exactly ONE
                    returning a readable envelope. Largest single response of any candidate at
                    18,303 tokens against a 32,000 cap.

Qwen3 235B A22B     THE TRUNCATION PATH. 7 responses cut at exactly its 8,000-token cap, each
                    preserved, marked TRUNCATED and NEVER continued; 6 replanning calls then
                    divided the WHOLE original part into 30 model-created subparts. This is the
                    one run that proves the blind-continuation prohibition under real load.

Llama 4 Maverick    NONE OF THEM, AND THE SHALLOWEST OUTPUT. A 5-part plan, 24 nodes, a largest
                    single response of 909 tokens against an 8,000 cap. No truncation, no
                    repair, no subparts. It also cost the least, by a factor of four.

Qwen3 VL 235B       THE FILING BUDGET. 26 tasks INTERRUPTED when the run reached its own
                    USD 0.60 ceiling before any reconciliation cycle ran -- which is the
                    ceiling doing exactly what it exists to do, on the most expensive candidate
                    per token of the five.
```

### The image-bearing proof

Both multimodal candidates received the filed GIF **intact, on every call**, alongside the complete
text source set:

| model | plan parts | tasks | assembly | parts terminal | nodes | references | parts citing the image | USD |
|---|---:|---:|---|---|---:|---|---:|---|
| Llama 4 Maverick | 7 | 16 | RECONCILIATION_UNRESOLVED | 12/12 | 30 | 14/30 | **3** | 0.08666540 |
| Qwen3 VL 235B | 7 | 20 | RECONCILIATION_UNRESOLVED | 14/14 | 88 | 82/89 | **0** | 0.29301922 |

Both runs record `image_coverage.analysed: true`, `submitted_to_parser: true`, and the image's
SHA-256. **The transport is proved for both. What each model DID with the image differs**, and that
difference is recorded as a measurement, not as a ranking.

### The finding that outranks every number above

**`table_count` IS ZERO IN ALL SEVEN RUNS.**

Not one of the five candidates emitted a structured table from a financial filing, on either the
1996 10-K405 or the 2025 10-Q/A. Tabular material was carried as node content or as a source quote
instead. Nothing in this phase asked for a table structure and no prompt names one, so this is not
a compliance failure — it is a measured fact about what these models produce unprompted, and it is
the most important open question this proof leaves behind.

### What the numeric validator found, on the two deepest parses

```
GPT OSS 120B        339 of 340 reported numbers occur verbatim in the preserved bytes
Nemotron 3 Super    317 of 317 reported numbers occur verbatim in the preserved bytes
```

**THAT IS NOT A CORRECTNESS RESULT.** It proves a number appears in the filing. It does not prove
the number was attached to the right node, the right period, or the right line item. Correctness is
a human judgement made in the review UI, and no human has made it: `review_history` is empty on
every one of the seven runs.

### The comparison with the single-response protocol, stated without ranking

On **the same filing and the same model**, Phase 2 measured `GPT OSS 120B` producing **25 nodes and
21 of 23 references resolved** in one 4,033-token response. Under multipart the same model produced
**214 nodes and 352 of 364 references**, across 51 calls, for `USD 0.36991305` instead of
`USD 0.0198`.

That is roughly 8.6x the nodes for roughly 19x the cost. It is a factual observation about two
protocols on one filing with one model. It is not a verdict about either protocol, and **the
single-response path remains runnable precisely so the two can keep being compared.**

### What the sizing policy got right, measured

Only one candidate ever hit its cap: `Qwen3 235B A22B`, 7 times, at exactly 8,000 tokens. Nemotron
reached 18,303 tokens against a 32,000 cap and never truncated. The Phase 1 empty-answer failure —
reasoning consuming the whole budget and returning no text — did not recur in any of the seven
runs.

---

## 4. Six defects this phase found, five of them by running real models

### A parse whose plan never returned reported `MECHANICALLY_ASSEMBLED`

Found by a live run, not by an assertion. When a planning call failed, the parse had zero parts and
zero *expected* parts. `terminal < parts_expected` was `0 < 0`, which is false, so a filing that
nothing had been produced for reported successful mechanical assembly.

**An emptiness that satisfies every count is the most dangerous shape a status check can have.**
`parts_expected` now comes from the PLAN rather than from the number of tasks that happen to exist,
and both "no readable plan" and "no parts at all" are checked explicitly. Four tests lock it,
including a mutation proof that a genuinely assembled parse is still reported as one.

### The content boundary could not express a request the protocol requires

`MARKDOWN_FENCE` was among the violations that still applied to a document proven to parse as one
YAML 1.2 mapping. That was correct about a *fenced document* and wrong about the *check*, which is
a textual search for three backticks at the start of any line — and a YAML literal block scalar can
contain such a line.

Two real request shapes must: the **replanning** call carries the exact truncated response as
evidence, and the **format-repair** call carries the exact malformed response, which is very often
malformed *because* it is fenced. Under the old rule neither request could be constructed at all.

The narrowing is **demonstrated rather than argued**: `parse_yaml` raises on both
` ```yaml\nkey: value\n``` ` and ` ```\nkey: value\n``` `, so a fence-wrapped document cannot reach
that branch. Three mutation proofs assert that a fenced document and a JSON document are both still
refused, and that JSON — a YAML subset, which therefore does reach the branch — still fails.

---

### The serializer wrote YAML this repository could not read back

A 1996 10-K405 table quoted by a parsing model contained `U+0085 NEXT LINE`. `_coerce` forces style
`|` on prose, which bypasses the emitter's own scalar analysis — the analysis that would have
refused a block scalar for that string. The reader counts `U+0085`, `U+2028` and `U+2029` as line
breaks, so the character came back as a newline. **Silently**, a preserved quote stopped matching
the bytes it cited; **loudly**, an assembly this repository had just written became one it could
not load. A string carrying any character a block scalar cannot return unchanged is now
double-quoted. Tab and newline stay out of that set deliberately: EDGAR text tables are made of
them, and an ordinary table is still a readable block scalar. Swept over every code point through
U+10FFF.

### A resumed parse could not reach review

A restart parks BOTH the tasks and the child job in `INTERRUPTED`. `resume` reopened the tasks;
nothing reopened the job. A real run then drove to 47 of 47 parts terminal, 214 nodes and 352 of
364 references resolved — and had nowhere to go, because `INTERRUPTED` was terminal in the
execution machine. It now reopens to `RUNNING` through an explicit user action and nothing else,
the same shape `TaskState.INTERRUPTED -> READY` already had one level down.
`mark_interrupted_jobs` still only ever moves work INTO the state, so a restart still re-invokes
nothing.

### A repaired part never reached the index, so the assembly reported a FALSE EMPTY

A model returned a part response that would not parse. The format repair succeeded and produced a
readable envelope with two nodes and the same model-created identifier. **The index carried the
ORIGINAL row** — `node_count: 0`, empty title, empty coverage summary — and reported the part
terminal. Content that exists, reported as absent: the inverse of the failure mode this project
guards against, and exactly as untrue.

The design intent was right and is unchanged — a repaired artifact is a SEPARATE artifact and the
original is never replaced or rewritten. What was missing is that the index never looked at the
repair. Each row now resolves to the artifact that holds the content, names BOTH task ids, and sums
what both calls cost. Re-deriving the affected run: **178 to 180 nodes, 210/227 to 212/229
references, `USD 0.57913415` unchanged.**

### A format repair could itself be repaired

`max_format_repairs_per_artifact` counted repairs of a GIVEN task, so an unreadable repair became a
new artifact with its own allowance — one repair per link rather than one per artifact. A real run
produced a `FORMAT_REPAIR` whose parent was a `FORMAT_REPAIR`. A repair is never repaired now; the
unreadable document is preserved and reported.

---

## 5. What this phase did NOT do

```
no breadth run across the 22 form strings   no summary artifact
no image-model call                         no chat session
no application database                     no Redis
no parser selected, ranked or promoted      no bulk background population
no prompt caching enabled                   nothing deployed
no single-response rerun                    no historical result rewritten
```

The five candidates remain equally available for user-directed testing. The single-response
protocol remains runnable, and the thirty preserved Phase 2 runs are untouched: all thirty were
re-opened over a real loopback HTTP socket after this work and every one still renders, with its
raw, parsed and side-by-side views intact.

**AND, AFTER SEVEN REAL RUNS, THESE REMAIN UNMEASURED:**

```
CORRECTNESS             No human has reviewed any of the seven parses. review_history is empty on
                        every one and review_state is EVALUATION. Validation proves a citation
                        resolves in the preserved bytes and a number occurs there. It proves
                        nothing about whether a node's title, type, boundary or period is right.

REPEAT-RUN VARIABILITY  No filing was parsed twice by the same model. A rerun is billable and
                        none was authorized. Nothing here says a second run would produce the
                        same plan, the same part count, or the same nodes.

TABLE STRUCTURE         table_count is 0 in all seven runs. Whether these models CAN emit a
                        structured table when asked is untested; no prompt in this phase asks.

R-21, MATERIALLY SIZED  Both proof filings fit every candidate's context intact. Whether a large
MODERN FILINGS          modern filing does is untouched, by construction.

A CORPUS DENOMINATOR    Two filings is not a corpus. Nothing in docs/llm/cost-model.md
                        extrapolates to 613 filings, and the 5.6x spread in plan size between
                        candidates on ONE filing is a warning against trying.
```

---

## 6. Prompt caching: investigated, not available

Model-directed multipart re-sends the intact filing on every semantic call, so caching would have
mattered a great deal. It is not available:

```
the live control plane exposes NO caching field on ANY of the 119 models visible to this account
the AWS prompt-caching documentation lists Claude, GPT-5.6 and Amazon Nova
NONE of the five approved candidates appears on that list
```

Full evidence, including what could NOT be verified and why no live probe was run:
[docs/llm/prompt-caching-investigation.md](../llm/prompt-caching-investigation.md).

---

## 7. The blocker that occurred, and how it was cleared

**The AWS IAM Identity Center session expired mid-run, at `2026-08-04T02:18:20Z`**, part way
through the first proof attempt.

```
what failed        every Bedrock invocation after that moment, with
                   "TokenRetrievalError: Token has expired and refresh failed"
what it is not     a provider fault, a permission fault, a code fault or a cost-ceiling refusal
how it presented   the orchestrator recorded it as a NON-RETRYABLE provider error, marked the
                   task FAILED, wrote the reason, and stopped. Nothing was retried, nothing was
                   substituted, and no filing lost work that had succeeded.
how it cleared     `aws sso login` on the host, by the user. The proof then ran to completion.
```

**Eleven jobs recorded nothing but that failure.** Their assemblies were written before the
`plan_available` fix in section 4 existed, so each reported `MECHANICALLY_ASSEMBLED` with zero
parts — eleven live instances of the exact false-complete that fix removed. Every one has been
re-derived from its preserved tasks with the corrected code and now reports `INCOMPLETE_WORK`. **No
model was invoked and nothing was bought**: `USD 0` on all eleven. The preserved requests, responses
and error records were not touched.

### Two operating facts this produced, recorded so they are not rediscovered

**A RESTART PARKS BOTH LEVELS, AND BOTH MUST REOPEN.** The tasks AND the child job go to
`INTERRUPTED`. Reopening only the tasks left a completed parse terminal with nowhere to go — 47 of
47 parts done and unreachable from the review UI. Section 4 records the fix.

**TWO PROOF PROCESSES AGAINST ONE STORE COLLIDE.** The host tooling calls `mark_interrupted_tasks()`
when it builds the application, which is right on a restart and wrong when a second process starts
while the first is still running: 46 live tasks of the Nemotron run were parked mid-flight. Nothing
was lost and nothing was double-charged — `resume` re-armed them and the run completed — but the
evaluation store has **no cross-process lock**, and Phase 2.1 does not add one. Proof runs are
serialized by the operator.

---

## 8. Risks

| ID | Movement |
|---|---|
| R-09 | Unit economics. **First multipart per-call figures exist** — USD 0.0071 to 0.0082 per call for one candidate on one filing. A 24-part plan implies roughly USD 0.19 for that filing against USD 0.0078 for the single-response attempt. Multipart costs more per filing and buys coverage; how much more, across candidates, is what the blocked runs measure. |
| R-21 | No candidate accepts a materially sized modern filing intact. **UNCHANGED and still OPEN.** Multipart addresses the OUTPUT limit and nothing about the INPUT limit. |
| R-23 | Repeat-run variability. **STILL NOT MEASURED.** No filing has been parsed twice by the same model under either protocol. |
| R-24 | Character-ratio token estimates. **One more data point**: 40,552 estimated against 36,414 measured on the planning call, a ratio of 1.11 — over-counting, which is the safe direction. |
| R-33 | The capability snapshot goes stale silently. **OPEN.** It was amended additively with one measured field and not regenerated. |
| R-34 | Discovery ran under a broad administrator role. **OPEN.** A least-privilege Bedrock policy is still required. |
| R-35 | **NEW.** An expiring SSO session interrupts a long multipart run. The interruption is safe — completed parts are kept, nothing is retried, and resume is an explicit action — but a run spanning more than the session lifetime will stop partway. |

---

## 9. The decision this phase stops at

Unchanged from Phase 2, and deliberately so:

```
Which parser and prompt version should advance to breadth validation across all 22 substantive
10-K/10-Q-family form strings?
```

**Nothing here selects, ranks, promotes or eliminates a parser.** Phase 2.1 exists to test whether a
model-directed multipart protocol changes the picture Phase 2 measured. On the partial evidence it
changes it materially for at least one candidate — but four candidates have not run, and a
comparison drawn from one is exactly the reasoning `rules.md` section 21 rule 14 forbids.
