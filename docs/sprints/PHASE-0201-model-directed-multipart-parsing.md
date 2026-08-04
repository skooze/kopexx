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

## 3. What a real model actually did

**PARTIAL EVIDENCE. FOUR OF THE FIVE CANDIDATES HAVE NOT YET RUN.** See section 7 for the blocker.

`GPT OSS 120B`, `us-east-1`, against the preserved **3M CO 10-K405 of 1996-03-11**,
`0000066740-96-000005`, 146,471 bytes, one non-addressable complete submission sent intact.

### The planning call

```
prompt              parser-multipart-plan@1
input tokens        36,414          output tokens   3,093
reasoning chars     3,569           stop reason     end_turn
latency             17,838 ms       cost            USD 0.00731790
plan validation     SCHEDULABLE, with one model-declared uncertainty item
```

**The model divided the filing into 24 parts and named every one of them itself**, in the filing's
own vocabulary. The backend supplied none of these words:

```
 1 cover-page                          13 item-10-directors-officers
 2 item-1-business                      14 item-11-executive-compensation
 3 item-2-properties                    15 item-12-security-ownership
 4 item-3-legal-proceedings             16 item-13-related-transactions
 5 item-4-submission-vote               17 item-14-exhibits
 6 item-5-market-price                  18 exhibit-11
 7 item-6-selected-financial-data       19 exhibit-12
 8 item-7-md&a                          20 exhibit-21
 9 item-8-financial-statements-index    21 exhibit-23
10 auditor-report                       22 exhibit-24
11 signatures                           23 exhibit-27-1995
12 item-9-accountants                   24 exhibit-27-1994
```

Its part TYPES are equally its own: `Filing Header`, `MD&A Narrative`, `Consent Document`,
`Power of Attorney Document`, `Financial Data Table`.

### The four part calls that completed before the blocker

| part | status | nodes | references resolved | output tokens | reasoning chars | ms | USD |
|---|---|---:|---|---:|---:|---:|---|
| `cover-page` | complete | 6 | 42/42 | 4,006 | 7,143 | 88,971 | 0.00815655 |
| `item-1-business` | complete | 9 | 9/9 | 3,416 | 4,410 | 27,926 | 0.00780405 |
| `item-2-properties` | complete | 2 | 2/2 | 2,313 | 8,305 | 39,300 | 0.00714000 |
| `item-3-legal-proceedings` | complete | 3 | 12/13 | 2,941 | 6,254 | 21,589 | 0.00751860 |

```
20 nodes and 65 of 66 source references resolved against the preserved bytes, from four parts
NO truncation: output ran 2,313 to 4,006 tokens against a target of 7,200 and a cap of 16,000
reasoning content ran 4,410 to 8,305 characters and was preserved SEPARATELY every time
```

### The one comparison this evidence supports, stated without ranking

Under the single-response protocol on **the same filing and the same model**, Phase 2 measured
**25 nodes and 21 of 23 references resolved** in one 4,033-token response. Under multipart, **four
parts of twenty-four** already produced 20 nodes and 65 of 66 references.

That is a factual observation about two protocols, not a verdict about a model, and it is a partial
observation: twenty parts of that plan have not run.

### What the sizing policy got right, measured

Every completed part landed between 2,313 and 4,006 visible tokens against a 7,200-token target,
and the reasoning content that would have competed with it — 4,410 to 8,305 characters — was
recorded separately. That is the Phase 1 empty-answer failure not happening at scale.

---

## 4. Two defects this phase found

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

## 7. The blocker, stated exactly

**The AWS IAM Identity Center session expired mid-run, at `2026-08-04T02:18:20Z`.**

```
what failed        every Bedrock invocation after that moment, with
                   "TokenRetrievalError: Token has expired and refresh failed"
what it is not     a provider fault, a permission fault, a code fault or a cost-ceiling refusal
how it presented   the orchestrator recorded it as a NON-RETRYABLE provider error on the planning
                   task, marked that task FAILED, wrote the reason, and stopped. Nothing was
                   retried, nothing was substituted, and no filing lost work that had succeeded.
what unblocks it   `aws sso login` on this host, which requires a browser authorization only the
                   user can complete
```

Runs affected: the four candidates after GPT OSS 120B on the primary proof filing, and the entire
multimodal proof.

**Everything that does not depend on it is complete**: the protocol, the queue, the cost controls,
the review surface, 1,234 hermetic tests, the documentation, and this record.

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
