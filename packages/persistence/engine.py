"""The single home for resolving database URLs, comparing database identities, and building
engines.

Three places needed URL resolution and each had its own copy: the Alembic environment, the live
migration tests, and the DERA loader. Three copies of a connection-string resolver is three chances
to point at a different database and not notice.

THREE URLS, THREE PURPOSES, NO FALLBACK BETWEEN THEM.

    DATABASE_URL                    the application database. Holds real loaded facts. Nothing may
                                    drop it, and no test writes to it.
    TEST_DATABASE_URL               disposable. The migration round trip drops every table in it.
    INTEGRATION_TEST_DATABASE_URL   disposable. The persistence integration suites load, query and
                                    clean it.

The last two are separate databases, not one shared disposable target. The migration round trip
runs `downgrade base`; if the integration suite were loading into the same database, the pair would
be order-dependent and intermittently green — a failure mode harder to diagnose than either suite
failing outright.

The migration round-trip test runs `alembic downgrade base`, which drops every application table.
Pointed at the application database it deletes real data, silently, while the suite reports green —
which is exactly what happened on this development host, costing 2,845 loaded facts. Skipping the
test when data is present prevents the deletion but leaves the test unrun. The correct answer is a
separate target, and a guard that FAILS CLOSED rather than falling back.

SECURITY: no credential is read, written, defaulted, or printed here. `DatabaseIdentity` carries
host, port, socket path, and database name — never user or password — so an error message naming a
target can never leak one. On this development host authentication is `peer` over a Unix socket, so
the URL contains no secret at all; a deployment supplies its own through the environment.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

REPO_ROOT = Path(__file__).resolve().parents[2]

# Peer authentication over the local socket. Correct for this development host and for nothing
# else: it works because client and server share a kernel that can vouch for the connecting UID.
DEFAULT_URL = "postgresql+psycopg://fintek@/fintek?host=/run/postgresql"

# A destructive test target must SAY it is one. `fintek` is rejected; `fintek_test` is accepted.
# `test` must be a whole underscore-delimited token, so `fintek_testing` and `latest` do not
# qualify by accident.
TEST_DESIGNATION = re.compile(r"(^|_)test($|_)")

# Names that must never be a destructive target however they are decorated. `prod_test` is still
# refused: a name that mentions production is not a name to drop tables in.
FORBIDDEN_TOKENS = frozenset({"prod", "production", "live", "master", "primary"})

# Cluster-owned databases. None of them belongs to this project, none may ever be a test target,
# and `template0` in particular rejects connections at all. A URL naming one is a misconfiguration
# that must be refused before any SQL runs rather than discovered by a confusing server error.
SYSTEM_DATABASES = frozenset({"postgres", "template0", "template1"})

# The one variable that names the persistence integration target. Deliberately its own name rather
# than an overload of DATABASE_URL: an overloaded variable means the safe and the unsafe target are
# spelled identically, and the only thing distinguishing them is which command happens to read it.
INTEGRATION_TARGET_ENV = "INTEGRATION_TEST_DATABASE_URL"


class UnsafeTestDatabaseError(RuntimeError):
    """The destructive test target could not be proven separate and disposable."""


@dataclass(frozen=True)
class DatabaseIdentity:
    """What makes two connection strings the same database.

    Credentials are deliberately absent. Two URLs differing only by user are the same database and
    must compare equal; including the user would let a destructive test run against production
    simply by connecting as someone else.
    """

    database: str
    host: str | None = None
    port: int | None = None
    socket_dir: str | None = None

    @property
    def endpoint(self) -> str:
        """A description safe to put in an error message or a log line."""
        if self.socket_dir:
            return f"{self.database} on socket {self.socket_dir}"
        return f"{self.database} on {self.host or 'localhost'}:{self.port or 5432}"


def parse_identity(url: str) -> DatabaseIdentity:
    """Reduce a URL to the database it actually names.

    Handles both connection styles this project uses. `?host=/run/postgresql` is a Unix-socket
    connection with no TCP endpoint at all, and comparing its (absent) host and port against
    another socket URL's would call every socket connection identical.
    """
    parsed = urlparse(url.replace("postgresql+psycopg", "postgresql"))
    database = (parsed.path or "").lstrip("/")

    query_host = parse_qs(parsed.query).get("host", [None])[0]
    if query_host and query_host.startswith("/"):
        return DatabaseIdentity(database=database, socket_dir=query_host.rstrip("/"))

    host = query_host or parsed.hostname
    if host in ("", None, "localhost", "127.0.0.1", "::1"):
        host = "localhost"
    return DatabaseIdentity(database=database, host=host, port=parsed.port or 5432)


def _from_env_file(key: str) -> str | None:
    env_file = REPO_ROOT / ".env"
    if not env_file.exists():
        return None
    for line in env_file.read_text(encoding="utf-8").splitlines():
        if line.startswith(f"{key}="):
            value = line.split("=", 1)[1].strip().strip('"').strip("'")
            if value:
                return value
    return None


def database_url() -> str:
    """The APPLICATION database: environment, then the project's .env, then the local default."""
    return os.environ.get("DATABASE_URL") or _from_env_file("DATABASE_URL") or DEFAULT_URL


def test_database_url() -> str | None:
    """The DISPOSABLE database for destructive tests, or None when none is configured.

    There is deliberately NO fallback to `database_url()`. A fallback is how a destructive test
    ends up dropping the application database: it would work everywhere, quietly, until the day
    the application database had something in it.
    """
    return os.environ.get("TEST_DATABASE_URL") or _from_env_file("TEST_DATABASE_URL")


def integration_test_database_url() -> str | None:
    """The DISPOSABLE database the PERSISTENCE INTEGRATION tests run against, or None.

    A THIRD identity, deliberately distinct from the other two:

        DATABASE_URL                    the application database. No test writes to it.
        TEST_DATABASE_URL               dropped and rebuilt by the migration round trip.
        INTEGRATION_TEST_DATABASE_URL   loaded, queried and cleaned by the persistence tests.

    Two disposable databases rather than one because the two suites would destroy each other: the
    migration round trip runs `downgrade base` and drops every table, which would delete the schema
    an integration test is mid-way through loading. Sharing one target makes the pair
    order-dependent and intermittently green, which is worse than either failure alone.

    There is deliberately NO fallback — not to DATABASE_URL, not to TEST_DATABASE_URL, not to a
    default. Absent configuration fails closed at the call site. A fallback to the application
    database is precisely the shape of defect D-13.
    """
    return os.environ.get(INTEGRATION_TARGET_ENV) or _from_env_file(INTEGRATION_TARGET_ENV)


def _assert_disposable_name(target: DatabaseIdentity, variable: str) -> None:
    """The name-shape checks shared by every disposable target.

    One implementation so a second target cannot be added with a weaker version of the same rule,
    which is how a safeguard quietly stops covering half the databases it is supposed to cover.
    """
    if target.database in SYSTEM_DATABASES:
        raise UnsafeTestDatabaseError(
            f"{variable} names the cluster database {target.database!r}. A system database is "
            "never a test target: it is shared with every other database on the server."
        )

    lowered = target.database.lower()
    if not TEST_DESIGNATION.search(lowered):
        raise UnsafeTestDatabaseError(
            f"the destructive target {target.endpoint} is not designated as a test database. "
            "Its name must contain 'test' as a whole underscore-delimited token, for example "
            "fintek_test, so that a misconfiguration is visible rather than merely survivable."
        )

    forbidden = FORBIDDEN_TOKENS.intersection(re.split(r"[_\-]", lowered))
    if forbidden:
        raise UnsafeTestDatabaseError(
            f"the destructive target {target.endpoint} contains {sorted(forbidden)} in its name. "
            "A database whose name mentions production is not a database to drop tables in, "
            "whatever else the name says."
        )


def assert_integration_disposable(
    integration_url: str | None,
    application_url: str | None = None,
    migration_url: str | None = None,
) -> str:
    """Prove the integration target is disposable and is not either of the other two databases.

    Everything `assert_disposable` proves, plus one more separation: the integration target must
    also differ from the MIGRATION test target. Both are disposable, so neither check subsumes the
    other — `fintek_test` passes every disposability test there is and is still the wrong database
    to run a persistence suite in, because the migration round trip drops its tables.

    Identity comparison excludes credentials, exactly as it does everywhere else here: connecting
    as a different user must never be a way to authorize a destructive run.
    """
    if not integration_url:
        raise UnsafeTestDatabaseError(
            f"{INTEGRATION_TARGET_ENV} is not set. The persistence integration tests write to a "
            "database and must never fall back to DATABASE_URL or to the migration test target. "
            f"Set {INTEGRATION_TARGET_ENV} to a disposable database, for example "
            "fintek_integration_test."
        )

    target = parse_identity(integration_url)
    if not target.database:
        raise UnsafeTestDatabaseError(
            f"{INTEGRATION_TARGET_ENV} names no database, so the integration target cannot be "
            "proven separate from the application one."
        )

    application = parse_identity(application_url or database_url())
    if target == application:
        raise UnsafeTestDatabaseError(
            f"{INTEGRATION_TARGET_ENV} and DATABASE_URL resolve to the SAME database: "
            f"{target.endpoint}. The integration suite writes rows and would reach real data."
        )

    configured_migration = migration_url if migration_url is not None else test_database_url()
    if configured_migration:
        migration = parse_identity(configured_migration)
        if target == migration:
            raise UnsafeTestDatabaseError(
                f"{INTEGRATION_TARGET_ENV} and TEST_DATABASE_URL resolve to the SAME database: "
                f"{target.endpoint}. The migration round trip drops every table in that database, "
                "so the two suites would destroy each other depending on which ran first."
            )

    _assert_disposable_name(target, INTEGRATION_TARGET_ENV)
    return integration_url


def assert_disposable(test_url: str | None, application_url: str | None = None) -> str:
    """Prove a URL is a separate, disposable, test-designated database, or raise.

    Four checks, each covering a way the previous one can be satisfied and still be wrong:

    1. The URL exists at all. Absent means fail closed, never fall back.
    2. It names a database. A URL with an empty path would compare equal to nothing and drop
       whatever the server's default happens to be.
    3. Its identity differs from the application database's. NAME COMPARISON IS NOT ENOUGH — two
       URLs can spell the same database differently — so host, port, socket path, and name are
       compared as a unit.
    4. The name is not a cluster database, carries a test designation, and mentions nothing
       production-like. Shared with `assert_integration_disposable` via `_assert_disposable_name`,
       so a second disposable target cannot be admitted under a weaker version of this rule.
    """
    if not test_url:
        raise UnsafeTestDatabaseError(
            "TEST_DATABASE_URL is not set. Destructive database tests drop every application "
            "table and must never fall back to DATABASE_URL. Set TEST_DATABASE_URL to a "
            "disposable database, for example fintek_test."
        )

    target = parse_identity(test_url)
    if not target.database:
        raise UnsafeTestDatabaseError(
            "TEST_DATABASE_URL names no database, so the destructive target cannot be proven "
            "separate from the application one."
        )

    application = parse_identity(application_url or database_url())
    if target == application:
        raise UnsafeTestDatabaseError(
            f"TEST_DATABASE_URL and DATABASE_URL resolve to the SAME database: "
            f"{target.endpoint}. Destructive tests would drop the application's data."
        )

    _assert_disposable_name(target, "TEST_DATABASE_URL")
    return test_url


# The one place an explicit Alembic target may be supplied. `migrations/env.py` reads it FIRST,
# ahead of DATABASE_URL, which is what makes an explicitly supplied target authoritative.
ALEMBIC_TARGET_ENV = "FINTEK_ALEMBIC_URL"


def migration_target_url(explicit: str | None = None) -> str:
    """THE authoritative migration target. One resolver, one precedence order, tested.

    WHY THIS EXISTS — DEFECT D-13. A test helper redirected Alembic by setting `sqlalchemy.url` on
    an Alembic `Config`. `migrations/env.py` resolved its target through `database_url()` instead,
    which reads DATABASE_URL and silently OVERRODE the explicit option, so `alembic stamp base` ran
    against the APPLICATION database and emptied its `alembic_version`. Not one row moved, so the
    row-count preservation gate stayed green.

    The root cause was two independent URL resolutions with no defined precedence, not the missing
    revision check. This function is the single resolver, and its order is explicit:

        1. an explicit argument supplied by the caller
        2. FINTEK_ALEMBIC_URL, the invocation-specific override
        3. TEST_DATABASE_URL, when FINTEK_ALEMBIC_TEST_TARGET selects it
        4. DATABASE_URL, the ordinary application target
        5. the repository-safe local default

    An explicitly supplied target is NEVER silently overridden by DATABASE_URL. That is the whole
    correction.
    """
    if explicit:
        return explicit
    override = os.environ.get(ALEMBIC_TARGET_ENV)
    if override:
        return override
    if os.environ.get("FINTEK_ALEMBIC_TEST_TARGET"):
        configured = test_database_url()
        if not configured:
            raise UnsafeTestDatabaseError(
                "FINTEK_ALEMBIC_TEST_TARGET is set but TEST_DATABASE_URL is not. Refusing to fall "
                "back to the application database, which is exactly how defect D-13 happened."
            )
        return configured
    return database_url()


def assert_safe_destructive_target(url: str | None, operation: str) -> str:
    """Refuse a destructive migration against anything but a proven disposable database.

    PRE-EXECUTION, not post-hoc. The preservation gate in `tests/conftest.py` compares row counts
    and the revision AFTER a suite; by then a `downgrade base` has already run. This raises before
    Alembic is called at all.

    Covers `downgrade`, `stamp`, and any `upgrade` that rebuilds or mutates an existing schema —
    every operation that can change `alembic_version`.
    """
    if not url:
        raise UnsafeTestDatabaseError(
            f"refusing to {operation}: no target URL was resolved. A destructive migration never "
            "falls back to a default."
        )
    # Reuses the four checks in `assert_disposable`: exists, names a database, differs in identity
    # from the application database, and carries a test designation with nothing production-like.
    # Duplicating them here would create a second, weaker gate.
    validated = assert_disposable(url)
    return validated


def create_database_engine(url: str | None = None, **kwargs: Any) -> Engine:
    """Build an engine against the resolved application URL.

    `future=True` is not passed: SQLAlchemy 2 has no legacy mode to opt out of.
    """
    return create_engine(url or database_url(), **kwargs)
