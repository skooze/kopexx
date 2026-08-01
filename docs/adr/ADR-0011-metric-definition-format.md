# ADR-0011: Metric definitions are curated, version-controlled YAML

STATUS: ACCEPTED
DATE: 2026-08-01
SPRINT: 1

## Context

The same financial concept is tagged differently by different issuers and by the same issuer over
time. Verified examples: Starbucks never uses
`RevenueFromContractWithCustomerExcludingAssessedTax` at all; Gilead and Starbucks both have
interior gaps in their dominant revenue concept. Any heuristic that detects one revenue concept
per issuer and reuses it produces silent holes in the series.

Concept priority is not a configuration preference. Ranking `SalesRevenueNet` ahead of
`Revenues` changes Costco's reported fiscal 2016 revenue growth from 2.2 percent to 4.4 percent.
That is a financial-accuracy artifact.

## Decision

Metric definitions live in version-controlled YAML under `metric_definitions/`. Each definition
declares accepted concepts in explicit priority order, allowed units, expected statement,
instant-or-duration semantics, expected duration buckets, sign normalization, industry and issuer
overrides, and explicitly excluded concepts.

Resolution is per issuer and per period: for each period, take facts matching any accepted
concept, filter by duration and unit, then select by most recently filed and then by priority
rank. Never elect one permanent concept for an issuer.

Changing a definition requires code review, updated test fixtures, a changelog entry, and a
version bump.

## Alternatives Considered

Hard-code the mapping in Python. Rejected: it makes a financial-accuracy artifact invisible to
review and impossible to diff meaningfully.

Derive the mapping from the data automatically. Rejected: the failure mode is silent, and the
verified counter-examples show per-issuer election is exactly the wrong shape.

A database table as the source of truth. Rejected: it loses code review and git history, which
are the controls that make a priority change safe.

## Consequences

Metric changes are reviewable and their effect on reported figures is testable against fixtures.
A YAML loader and validator are required, and the definitions must be regression-tested against
known issuers whose concept usage changes mid-history.

## Migration Impact

Definitions are versioned, so a change supersedes rather than rewrites, and derived metrics record
the definition version that produced them.

## Revisit Conditions

Revisit if the number of issuer-specific overrides grows to the point where the curated list is no
longer maintainable, which would indicate the concept model needs a different structure.
