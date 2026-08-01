# Derived Metrics

IMPLEMENTATION STATUS: PLANNED (Phase 3)
OWNER PACKAGE: `packages/financial_metrics`

Derived metrics are computed deterministically from normalized facts. The language model may
explain a calculation; it is never the calculator.

Every derived value stores: `formula_version`, `input_fact_ids`, `input_periods`, `result`,
`unit`, `warnings`, `comparability_status`, `calculated_at`.

Missing-data behaviour is uniform: if any required input is missing, the result is **null with a
reason**, never zero and never interpolated.

| Metric | Formula | Unit | Period | Sector limits and warnings |
|---|---|---|---|---|
| Revenue growth (annual) | `(rev[t] - rev[t-1]) / abs(rev[t-1])` | percent | duration | Null when prior is zero. Warns across a 53-week year |
| Revenue growth (quarterly) | `(rev[q] - rev[q-4]) / abs(rev[q-4])` | percent | duration | Year-over-year, not sequential, to avoid seasonality |
| Gross margin | `(revenue - cost_of_revenue) / revenue` | percent | duration | Not meaningful for banks and insurers |
| Operating margin | `operating_income / revenue` | percent | duration | Warns when operating income is a company extension concept |
| Net margin | `net_income / revenue` | percent | duration | Warns when net income rank 1 and 2 are mixed |
| Effective tax rate | `income_tax_expense / pretax_income` | percent | duration | Null when pretax income is negative or near zero |
| Free cash flow | `operating_cash_flow - capital_expenditures` | USD | duration | Capex is sign-normalized to positive magnitude first |
| Free cash flow margin | `free_cash_flow / revenue` | percent | duration | Inherits both inputs' warnings |
| Current ratio | `current_assets / current_liabilities` | ratio | instant | Not meaningful for banks; suppressed for SIC 6000-6199 |
| Quick ratio | `(current_assets - inventory) / current_liabilities` | ratio | instant | Null when inventory is not disclosed rather than assuming zero |
| Net debt | `total_debt - cash_and_equivalents - marketable_securities` | USD | instant | Warns when a debt component was undisclosed |
| Debt to equity | `total_debt / stockholders_equity` | ratio | instant | Null when equity is negative; that is a real state, not an error |
| Debt to EBITDA | `total_debt / ebitda` | ratio | mixed | EBITDA is itself derived; warns as an approximation |
| Return on assets | `net_income / average_total_assets` | percent | mixed | Average of opening and closing instants |
| Return on equity | `net_income / average_stockholders_equity` | percent | mixed | Null when average equity is negative |
| Share count change | `(shares[t] - shares[t-1]) / shares[t-1]` | percent | instant | Uses period-end shares, not weighted average |
| Dilution | `(diluted_shares - basic_shares) / basic_shares` | percent | duration | Weighted-average shares only |
| SBC as percent of revenue | `stock_based_compensation / revenue` | percent | duration | |
| Cash conversion | `operating_cash_flow / net_income` | ratio | duration | Null when net income is negative or near zero |
| Receivables growth | `(ar[t] - ar[t-1]) / ar[t-1]` | percent | instant | |
| Inventory growth | `(inv[t] - inv[t-1]) / inv[t-1]` | percent | instant | Null when the issuer holds no inventory |
| Capex growth | `(capex[t] - capex[t-1]) / capex[t-1]` | percent | duration | |
| Segment concentration | `max(segment_revenue) / total_segment_revenue` | percent | duration | Requires dimensional facts, which companyfacts omits |
| Debt maturity concentration | `debt_due_within_12m / total_debt` | percent | instant | Sourced from the debt footnote maturity table |

## Near-zero denominators

A ratio whose denominator is within a configured epsilon of zero returns null with reason
`denominator_near_zero`. Returning a very large number would be arithmetically correct and
analytically useless.

## Comparability status

```
COMPARABLE                  inputs share a consistent basis across periods
WARN_53_WEEK                the period or its comparator is a 53-week year
WARN_MIXED_CONCEPT          the series drew on different concept ranks
WARN_RESTATED               an input was restated in a later filing
WARN_MISSING_COMPONENT      a composed input lacked an optional component
NOT_COMPARABLE              a transition period or a fiscal-year-end change intervenes
```

## Tests

Every metric has: a positive case with known inputs and expected output; a missing-input case
asserting null with a reason; a near-zero denominator case; a sector-limit case where applicable;
and a provenance case asserting `input_fact_ids` resolves to real facts.
