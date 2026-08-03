# Runbook — the disposable test database

Destructive database tests drop every application table. They run against a database that exists
only for them, never against the one holding real loaded facts.

There are **two** disposable databases, not one, and no test writes to the application database.

```
DATABASE_URL                   fintek                    the application database. No test
                                                         reads or writes it. Ordinary CI does
                                                         not set this variable at all.
TEST_DATABASE_URL              fintek_test               disposable; the migration round trip
                                                         drops every table in it
INTEGRATION_TEST_DATABASE_URL  fintek_integration_test   disposable; the persistence suites
                                                         load, query and clean it
```

**Why two disposable databases and not one.** The migration round trip runs `alembic downgrade
base`. Pointed at the database a persistence test is loading into, it deletes that schema
mid-suite. Which suite loses depends on which ran first, so the result is intermittently green —
harder to diagnose than either suite failing outright.

The rule is `rules.md`, section 3, TEST-DATABASE-ISOLATION-INVARIANT.

---

## Why this exists

For one sprint the migration round-trip test ran against `DATABASE_URL`. `make check` executed
`alembic downgrade base`, dropped every application table, **deleted 2,845 loaded facts, and
reported green.** Every assertion it made was correct; it destroyed the data beside them.

The first fix was to skip the test when the target held data. That stopped the deletion and left
the test unrun — the other half of the same failure, and the one this project has already made
twice. A separate target runs the test *and* keeps the data.

---

## Local setup

One privileged action, once. Two deliberate properties of the local cluster require it:

1. The `fintek` role has no `CREATEDB`. Granting it would hand every future test run the ability
   to create databases, which is broader than the problem. One database, created once, is
   narrower.
2. `pg_hba.conf` scopes peer authentication to the `fintek` *database*:
   `local fintek fintek peer map=fintek_map`. A new database is not covered by that rule.

Run:

```bash
sudo bash var/local-tools/setup_test_database.sh
```

It creates `fintek_test` owned by `fintek`, widens that one `pg_hba` line to
`local fintek,fintek_test fintek peer map=fintek_map`, reloads PostgreSQL, verifies the
unprivileged user can reach the new database, and reports the application database's row count so
you can see it was untouched. It backs up `pg_hba.conf` first and sets no password on any role.

Verified after the run on this host:

```
fintek_test                exists, owned by fintek
pg_hba.conf backup         /var/lib/postgres/data/pg_hba.conf.backup-20260801-214426
                           5,661 bytes, postgres:postgres, mode 0600
fintek role verifier       none (rolpassword IS NULL in pg_authid)
application database       2,845 xbrl_fact rows, unchanged
```

The peer rule's scope was confirmed by probing rather than by reading the file: `fintek` and
`fintek_test` are reachable over the socket with no password, while `postgres`, `template1`, and
any other role are still refused. The rule was widened by one database name and nothing else.

Then add to `.env`, which is gitignored:

```
TEST_DATABASE_URL=postgresql+psycopg://fintek@/fintek_test?host=/run/postgresql
```

Verify:

```bash
make db-verify-isolation
```

```
application database   fintek on socket /run/postgresql
test database          fintek_test on socket /run/postgresql
they differ            OK, destructive tests cannot reach the application data
```

**The helper lives under `var/local-tools/`, which is gitignored.** Host bootstrap is not
repository code: it edits a system configuration file outside the project and is specific to this
machine's PostgreSQL layout.

---

## CI setup

The workflow declares both URLs against one service container and creates the second database
explicitly, because `POSTGRES_DB` creates exactly one. Both URLs carry a **disposable CI-only
password**, written openly in `.github/workflows/ci.yml`:

```yaml
env:
  DATABASE_URL: postgresql+psycopg://fintek:<ci-password>@localhost:5432/fintek
  TEST_DATABASE_URL: postgresql+psycopg://fintek:<ci-password>@localhost:5432/fintek_test
```

That password protects nothing. The container is created and destroyed by one job, is reachable
only from that job, and holds public SEC data. A repository secret would imply it is sensitive and
add a rotation obligation for a value that cannot leak anything.

It replaced `POSTGRES_HOST_AUTH_METHOD: trust`, which accepted any connection with no password at
all — so the workflow never exercised the authentication path the application code takes, and it
normalised a posture that must never reach a deployment. The service health check authenticates
rather than probing the port, so the job waits for a server that will accept the credential the
tests use.

**This is CI only.** The local host uses peer authentication and has no verifier for the role.
Deployment authentication is undecided and follows from neither.

```
make db-create-test        creates fintek_test
make db-upgrade            applies the schema to fintek
make db-verify-isolation   fails the job if the two resolve to one database
```

`db-verify-isolation` runs **before** any test, so a misconfiguration is caught before something
drops a table rather than after. It prints host, port, and database name only — no step echoes a
URL.

---

## What the guard actually checks

`packages/persistence/engine.assert_disposable`, in order:

| Check | The failure it prevents |
|---|---|
| `TEST_DATABASE_URL` is set | falling back to `DATABASE_URL`, which works quietly until the application database has data |
| it names a database | an empty path drops whatever the server's default happens to be |
| its identity differs from the application's | `@localhost/fintek` and `@127.0.0.1:5432/fintek` are different strings and the same database |
| the name carries a `test` token | `fintek_backup` is separate and still not one to drop tables in |
| the name has no production token | `prod_test` has a test designation and mentions production |

Identity is host, port, socket path, and database name. **Credentials are excluded on purpose:**
including the user would let a destructive run be authorized by connecting as someone else.

A second guard watches from the other side. A session hook in `tests/conftest.py` records the row
counts of `issuer`, `filing`, and `xbrl_fact` before the suite and compares them after. Any
change fails the run — a dropped table, or a fixture row left behind by a test that should have
cleaned up.

---

## Failure: "the server is up but the test database is unusable"

The database does not exist, or the role cannot reach it. Run `make db-create-test`; if that
reports it cannot create the database, run the local setup above.

This **fails rather than skips** on purpose. A skip is how a destructive test silently stops
running.

## Failure: "TEST_DATABASE_URL and DATABASE_URL resolve to the SAME database"

Exactly what the guard is for. Do not relax it. Point `TEST_DATABASE_URL` at a different database.

## Failure: "the suite changed the APPLICATION database"

Either a destructive test reached it, or a non-destructive test left rows behind. The message
names each table and its before and after counts. Fix the test; do not adjust the baseline.

## Failure: "not designated as a test database"

The name must contain `test` as a whole underscore-delimited token. `fintek_testing` and `latest`
do not qualify, and that is deliberate — a substring match would designate `latest` disposable.

---

## Recovering the application database

If a load is lost, it is fully reproducible. That is the point of the loader being idempotent and
reconciled rather than a one-shot import:

```bash
make db-upgrade
for a in 0000320193-25-000079 0000320193-25-000008 0000320193-25-000057 0000320193-25-000073; do
  python scripts/load_dera_partition.py "$a"
done
```

Each run re-reads its package, re-verifies its hash, and reconciles on nine checks.


---

## Redirecting Alembic safely — defect D-13

**`sqlalchemy.url` on an Alembic `Config` is not, on its own, the migration target.**

`migrations/env.py` resolves through `packages.persistence.engine.migration_target_url()`. Before
Sprint 4.1 it called `database_url()` directly, so a caller that set `sqlalchemy.url` was silently
overridden by `DATABASE_URL`. A test helper doing exactly that ran `alembic stamp base` against the
APPLICATION database and emptied its `alembic_version`.

No data was lost — the following `upgrade head` failed on tables that already existed and rolled
back — but that was an accident of ordering. Against an empty application database the helper
would have migrated it. Not one row moved, so the row-count preservation gate stayed green.

### The precedence, which is now explicit and tested

```
1  an explicit argument to migration_target_url()
2  FINTEK_ALEMBIC_URL                       invocation-specific override
3  TEST_DATABASE_URL                        when FINTEK_ALEMBIC_TEST_TARGET is set
4  DATABASE_URL                             the ordinary application target
5  the repository-safe local default
```

An explicitly supplied target is never silently overridden by `DATABASE_URL`.

### Before any destructive migration in a test

```python
from packages.persistence.engine import assert_safe_destructive_target

assert_safe_destructive_target(url, "downgrade base")   # raises BEFORE alembic is called
```

It proves parsed identity, database name, host or socket, port, the disposable-test token, and
difference from the application database — without opening a connection. Use it for `downgrade`,
`stamp`, and any `upgrade` that rebuilds or mutates an existing schema.

### If the application revision is ever wrong again

```bash
# 1. Confirm the SCHEMA before trusting any marker. Never stamp a revision the schema lacks.
psql -c "select to_regclass('public.filing_content_unit')"
# 2. Only then restore the marker.
alembic stamp <the revision the schema actually matches>
```

The preservation gate now watches `alembic_version` as well as row counts, so a recurrence fails
the suite rather than being noticed days later. That is the backstop, not the fix — by the time it
fires, a `downgrade base` has already run.


---

## The second disposable database — `fintek_integration_test`

Three suites persist rows and read them back:

```
tests/integration/test_dera_load.py
tests/integration/test_ten_q_persistence.py
tests/integration/test_canonicalization_persistence.py
```

They used to run against `DATABASE_URL` through the `database_engine` fixture — that is, against
the **application** database, the one holding real loaded facts. Every run depended on that
database being present and on each test cleaning up after itself perfectly. When the application
database was dropped, the three files produced 37 collection errors and one failure. Nothing under
test had broken; a persistence suite had simply been pointed at production-shaped data all along.

They now use the `integration_engine` fixture, which resolves `INTEGRATION_TEST_DATABASE_URL` and
refuses to run unless that database is provably disposable and provably not either of the other
two.

### Creating it locally

One privileged action, once, for the same two reasons the first disposable database needed one:
the `fintek` role has no `CREATEDB`, and `pg_hba.conf` scopes its peer authentication to *named*
databases. Creating the database alone is not enough — without the second change the observed
error is `Peer authentication failed for user "fintek"`, because the general `local all all peer`
rule then matches and the OS user is not the role.

```bash
sudo bash var/local-tools/setup_integration_database.sh
```

It changes exactly two things: it creates `fintek_integration_test` owned by the existing `fintek`
role, and it adds that one name to the existing peer rule, backing the file up first.

```
local  fintek,fintek_test  fintek  peer map=fintek_map
```

becomes

```
local  fintek,fintek_test,fintek_integration_test  fintek  peer map=fintek_map
```

It is idempotent. It creates no role, grants no `CREATEDB`, `SUPERUSER` or `CREATEROLE`, drops
nothing, never creates a database named `fintek` — and refuses to run at all if one has appeared —
leaves `fintek_test` and the general `local all all peer` rule untouched, and reads, writes and
prints no password. It ends by printing the cluster's `fintek%` databases with their owners, the
`fintek` role's still-empty cluster privileges, and `fintek_test`'s table count.

### Then migrate it

```bash
make db-upgrade-integration
```

Routed through `FINTEK_ALEMBIC_URL`, the invocation-specific override `migrations/env.py` reads
**ahead of** `DATABASE_URL`. Setting `DATABASE_URL` to the integration URL would also work, and
would be wrong: it would put a test database's address in the variable the application reads.

### Verify every identity

```bash
make db-verify-isolation
```

Checks the whole set rather than one pair — application against each disposable target, and the
two disposable targets against each other. Verifying only one pair would leave the other free to
collide, and two disposable databases that turn out to be one database show up only as
intermittent test results. It connects to nothing and prints host, port, and database name only,
never a URL.

### What CI does

Ordinary CI has **no application database at all.** The service container creates `fintek_test`
directly, a step creates `fintek_integration_test`, `DATABASE_URL` is not set, and no step runs
`make db-upgrade`. `tests/architecture/test_ci_workflow.py` parses the workflow and fails if a
database named `fintek` is ever created or configured, if the two disposable databases collide,
or if identities are verified after the first test rather than before it.
