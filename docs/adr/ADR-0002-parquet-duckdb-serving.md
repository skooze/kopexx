# ADR-0002: Serve analytics from immutable versioned Parquet queried by in-process DuckDB

STATUS: SUPERSEDED AS AN ACTIVE DECISION BY ADR-0017
DATE: 2026-08-01
SPRINT: 1

> **Forward note, added 2026-08-03. Nothing below this note has been edited.**
>
> There is no fact lake and no serving layer to publish:
> `docs/adr/ADR-0017-delete-the-rejected-parser-and-application-persistence.md` deleted the numeric
> pipeline and the application persistence layer. The DuckDB lock finding and the reasoning below
> stand as history, and are RECONSIDERED rather than assumed when persistence is designed from
> measured model artifacts. The full retrospective is in ADR-0017.

## Context

The serving path must answer chart and screening queries over tens of millions of fact rows while
an ingestion process is continuously writing new data.

DuckDB is the natural analytical engine for this shape of workload. However, a DuckDB database
file is single-writer, and a reader cannot open a file that another process holds read-write even
with `read_only=True`; the connection attempt fails with a lock conflict rather than degrading.
An architecture in which the API opens the same `.duckdb` file the ingester writes would
therefore fail intermittently under exactly the conditions it is meant to serve.

## Decision

Treat Parquet on object storage as the system of record for the fact lake and for serving
datasets. Publish immutable, versioned dataset directories. Advertise the current version through
a pointer row in PostgreSQL and flip that pointer atomically after a new version is verified.

API workers open `duckdb.connect(":memory:")` per worker and read the published Parquet
directory. No DuckDB database file is ever shared between processes, so no file lock exists.

## Alternatives Considered

A shared DuckDB file with read-only connections. Rejected: verified to fail at connect time while
a writer holds the file.

PostgreSQL for the fact lake. Rejected: columnar scans across tens of millions of rows are the
dominant read pattern, and PostgreSQL is retained for the control plane where transactional
integrity matters instead.

A managed warehouse. Rejected for the MVP as unnecessary infrastructure for a single-machine
workload; the Parquet layout does not preclude it later.

## Consequences

Readers never block writers and never contend for a lock. Publication is atomic and instantly
reversible by flipping the pointer back. Storage cost rises because multiple dataset versions
coexist, and a retention policy is required. Real-time freshness is bounded by publication
cadence rather than by write latency.

## Migration Impact

Moving to a warehouse later means changing the query layer while retaining the Parquet layout.

## Revisit Conditions

Revisit if publication cadence proves too slow for product requirements, if dataset size makes
full-version publication impractical, or if concurrent multi-writer ingestion becomes necessary.
