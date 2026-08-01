# Metric Normalization

IMPLEMENTATION STATUS: PLANNED (Sprint 6)
OWNER PACKAGES: `packages/metric_definitions`, `packages/financial_metrics`
DECISION RECORD: `docs/adr/ADR-0011-metric-definition-format.md`
DEFINITIONS: `metric_definitions/*.yaml`

## Two layers

Layer 1 is the immutable fact lake. Layer 2 is a curated, version-controlled mapping from a
business metric to an ordered list of accepted XBRL concepts.

The mapping is never auto-derived.

## Why per-period resolution, not per-issuer election

The intuitive optimization is to detect one revenue concept per issuer and reuse it. Verified
counter-evidence:

- Starbucks never uses `RevenueFromContractWithCustomerExcludingAssessedTax` at all.
- Gilead and Starbucks both have interior gaps in their otherwise-dominant revenue concept
  (Gilead 2013 to 2015, Starbucks 2014 to 2015).

Per-issuer election produces a series with silent holes in exactly those windows.

## The resolution algorithm

```
for each period in the requested range:
    candidates = facts where concept in metric.accepted_concepts
                       and duration_months in metric.allowed_duration_months
                       and unit in metric.allowed_units
                       and dimensions = {}          -- consolidated only
                       and period matches
    if candidates is empty:
        emit a missing observation with a reason
    else:
        chosen = select by (max filed_at, then min priority_rank)
        emit an observation citing chosen.fact_id
annotate comparability across the resulting series
```

Coalescing happens **per period**, which is what makes an issuer that switched concepts
mid-history produce a gap-free series.

## Priority order is financial accuracy

Costco's fiscal 2016 revenue growth is **2.2 percent** with `Revenues` ranked ahead of
`SalesRevenueNet`, and **4.4 percent** with the order reversed. Both are defensible readings of
the filing; they are not the same number.

Changing a rank therefore requires code review, an updated fixture, a changelog entry, and a
version bump, exactly as a code change would.

## Composed metrics

Some metrics have no single concept. `total_debt` sums declared components. A missing optional
component emits a comparability warning rather than being treated as zero, because zero and
unknown are different and the difference changes a leverage ratio.

## Where the model fits

The curated chain is the deterministic base. The model reconciles the extracted statement against
the filing's own rendered statement and proposes mapping corrections.

**A correction changes which fact is displayed. It never changes a fact's value.** The output is a
mapping decision plus reasoning, stored with provenance, so a wrong correction is auditable and
reversible rather than an unattributable bad number.

## Regression fixtures

Every definition names issuer fixtures whose concept usage is known to be awkward. A definition
change re-runs them. Costco fiscal 2016 is the canonical regression case for revenue.
