# ADR-0003: PostgreSQL owns the control plane

STATUS: ACCEPTED
DATE: 2026-08-01
SPRINT: 1

## Context

The system has two very different kinds of state. Financial facts are append-only, enormous, and
read by columnar scan. Control-plane state is comparatively small, highly relational, mutable,
and requires transactional integrity: issuer identity with temporal validity, filing metadata,
canonical footnotes, summary versions, processing jobs, analysis sessions, and audit records.

Deep Analysis additionally requires retrieval over summaries, which needs full-text search and
vector similarity.

## Decision

PostgreSQL owns all control-plane state. It does not own the financial fact lake, which lives in
Parquet per ADR-0002. Retrieval begins with PostgreSQL full-text search plus pgvector rather than
a separate search cluster, per ADR-0007.

## Alternatives Considered

A document store for filing metadata. Rejected: the relationships between issuer, listing,
filing, footnote, summary, and session are the point, and referential integrity is the property
that prevents a summary from being attached to the wrong filing.

Splitting control-plane state across several stores by subsystem. Rejected as
architecture-by-accumulation; the operational cost of each additional datastore is real.

## Consequences

One well-understood transactional store with foreign keys, check constraints, and partial
indexes. Retrieval and control plane share a backup and recovery story. PostgreSQL must be sized
for the summary corpus and its embeddings.

## Migration Impact

Moving retrieval out later is contained to the retrieval package because scope filtering happens
in the query builder rather than in the store.

## Revisit Conditions

Revisit if summary volume makes pgvector recall or latency inadequate at the measured corpus
size, or if control-plane write throughput becomes a bottleneck.
