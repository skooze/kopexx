# SPRINT-0002: DERA Mirror Execution and the Control-Plane Schema

STATUS: COMPLETE
DATE: 2026-08-01

> **Forward note, added 2026-08-03. Nothing below this note has been edited.** The SEC HTTP client
> survives unchanged in role. Deleted from the active tree on 2026-08-03: `packages/dera_notes` and
> the mirror script, `packages/persistence` and its 24 tables, `migrations/` including revision
> `0001_initial`, `alembic.ini` and `docker-compose.yml`. The mirrored DERA bytes under `var/dera/`
> are untouched, and no application database ever existed. Authoritative:
> `docs/adr/ADR-0017-delete-the-rejected-parser-and-application-persistence.md`.

## Objective

Discharge URGENT-01 by actually mirroring the SEC DERA datasets, which required building the SEC
HTTP client first. Then establish the PostgreSQL control-plane schema and its initial migration.
Also verify the YAML implementation against the project invariant.

Ordered this way because URGENT-01 has an external deadline that the schema does not.

## Scope

In scope: SEC HTTP client, live DERA mirror, download manifest, idempotency proof, PostgreSQL
schema, initial Alembic migration, migration tests, YAML verification, documentation
synchronization.

Out of scope: DERA TSV loading, filing discovery, the Redis distributed limiter.

## Requirements addressed

URGENT-01 in full. The YAML verification requirements. The database schema and migration
requirements.

## Plan versus outcome

Planned and delivered: everything above, with one exception below.

Planned and **not** delivered: applying the migration to a live PostgreSQL. This machine has no
PostgreSQL, and its Docker daemon cannot start containers. Recorded as a blocker, with the exact
failing commands, rather than worked around by weakening the schema to fit SQLite.

## URGENT-01: what actually happened

Authoritative listing:

```
https://www.sec.gov/data-research/sec-markets-data/financial-statement-notes-data-sets
```

Discovery found **78** packages: 66 quarterly (2009q1 through 2025q2) and 12 monthly
(2025_07 through 2026_06). URLs were scraped from the listing, never constructed. The three
irregular 2010 filenames confirmed present and handled: `2010q1_notes_1.zip`,
`2010q2_notes_0.zip`, `2010q3_notes_0.zip`.

**The deadline risk, confirmed live.** Quarterly coverage ends at 2025q2 while monthlies run
2025_07 through 2026_06. Twelve months of data currently have **no quarterly consolidation**, so
those twelve packages are the irreplaceable ones. They were mirrored first, in a separate run, in
74 seconds, before the bulk. Had SEC published 2025q3 and deleted 2025_07 first, that month would
have been lost permanently.

Run 1a, monthlies only:

```
$ SEC_USER_AGENT="..." python scripts/mirror_dera.py --only-monthly \
      --manifest var/dera/manifest_monthly.json
discovered 12 packages (0 quarterly, 12 monthly); 0 already held, 12 pending
...
discovered: 12   downloaded: 12   already present: 0   failed: 0
bytes stored: 2,145,477,071 (2.00 GiB)
exit 0, 74 seconds
```

Run 1b, everything:

```
$ SEC_USER_AGENT="..." python scripts/mirror_dera.py
discovered: 78   downloaded: 66   already present: 12   failed: 0
persisted total: 78
bytes stored: 27,228,877,737 (25.36 GiB)
exit 0
```

Run 2, idempotency:

```
$ SEC_USER_AGENT="..." python scripts/mirror_dera.py
discovered 78 packages (66 quarterly, 12 monthly); 78 already held, 0 pending
discovered: 78   downloaded: 0   already present: 78   failed: 0
bytes stored: 27,228,877,737 (25.36 GiB)
exit 0, 82 seconds, 0 download attempts
```

Run 2 re-hashed all 78 files on disk rather than trusting the ledger, so idempotency is proven by
content address rather than by a bookkeeping flag.

Reconciliation: 78 discovered, 78 persisted, 0 failed. 78 unique SHA-256 values, so no package was
double-counted. Every row has `hash_validated: true` and `zip_validated: true`. The stored byte
total is identical to the independent HEAD size probe taken before any download.

Zero throttle events across all three runs.

## Files created

```
packages/sec_client/client.py                          SEC HTTP client
packages/persistence/__init__.py                       public interface
packages/persistence/base.py                           declarative base, naming convention
packages/persistence/models.py                         24 tables
migrations/env.py                                      URL from DATABASE_URL, not alembic.ini
migrations/versions/0001_initial_control_plane_schema.py
alembic.ini
scripts/generate_initial_migration.py
tests/unit/test_sec_http_client.py                     15 tests
tests/unit/test_migrations.py                          14 tests
var/dera/manifest.json                                 78-package manifest
var/dera/ledger.json                                   78-entry mirror ledger
var/dera/packages/{monthly,quarterly}/*.zip            78 packages, 25.36 GiB
```

## Files modified

```
packages/sec_client/__init__.py        export SecHttpClient, FetchResult
packages/llm_gateway/yaml_parser.py    pre-parse alias and anchor budget
tests/unit/test_yaml_parser.py         6 tests added
scripts/mirror_dera.py                 rewritten from the Sprint 1 placeholder
roadmap.md techspecs.md CHANGELOG.md   synchronized
docs/adr/ADR-0013-...md                YAML parser pinned; alias bound documented
docs/data-dictionary/README.md         schema now IMPLEMENTED
docs/sec/dera-notes.md                 mirror EXECUTED
docs/runbooks/dera-mirror.md           live run and idempotency recorded
```

## Schema changes

24 tables, 36 indexes, 93 constraints. Enforcement worth noting:

- `xbrl_fact` carries a BEFORE UPDATE trigger rejecting any change to a filed value, unit, scale,
  concept, or period. The append-only guarantee now holds against a direct SQL session, not only
  against application code.
- `listing` is unique on `(ticker, exchange, effective_start)`, never on ticker alone.
- `footnote_summary` has a partial unique index giving exactly one active version per footnote.
- `footnote_source_block.footnote_id` is nullable with a partial index over orphans, so an
  ungrouped block is a visible defect.
- `llm_invocation` has a check constraint restricting content format to plain_text or yaml.

## API changes

None. No API exists yet.

## Prompt and model changes

None. No real model was invoked during this sprint.

## YAML verification

```
library   ruamel.yaml 0.19.1        floor pinned at 0.18 by test
mode      YAML(typ="safe", pure=True)
schema    YAML 1.2 core
resolver  VersionedResolver
python    3.14.6
```

Confirmed YAML 1.2 semantics: `yes`, `no`, `on`, `off` remain strings. Confirmed quoted CIKs,
accessions, dates, fiscal periods, zero-prefixed footnote numbers, and version strings survive as
text, and that an unquoted `0000320193` becomes the integer `320193`, which is why `require_string`
refuses it rather than coercing it back.

**A real vulnerability was found.** Alias expansion was unbounded: the Sprint 1 limits ran after
parsing, which is useless against a construct that expands during parsing. A five-line document
with nine anchors each referencing the previous nine expanded to 59,049 leaf nodes; two more
levels exhaust memory. A pre-parse anchor and alias budget now rejects it. This was found because
the sprint asked for alias handling to be verified, not by review.

## Tests added

33 new, 170 total assertions across 12 files.

```
tests/unit/test_sec_http_client.py    15   UA headers, 403 classification, 600s cooldown not
                                           backoff, directory listing, HTML-where-ZIP-expected,
                                           truncation, corrupt ZIP, empty ZIP, provenance,
                                           transient retry, EFTS bucket, request counting
tests/unit/test_migrations.py         14   every model table created, create/drop symmetry,
                                           reverse drop order, append-only trigger present and
                                           dropped, listing not unique on ticker, one active
                                           summary, nullable orphan parent, content-format check,
                                           offline upgrade and downgrade DDL, plus 2 live tests
                                           that SKIP without a database
tests/unit/test_yaml_parser.py        +6   library identity, quoted dates, quoted fiscal period
                                           and version, alias bomb, anchor bound, benign aliases
```

## Tests run and results

Commands executed, output observed:

```
$ ./.venv/bin/ruff format --check packages tests scripts migrations
75 files already formatted

$ ./.venv/bin/ruff check packages tests scripts migrations
All checks passed!

$ ./.venv/bin/mypy packages --ignore-missing-imports
Success: no issues found in 59 source files

$ ./.venv/bin/python -m pytest tests
137 passed, 2 skipped in 3.14s

$ ./.venv/bin/python -m pytest tests -q --cov=... --cov-report=term
TOTAL  1683  88  95%
```

The 2 skips are the live-database migration tests. They skip with an explicit reason so a missing
database cannot masquerade as a pass.

Migration verification without a database:

```
$ ./.venv/bin/alembic upgrade head --sql
exit 0, 653 lines of DDL
  25 CREATE TABLE (24 plus alembic_version)
  36 CREATE INDEX
  21 CHECK
  29 FOREIGN KEY
  19 UNIQUE
  trigger and function present

$ ./.venv/bin/alembic downgrade 0001_initial:base --sql
exit 0, 62 lines
  25 DROP TABLE in reverse-dependency order
  2 DROP TRIGGER / DROP FUNCTION
```

## Benchmarks

None. Model benchmarking requires a real provider and is Phase 6 work.

Measured during this sprint: DERA total 27,228,877,737 bytes across 78 packages; monthlies
2,145,477,071 bytes; smallest package 28,064 bytes (2009q1, early XBRL); largest 663,293,756
bytes (2025q1). HEAD returns `Content-Length` on `/files/` paths, unlike the Archives paths, so
the whole download could be sized precisely before starting.

## Known issues

1. **The migration has not been applied to a live PostgreSQL.** No PostgreSQL on this machine, and
   the Docker daemon cannot start containers:
   ```
   $ docker run --rm hello-world
   docker: Error response from daemon: failed to create task for container:
   failed to start shim: start failed: failed to create TTRPC connection:
   unsupported protocol: Yunix

   $ docker compose version
   docker: unknown command: docker compose

   $ ./.venv/bin/alembic upgrade head
   connection to server at "127.0.0.1", port 5432 failed: Connection refused
   ```
   Verified by offline DDL generation and structural tests instead. BLOCKING for Phase 3; run the
   two skipped tests first wherever a database exists.
2. The rate limiter is in-process. The mirror ran as a single process for exactly this reason.
   BLOCKING for Phase 4.
3. Canonical grouping by role URI is still verified on exactly one filing. BLOCKING for Phase 5.
4. Provider catalog and pricing still unverified. BLOCKING for any cost commitment.
5. Authentication is still a local single-user implementation. BLOCKING for public deployment.
6. The DERA packages are held on local disk only. A second copy in durable object storage is
   prudent given that twelve of them are irreplaceable.

## Deferred work

DERA TSV loading, filing discovery, document acquisition. All in `roadmap.md`.

## Documentation updated

`roadmap.md`, `techspecs.md`, `CHANGELOG.md`, `docs/adr/ADR-0013-...`,
`docs/data-dictionary/README.md`, `docs/sec/dera-notes.md`, `docs/runbooks/dera-mirror.md`, and
this record.

## Roadmap changes

URGENT-01 COMPLETE with completion evidence. Risk R-01 CLOSED. Phase 0 COMPLETE. Sprint 2 marked
COMPLETE.

## ADRs created

None new. ADR-0013 amended to pin the YAML parser and document the alias bound.

## Deployment notes

Still nothing deployable. No API, no infrastructure definition.

## Rollback notes

The migration is reversible and its downgrade is verified offline. The DERA mirror is additive;
rolling back means deleting `var/dera/`, which would discard twelve irreplaceable packages, so
do not.

## Next recommended sprint

**SPRINT-0003: apply the migration and load DERA into the fact lake.**

First action wherever a PostgreSQL exists: run the two skipped live migration tests. Then load
`sub`, `num`, `pre`, `tag`, `ren`, and `txt` from the mirrored packages, with quoting disabled,
into the fact lake, and reconcile monthly against quarterly coverage.
