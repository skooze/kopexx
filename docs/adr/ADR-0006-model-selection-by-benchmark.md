# ADR-0006: Select models by measured benchmark, not by reputation

STATUS: ACCEPTED
DATE: 2026-08-01
SPRINT: 1

## Context

An earlier version of this architecture proposed a tiered model plan with a headline cost figure.
That figure was computed on the wrong unit of work: it assumed 58 summarization jobs per Apple
10-K where the correct number is 13 (ADR-0005). Any cost conclusion drawn from it is invalid.

Separately, the strongest available model is not automatically the right one for a bounded,
highly structured task like summarizing a single footnote. That is an empirical question about
numeric fidelity and instruction following, not a question about general capability.

## Decision

No model is selected until it has been measured on a representative footnote corpus. Two model
classes are defined by capability requirement rather than by name: a standard model for offline
per-footnote summarization, and an analysis model for user-triggered Deep Analysis.

Production gates a model must pass before selection: numeric fidelity at or above 99.5 percent,
structured output validity at or above 99 percent, zero omitted footnotes, and citation accuracy
at or above 95 percent. Among models that pass every gate, the cheapest is selected.

The provider catalog, model identifiers, context limits, batch availability, and prices must be
verified in the target region before any cost commitment. That verification is a blocking gate
before Phase 6.

## Alternatives Considered

Select the strongest model for everything. Rejected: it optimizes a variable that is not
constrained while ignoring the ones that are.

Select from published general benchmarks. Rejected: none measures numeric fidelity on financial
footnotes, which is the property that matters here.

## Consequences

Model selection is deferred until evidence exists, which delays a cost commitment. The benchmark
corpus and its gold labels are real work. In exchange the choice is defensible and re-runnable
when a new model appears, and model swaps become configuration changes.

## Migration Impact

None at selection time. Changing models later supersedes affected summaries rather than
overwriting them.

## Revisit Conditions

Re-run the benchmark whenever a candidate model is added or deprecated, whenever prompt version
changes materially, and on a scheduled cadence to detect provider-side drift.
