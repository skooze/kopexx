# Model Benchmark

IMPLEMENTATION STATUS: PLANNED (blocking gate before Phase 6)
DECISION RECORD: `docs/adr/ADR-0006-model-selection-by-benchmark.md`
GATES: `prompts/footnote-summary/v1.0.0/evaluation.yaml`

## Principle

No model is selected until measured on a representative footnote corpus. The strongest available
model is not automatically right for a bounded, highly structured task; that is an empirical
question about numeric fidelity and instruction following.

Among models passing every gate, the **cheapest** is selected.

## Corpus construction

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
