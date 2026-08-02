# Runbook — the disposable test database

Destructive database tests drop every application table. They run against a database that exists
only for them, never against the one holding real loaded facts.

```
DATABASE_URL       fintek        the application database
TEST_DATABASE_URL  fintek_test   disposable; destructive tests drop every table in it
```

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
