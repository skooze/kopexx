"""Create the disposable database that destructive tests run against.

    python scripts/create_test_database.py

Idempotent: an existing database is left alone. The script refuses to do anything unless the
target is provably separate from the application database, so it can never create — or be
redirected at — the database holding real facts.

CI invokes this through `make db-create-test`. On a development host where the application role
lacks CREATEDB, it explains exactly what is missing rather than failing obscurely; creating the
database is then a single privileged action, documented in docs/runbooks/test-database.md.

SECURITY: connects with whatever credentials the environment already supplies and prints none of
them. Error messages carry host, port, socket path, and database name only.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.exc import OperationalError, ProgrammingError  # noqa: E402

from packages.persistence.engine import (  # noqa: E402
    UnsafeTestDatabaseError,
    assert_disposable,
    database_url,
    parse_identity,
    test_database_url,
)

# CREATE DATABASE cannot run inside the database it creates, so a maintenance connection is needed.
# `postgres` exists on every standard cluster.
MAINTENANCE_DATABASE = "postgres"


def maintenance_url(target: str) -> str:
    """The same server as the target, but connected to the maintenance database."""
    identity = parse_identity(target)
    return target.replace(f"/{identity.database}", f"/{MAINTENANCE_DATABASE}", 1)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--print-url",
        action="store_true",
        help="print the validated test URL and exit, creating nothing",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="prove the target is separate and disposable, then exit without connecting",
    )
    args = parser.parse_args(argv)

    configured = test_database_url()
    try:
        url = assert_disposable(configured)
    except UnsafeTestDatabaseError as error:
        print(f"REFUSED: {error}", file=sys.stderr)
        return 2

    if args.print_url:
        print(url)
        return 0

    target = parse_identity(url)
    application = parse_identity(database_url())
    print(f"application database   {application.endpoint}")
    print(f"test database          {target.endpoint}")

    if args.verify:
        print("they differ            OK, destructive tests cannot reach the application data")
        return 0

    # Ask the target itself first. A usable database needs no maintenance connection, and on a
    # locked-down host the application role deliberately has no route to one: pg_hba scopes peer
    # authentication to named databases, and `postgres` is not among them. Checking here makes the
    # target idempotent both in CI, where the first run creates it, and locally, where a privileged
    # helper already did.
    probe = create_engine(url)
    try:
        with probe.connect() as connection:
            connection.execute(text("SELECT 1"))
        print(f"already present        {target.database}")
        return 0
    except (OperationalError, ProgrammingError):
        pass
    finally:
        probe.dispose()

    engine = create_engine(maintenance_url(url), isolation_level="AUTOCOMMIT")
    try:
        with engine.connect() as connection:
            exists = connection.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": target.database}
            ).fetchone()
            if exists:
                print(f"present but unreachable by this role: {target.database}", file=sys.stderr)
                return 1

            # The identifier cannot be a bound parameter in DDL. It has been validated by
            # assert_disposable, which rejects anything but a test-designated name.
            connection.execute(text(f'CREATE DATABASE "{target.database}"'))
            print(f"created                {target.database}")
            return 0
    except (OperationalError, ProgrammingError) as error:
        message = str(error.orig) if error.orig else str(error)
        print(f"could not create {target.database}: {message.strip()}", file=sys.stderr)
        print(
            "\nOn this development host the application role has neither CREATEDB nor access to "
            "the maintenance database, both by design. Creating the test database is one "
            "privileged action; see docs/runbooks/test-database.md.",
            file=sys.stderr,
        )
        return 1
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
