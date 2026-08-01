# ADR-0009: Run ingestion and parsing on ECS Fargate, not Lambda

STATUS: PROVISIONAL — revisit before implementation in Stage 2 phase W-7
DATE: 2026-08-01
SPRINT: 1
STATUS CHANGED: Sprint 2 alignment review, from ACCEPTED to PROVISIONAL

> Taken in Sprint 1 with no deployable component and no measured workload shape. The choice
> between long-lived workers and event-driven functions depends on the summarization batch
> profile measured in Sprint 5, which did not exist when this was decided. Recorded as current
> intent and re-decided when W-7 begins. See ADR-0015.

## Context

Ingestion work is long-running and stateful in ways that matter. A full-history backfill runs for
hours under a rate limit. Parsing a large filing loads multi-megabyte documents. A DERA package is
gigabytes. The rate limiter must be shared across all concurrent workers, which requires a
coordination point rather than an unbounded fan-out of short-lived functions.

## Decision

Run ingestion, parsing, and summarization workers on ECS Fargate as long-lived services scaled by
queue depth. Use Lambda only for genuinely bounded, event-driven tasks such as reacting to a
publication event or a webhook.

Do not force long parsing jobs into Lambda for convenience.

## Alternatives Considered

Lambda for everything. Rejected: the execution time limit conflicts with multi-hour backfill,
package size limits conflict with the parsing dependency set, and unbounded concurrency is
actively harmful when the SEC rate limit is a shared global budget.

EC2 instances managed directly. Rejected: more operational burden than Fargate for no benefit at
this scale.

## Consequences

Workers can hold connections and in-process state across many filings, and rate-limit coordination
has a stable home. Cost is continuous rather than per-invocation, so scaling to zero requires
explicit configuration during idle periods.

## Migration Impact

Moving a workload to Lambda later requires it to be bounded and to acquire rate-limit tokens from
the shared bucket rather than assuming local state.

## Revisit Conditions

Revisit if a workload proves genuinely short and burst-shaped, or if idle cost becomes material
relative to total spend.
