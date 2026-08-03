# ADR-0007: Start retrieval with PostgreSQL full-text search and pgvector

STATUS: SUPERSEDED AS AN ACTIVE DECISION BY ADR-0017
DATE: 2026-08-01
SPRINT: 1

> **Forward note, added 2026-08-03. Nothing below this note has been edited.**
>
> There is no store to retrieve from and no summary corpus to index:
> `docs/adr/ADR-0017-delete-the-rejected-parser-and-application-persistence.md` deleted the
> persistence layer, and no summary has ever been produced. The reasoning below stands as history,
> and is RECONSIDERED rather than assumed when persistence is designed from measured model
> artifacts. The full retrospective is in ADR-0017.

## Context

Deep Analysis needs to locate relevant footnotes within an authorized corpus. The corpus for a
single session is small by search standards: one issuer, at most a few hundred filings, at most a
few thousand footnotes. Every retrieval is filtered by scope before ranking matters.

## Decision

Implement retrieval as hybrid search in PostgreSQL: full-text search for lexical matching and
pgvector for semantic similarity, combined by a ranking function. Do not deploy a separate search
cluster for the MVP.

## Alternatives Considered

OpenSearch from the start. Rejected: it adds a cluster to operate, secure, back up, and keep in
sync, to serve a per-session corpus of a few thousand documents. Scope filtering, not ranking, is
what makes retrieval correct here.

Vector-only retrieval. Rejected: exact identifier and concept-name matching is common in this
domain and lexical search handles it better.

## Consequences

One store for control plane and retrieval. Scope filters are SQL predicates on the same rows,
which makes a scope bypass a visible query defect rather than an index synchronization problem.
Ranking quality is bounded by what PostgreSQL offers, and embedding storage grows the database.

## Migration Impact

Retrieval is confined to `packages/retrieval` behind an interface, so replacing the backend does
not touch Deep Analysis logic. Scope filtering must be reimplemented in the new backend and
re-tested.

## Revisit Conditions

Revisit if measured retrieval latency exceeds the interactive budget, if recall proves inadequate
on the evaluation set, or if the corpus grows past the point where pgvector index maintenance
affects control-plane write performance.
