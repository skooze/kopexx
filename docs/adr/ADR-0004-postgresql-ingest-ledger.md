# ADR-0004: PostgreSQL owns the ingest ledger; SQLite is not introduced

STATUS: ACCEPTED
DATE: 2026-08-01
SPRINT: 1
SUPERSEDES: an earlier draft recommendation to use SQLite in WAL mode as a separate ingest ledger

## Context

An earlier version of this architecture proposed SQLite in write-ahead-logging mode as a
dedicated ingest ledger, on the reasoning that DuckDB's single-writer lock makes it unsuitable
for concurrent row-level upserts from many workers.

The premise is correct about DuckDB but the conclusion does not follow, because PostgreSQL is
already present in the architecture and handles concurrent upserts natively.

The decisive number is the ingest rate. SEC access is capped at a single-digit request rate
aggregated across all machines, so the ingest ledger sees on the order of ten writes per second
at absolute peak. That is three to four orders of magnitude below what a single PostgreSQL
instance sustains.

## Decision

PostgreSQL owns the ingest ledger. SQLite is not introduced.

## Alternatives Considered

SQLite in WAL mode as a separate ledger. Rejected: it adds a fourth datastore, a second backup
and recovery story, and a second migration tool, to solve a concurrency problem that does not
exist at ten writes per second. It would also place job state in a different store from the
filing metadata that job state refers to, making a foreign key impossible and permitting an
orphaned job row.

Keeping job state in Redis. Rejected: job state is authoritative, and rules.md forbids Redis
owning anything authoritative.

## Consequences

One fewer datastore to operate, back up, and migrate. Job state can carry real foreign keys to
filings and footnotes. Ingestion now requires PostgreSQL to be available, which is acceptable
because the control plane already does.

## Migration Impact

If this is reversed, job state must be extracted to a separate store and the foreign keys
replaced with application-level checks.

## Revisit Conditions

Revisit if measured ingest write rate exceeds roughly 5,000 writes per second sustained, or if a
deployment topology requires ingestion to proceed while PostgreSQL is unavailable. Both are
currently far outside the operating envelope.
