"""Create a disposable database that tests run against.

    python scripts/create_test_database.py                     the migration round-trip target
    python scripts/create_test_database.py --target integration the persistence integration target

Idempotent: an existing database is left alone. The script refuses to do anything unless the
target is provably separate from the application database, so it can never create — or be
redirected at — the database holding real facts.

TWO DISPOSABLE TARGETS, ONE SCRIPT. `--target migration` reads TEST_DATABASE_URL and proves it
separate from the application database. `--target integration` reads INTEGRATION_TEST_DATABASE_URL
and proves it separate from BOTH the application database and the migration target. One home for
"create a disposable database" so a second copy cannot drift into a weaker set of checks.

CI invokes this through `make db-create-test`. On a development host where the application role
lacks CREATEDB, it explains exactly what is missing rather than failing obscurely; creating the
database is then a single privileged action, documented in docs/runbooks/test-database.md.

SECURITY: connects with whatever credentials the environment already supplies and prints none of
them. Error messages carry host, port, socket path, and database name only.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.exc import OperationalError, ProgrammingError  # noqa: E402

from packages.persistence.engine import (  # noqa: E402
    UnsafeTestDatabaseError,
    assert_disposable,
    assert_integration_disposable,
    database_url,
    integration_test_database_url,
    parse_identity,
    test_database_url,
)

# Which configured URL each target reads, and which validator proves it disposable. Adding a
# target here is the only way to add one: the resolver and the proof arrive together.
TARGETS: dict[str, tuple[Callable[[], str | None], Callable[[str | None], str], str]] = {
    "migration": (test_database_url, assert_disposable, "TEST_DATABASE_URL"),
    "integration": (
        integration_test_database_url,
        assert_integration_disposable,
        "INTEGRATION_TEST_DATABASE_URL",
    ),
}

# CREATE DATABASE cannot run inside the database it creates, so a maintenance connection is needed.
# `postgres` exists on every standard cluster.
MAINTENANCE_DATABASE = "postgres"


def maintenance_url(target: str) -> str:
    """The same server as the target, but connected to the maintenance database."""
    identity = parse_identity(target)
    return target.replace(f"/{identity.database}", f"/{MAINTENANCE_DATABASE}", 1)


def verify_all() -> int:
    """Prove every configured database identity before any test runs. Connects to nothing.

    Checks the whole set rather than one pair. Verifying only the migration target would leave the
    integration target free to collide with it, and two disposable databases that turn out to be
    one database is a failure mode that only shows up as intermittent test results.
    """
    application = parse_identity(database_url())
    print(f"{'application database':<31}{application.endpoint}   (never created, never written)")

    identities: dict[str, object] = {}
    for name in sorted(TARGETS):
        resolve, prove, variable = TARGETS[name]
        try:
            url = prove(resolve())
        except UnsafeTestDatabaseError as error:
            print(f"REFUSED: {error}", file=sys.stderr)
            return 2
        identity = parse_identity(url)
        identities[variable] = identity
        print(f"{variable:<31}{identity.endpoint}")
        if identity == application:
            print(f"REFUSED: {variable} IS the application database", file=sys.stderr)
            return 2

    if len(set(identities.values())) != len(identities):
        print("REFUSED: two disposable targets resolve to the same database", file=sys.stderr)
        return 2

    print(f"{'all identities distinct':<31}OK, no suite can reach another's database")
    return 0


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
        help="prove every configured target is separate and disposable, then exit",
    )
    parser.add_argument(
        "--target",
        choices=sorted(TARGETS),
        default="migration",
        help="which disposable database to act on (default: migration)",
    )
    args = parser.parse_args(argv)

    if args.verify:
        return verify_all()

    resolve, prove, variable = TARGETS[args.target]
    configured = resolve()
    try:
        url = prove(configured)
    except UnsafeTestDatabaseError as error:
        print(f"REFUSED: {error}", file=sys.stderr)
        return 2

    if args.print_url:
        print(url)
        return 0

    target = parse_identity(url)
    application = parse_identity(database_url())
    print(f"{'application database':<31}{application.endpoint}")
    print(f"{variable:<31}{target.endpoint}")

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

            # The identifier cannot be a bound parameter in DDL. It has been validated by this
            # target's proof, which rejects anything but a distinct test-designated name.
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
