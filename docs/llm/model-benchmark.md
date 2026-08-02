# Summarization Model Benchmark

IMPLEMENTATION STATUS: smoke benchmark PLANNED (Sprint 5); full benchmark PLANNED (pre-backfill)
DECISION RECORD: `docs/adr/ADR-0006-model-selection-by-benchmark.md`
GATES: `prompts/footnote-summary/v1.0.0/evaluation.yaml`
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

```
PURPOSE     Prove the pipeline end to end and measure real cost per footnote.
CORPUS      The 13 canonical footnotes of Apple's FY2025 10-K, plus 2 deliberately hard
            cases: the largest note and a routine one-paragraph note.
LABELS      Figures, units, scales, periods, and signs extracted from the filed source
            programmatically, then reviewed once by a human. Not full gold labels.
CANDIDATES  At least 2, spanning 2 capability tiers.
```

Gates for tier 1 — deliberately narrower than production gates, because 15 footnotes cannot
establish a rate to three decimal places:

```
structured_output_validity    == 1.0     every response parses as one YAML 1.2 document
footnote_omission_rate        == 0.0     13 footnotes in, 13 summaries out
numeric_fidelity              == 1.0     on 15 items, any error is a real defect
unit_and_scale_fidelity       == 1.0
citation_resolvability        == 1.0     every cited source id exists and belongs to that note
boundary_violations           == 0       no prohibited format in either direction
```

Tier 1 also **measures and publishes**, replacing the placeholders in `docs/llm/cost-model.md`:
`T_src`, `T_tbl`, `T_out`, `R_retry`, observed `P_in` and `P_out`, cost per footnote, cost per
filing, and extrapolated cost per issuer history.

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
canonical_footnote_coverage      omission_rate                unsupported_claim_rate
numeric_fidelity                 date_fidelity                period_fidelity
unit_fidelity                    scale_fidelity               sign_fidelity
citation_precision               citation_recall              financial_relationship_accuracy
material_change_accuracy         accounting_policy_accuracy   risk_identification_recall
structured_output_validity       hallucination_rate           concision
readability                      latency_p50 / latency_p95    retry_rate
cost_per_footnote                cost_per_filing              human_review_rate
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

Every fixture records token counts across plain text, YAML, Markdown, JSON, and XML, per the
harness in `packages/llm_gateway/token_counter.py`. The production path selects plain text or YAML
regardless of the result, because the boundary is a correctness constraint. The measurement
quantifies the benefit and detects regression.

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
