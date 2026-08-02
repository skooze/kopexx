"""The single home for resolving database URLs, comparing database identities, and building
engines.

Three places needed URL resolution and each had its own copy: the Alembic environment, the live
migration tests, and the DERA loader. Three copies of a connection-string resolver is three chances
to point at a different database and not notice.

TWO URLS, TWO PURPOSES.

    DATABASE_URL        the application database. Holds real loaded facts. Nothing may drop it.
    TEST_DATABASE_URL   a disposable database for DESTRUCTIVE tests only.

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


def assert_disposable(test_url: str | None, application_url: str | None = None) -> str:
    """Prove a URL is a separate, disposable, test-designated database, or raise.

    Four checks, each covering a way the previous one can be satisfied and still be wrong:

    1. The URL exists at all. Absent means fail closed, never fall back.
    2. It names a database. A URL with an empty path would compare equal to nothing and drop
       whatever the server's default happens to be.
    3. Its identity differs from the application database's. NAME COMPARISON IS NOT ENOUGH — two
       URLs can spell the same database differently — so host, port, socket path, and name are
       compared as a unit.
    4. The name carries a test designation and mentions nothing production-like.
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

    return test_url


def create_database_engine(url: str | None = None, **kwargs: Any) -> Engine:
    """Build an engine against the resolved application URL.

    `future=True` is not passed: SQLAlchemy 2 has no legacy mode to opt out of.
    """
    return create_engine(url or database_url(), **kwargs)
