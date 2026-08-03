"""Shared test fixtures, the isolated destructive-test target, and two gates.

Gate one stops a skip from reading as a pass. Gate two proves the application database still holds
exactly what it held before the suite ran.
"""

from __future__ import annotations

import os
import socket
import sys
from collections.abc import Iterator
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

FIXTURES = Path(__file__).parent / "fixtures"

# The tables a load writes to. Their combined row count is what the preservation gate watches.
APPLICATION_TABLES = ("xbrl_fact", "filing", "issuer")


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES


@pytest.fixture
def valid_user_agent() -> str:
    return "FinTek Research contact@example.com"


# --- reachability -------------------------------------------------------------------------------


def _reachable(url: str) -> bool:
    """Whether a PostgreSQL server answers at a URL.

    Handles both connection styles this project uses. A URL with `?host=/run/postgresql` is a
    Unix-socket connection and has no TCP endpoint at all; probing localhost:5432 for it would
    answer a question about a different server. The socket path is checked directly instead.
    """
    parsed = urlparse(url.replace("postgresql+psycopg", "postgresql"))
    socket_dir = parse_qs(parsed.query).get("host", [None])[0]
    if socket_dir and socket_dir.startswith("/"):
        return any(Path(socket_dir).glob(".s.PGSQL.*"))
    try:
        with socket.create_connection((parsed.hostname or "localhost", parsed.port or 5432), 2):
            return True
    except OSError:
        return False


def database_reachable() -> bool:
    """Whether the APPLICATION database's server answers."""
    from packages.persistence.engine import database_url

    return _reachable(database_url())


# --- the application database --------------------------------------------------------------------


@pytest.fixture
def integration_database_url() -> str:
    """A URL proven disposable and distinct from BOTH other databases, or a hard failure.

    WHY THIS REPLACED `database_engine`. The persistence integration suites used to run against
    the APPLICATION database through `create_database_engine()`. They write rows, so every run
    depended on a database holding real facts being present and on each test cleaning up after
    itself perfectly. When that database was dropped, 37 collection errors and one failure
    appeared — not because anything under test broke, but because a test suite had been pointed at
    production-shaped data all along.

    Deliberately NOT a skip when the variable is unset. A skip is how an integration suite
    silently stops running; this is the same reasoning as `test_database_url` above.
    """
    from packages.persistence.engine import (
        UnsafeTestDatabaseError,
        assert_integration_disposable,
    )
    from packages.persistence.engine import integration_test_database_url as configured

    url = configured()

    if url is None and not database_reachable():
        pytest.skip(
            "no reachable PostgreSQL and no INTEGRATION_TEST_DATABASE_URL; nothing to test against"
        )

    try:
        return assert_integration_disposable(url)
    except UnsafeTestDatabaseError as error:
        pytest.fail(str(error))


@pytest.fixture
def integration_engine(integration_database_url: str) -> Iterator[object]:
    """A working, migrated connection to the disposable integration database.

    Fails rather than skips when the server is up but the database is missing or unmigrated, for
    the same reason `disposable_engine` does: a setup error with a one-line fix must not be able to
    masquerade as a passing suite.
    """
    from sqlalchemy import create_engine, text

    if not _reachable(integration_database_url):
        pytest.skip("no reachable PostgreSQL; this test exercises a live schema")

    engine = create_engine(integration_database_url)
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
            migrated = connection.execute(text("SELECT to_regclass('public.filing')")).scalar()
    except Exception as error:  # noqa: BLE001 - the reason is reported, not swallowed
        engine.dispose()
        from packages.persistence.engine import parse_identity

        target = parse_identity(integration_database_url)
        pytest.fail(
            f"the server is up but the integration database {target.endpoint} is unusable: "
            f"{type(error).__name__}. Create it with `make db-create-integration` and migrate it "
            f"with `make db-upgrade-integration`, or see docs/runbooks/test-database.md."
        )

    if migrated is None:
        engine.dispose()
        pytest.fail(
            "the integration database exists but has no schema. Run "
            "`make db-upgrade-integration`. This fails rather than skips because an unmigrated "
            "target is a setup error, not an environment that cannot run the test."
        )

    try:
        yield engine
    finally:
        engine.dispose()


# --- the disposable destructive-test database -----------------------------------------------------


@pytest.fixture
def test_database_url() -> str:
    """A URL proven separate, disposable, and test-designated, or a hard failure.

    Deliberately NOT a skip when `TEST_DATABASE_URL` is unset. A skip would mean the destructive
    test silently stops running the moment someone forgets the variable, which is the state this
    whole arrangement exists to end. It skips only when the SERVER is unreachable — an environment
    that genuinely cannot run it — and fails when the configuration is wrong.
    """
    from packages.persistence.engine import (
        UnsafeTestDatabaseError,
        assert_disposable,
    )
    from packages.persistence.engine import test_database_url as configured

    url = configured()

    if url is None and not database_reachable():
        pytest.skip("no reachable PostgreSQL and no TEST_DATABASE_URL; nothing to test against")

    try:
        return assert_disposable(url)
    except UnsafeTestDatabaseError as error:
        pytest.fail(str(error))


@pytest.fixture
def disposable_engine(test_database_url: str) -> Iterator[object]:
    """A working connection to the disposable database.

    Distinguishes two situations that a single skip would blur:

    - The SERVER is unreachable. The machine cannot run database tests at all, so this skips.
    - The server answers but the test DATABASE is missing. That is a setup error with a one-line
      fix, and skipping it is how a destructive test quietly stops running. It fails, with the
      command that fixes it.
    """
    from sqlalchemy import create_engine, text

    if not _reachable(test_database_url):
        pytest.skip("no reachable PostgreSQL; this test exercises a live schema")

    engine = create_engine(test_database_url)
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception as error:  # noqa: BLE001 - the reason is reported, not swallowed
        engine.dispose()
        from packages.persistence.engine import parse_identity

        target = parse_identity(test_database_url)
        pytest.fail(
            f"the server is up but the test database {target.endpoint} is unusable: "
            f"{type(error).__name__}. Create it with `make db-create-test`, or see "
            f"docs/runbooks/test-database.md. This fails rather than skips because a destructive "
            f"test that silently stops running is the defect this whole arrangement exists to end."
        )

    try:
        yield engine
    finally:
        engine.dispose()


# --- the skip gate ------------------------------------------------------------------------------

_skipped: list[tuple[str, str]] = []


def pytest_runtest_logreport(report: pytest.TestReport) -> None:
    """Record every skip, however it was raised.

    A fixture-level skip reports during `setup`; a `pytest.skip()` inside the test body reports
    during `call`. Watching only `setup` misses the second kind entirely, which is how the first
    version of this gate passed a suite containing a deliberate skip.
    """
    if report.skipped and report.when in ("setup", "call"):
        reason = report.longrepr[2] if isinstance(report.longrepr, tuple) else str(report.longrepr)
        _skipped.append((report.nodeid, reason))


# --- the application-preservation gate -------------------------------------------------------------

_baseline: dict[str, int] | None = None


def _application_counts() -> dict[str, int] | None:
    """Row counts in the application database, plus its migration revision, or None if unreadable.

    THE REVISION IS WATCHED BECAUSE ROW COUNTS ALONE MISSED A REAL INCIDENT. A Sprint 4.1 test
    helper redirected alembic by setting `sqlalchemy.url` on the Config — but `migrations/env.py`
    resolves its target through `packages.persistence.engine.database_url()`, which reads
    DATABASE_URL and overrides that option. The helper therefore ran `alembic stamp base` against
    the APPLICATION database. Not one row moved, so this gate stayed green while the application's
    `alembic_version` was silently emptied, and the schema and its recorded revision disagreed.

    A revision string is not a row count, so it is folded in as a pseudo-entry rather than given a
    second gate: one comparison, one failure message, no way to add a watched property and forget
    to check it.
    """
    if not database_reachable():
        return None
    try:
        from sqlalchemy import text

        from packages.persistence.engine import create_database_engine

        engine = create_database_engine()
        try:
            with engine.connect() as connection:
                present = {
                    row[0]
                    for row in connection.execute(
                        text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
                    )
                }
                counts: dict[str, int] = {
                    table: connection.execute(
                        text(f"SELECT count(*) FROM {table}")  # noqa: S608 - fixed identifiers
                    ).scalar_one()
                    for table in APPLICATION_TABLES
                    if table in present
                }
                if "alembic_version" in present:
                    revision = connection.execute(
                        text("SELECT version_num FROM alembic_version")
                    ).scalar()
                    # Hashed to an int so the whole baseline stays one comparable mapping. The
                    # value is opaque; what matters is that it does not change during a suite.
                    counts["alembic_version:" + str(revision)] = 1
                return counts
        finally:
            engine.dispose()
    except Exception:
        # An unreadable application database is not a test failure by itself. It becomes one only
        # if the counts were readable BEFORE the suite and are not after, which is handled below.
        return None


def pytest_sessionstart(session: pytest.Session) -> None:
    global _baseline
    _baseline = _application_counts()


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    """Two gates, both able to fail an otherwise green run.

    GATE 1, skips. A skip is invisible in the default progress line and reads as success in the
    summary: "203 passed, 2 skipped" is what this suite reported for two sprints while the only
    two tests exercising the live schema had never once executed. Off unless
    `FINTEK_FORBID_SKIPS` is set, because a developer without a database should still get a useful
    local run. `make test-no-skips` sets it; CI runs that target.

    GATE 2, application data. Always on. The suite must not change the application database's row
    counts — not by dropping tables, and not by leaving a fixture row behind. This is the check
    that would have caught 2,845 facts being deleted by `make check`, instead of the deletion
    being noticed days later.
    """
    writer = session.config.get_terminal_writer()
    failed = False

    if os.environ.get("FINTEK_FORBID_SKIPS") and _skipped:
        writer.line("")
        writer.line(f"FAIL: {len(_skipped)} test(s) skipped where all tests were expected to run.")
        for nodeid, reason in _skipped:
            writer.line(f"  {nodeid}")
            writer.line(f"      {reason}")
        failed = True

    if _baseline is not None:
        after = _application_counts()
        if after is None:
            writer.line("")
            writer.line(
                "FAIL: the application database was readable before the suite and is not after. "
                "A destructive test targeted it."
            )
            failed = True
        elif after != _baseline:
            writer.line("")
            writer.line("FAIL: the suite changed the APPLICATION database.")
            for table in sorted(set(_baseline) | set(after)):
                before_count = _baseline.get(table, 0)
                after_count = after.get(table, 0)
                if before_count != after_count:
                    writer.line(f"  {table}: {before_count} -> {after_count}")
            writer.line(
                "  Destructive tests belong on TEST_DATABASE_URL; non-destructive ones must "
                "clean up after themselves."
            )
            failed = True

    if failed:
        session.exitstatus = 1
