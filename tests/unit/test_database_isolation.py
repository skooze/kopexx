"""The guard that keeps destructive tests off the application database.

This is the module that would have prevented 2,845 loaded facts being deleted by `make check`.
Every test below names the specific way a weaker guard lets that happen anyway.
"""

from __future__ import annotations

import pytest

from packages.persistence.engine import (
    DatabaseIdentity,
    UnsafeTestDatabaseError,
    assert_disposable,
    parse_identity,
)

APPLICATION = "postgresql+psycopg://fintek@/fintek?host=/run/postgresql"
DISPOSABLE = "postgresql+psycopg://fintek@/fintek_test?host=/run/postgresql"


# --- identity parsing -----------------------------------------------------------------------


def test_a_socket_url_parses_to_its_socket_directory_and_database() -> None:
    identity = parse_identity(APPLICATION)
    assert identity == DatabaseIdentity(database="fintek", socket_dir="/run/postgresql")
    assert identity.host is None and identity.port is None


def test_a_tcp_url_parses_to_host_port_and_database() -> None:
    identity = parse_identity("postgresql+psycopg://fintek@db.example:6543/fintek")
    assert identity == DatabaseIdentity(database="fintek", host="db.example", port=6543)


def test_a_tcp_url_without_a_port_assumes_the_postgres_default() -> None:
    assert parse_identity("postgresql://u@h/fintek").port == 5432


def test_loopback_spellings_normalize_to_one_host() -> None:
    """`localhost`, `127.0.0.1`, and `::1` are the same server.

    Left unnormalized, `DATABASE_URL=...@localhost/fintek` and
    `TEST_DATABASE_URL=...@127.0.0.1/fintek` would compare unequal and the guard would wave
    through a destructive run against the application database.
    """
    a = parse_identity("postgresql://u@localhost:5432/fintek")
    b = parse_identity("postgresql://u@127.0.0.1:5432/fintek")
    c = parse_identity("postgresql://u@[::1]:5432/fintek")
    assert a == b == c


def test_identity_ignores_credentials() -> None:
    """Two URLs differing only by user name are the SAME database.

    Including the user in the identity would let a destructive test run against the application
    database simply by connecting as someone else.
    """
    assert parse_identity("postgresql://alice@h/fintek") == parse_identity(
        "postgresql://bob@h/fintek"
    )


def test_the_endpoint_description_carries_no_credential() -> None:
    """Error messages name the target. They must never name a secret."""
    endpoint = parse_identity("postgresql://user:hunter2@h:5432/fintek_test").endpoint
    assert "hunter2" not in endpoint
    assert "user" not in endpoint
    assert "fintek_test" in endpoint


# --- the guard ------------------------------------------------------------------------------


def test_a_separate_test_database_is_accepted() -> None:
    assert assert_disposable(DISPOSABLE, APPLICATION) == DISPOSABLE


def test_same_host_and_port_but_a_different_database_is_accepted() -> None:
    """Isolation is per database, not per server. One cluster serving both is the normal case."""
    assert assert_disposable(
        "postgresql://u@localhost:5432/fintek_test",
        "postgresql://u@localhost:5432/fintek",
    )


def test_an_identical_url_is_rejected() -> None:
    with pytest.raises(UnsafeTestDatabaseError, match="SAME database"):
        assert_disposable(APPLICATION, APPLICATION)


def test_the_same_database_spelled_differently_is_rejected() -> None:
    """NAME COMPARISON IS NOT ENOUGH.

    These two URLs differ as strings, name the same database, and a guard comparing only the
    configured text would let the destructive test run against production data.
    """
    with pytest.raises(UnsafeTestDatabaseError, match="SAME database"):
        assert_disposable(
            "postgresql://someone@127.0.0.1:5432/fintek",
            "postgresql+psycopg://fintek@localhost:5432/fintek",
        )


def test_a_missing_url_fails_closed_and_does_not_fall_back() -> None:
    """The whole point. A fallback to DATABASE_URL would work everywhere, quietly, until the day
    the application database had something in it."""
    with pytest.raises(UnsafeTestDatabaseError, match="not set"):
        assert_disposable(None, APPLICATION)
    with pytest.raises(UnsafeTestDatabaseError, match="not set"):
        assert_disposable("", APPLICATION)


def test_a_url_naming_no_database_is_rejected() -> None:
    """An empty path would drop whatever the server's default database happens to be."""
    with pytest.raises(UnsafeTestDatabaseError, match="names no database"):
        assert_disposable("postgresql://u@localhost:5432/", APPLICATION)


def test_a_database_without_a_test_designation_is_rejected() -> None:
    """Separate is not sufficient. `fintek_backup` is a different database and still not one to
    drop every table in."""
    with pytest.raises(UnsafeTestDatabaseError, match="not designated"):
        assert_disposable("postgresql://u@localhost:5432/fintek_backup", APPLICATION)


@pytest.mark.parametrize("name", ["fintek_testing", "latest", "attest", "testbed"])
def test_test_must_be_a_whole_token_not_a_substring(name: str) -> None:
    """`latest` contains 'test'. A substring match would designate it a disposable database."""
    with pytest.raises(UnsafeTestDatabaseError, match="not designated"):
        assert_disposable(f"postgresql://u@localhost:5432/{name}", APPLICATION)


@pytest.mark.parametrize("name", ["fintek_test", "test_fintek", "fintek_test_eu", "test"])
def test_a_whole_test_token_anywhere_in_the_name_qualifies(name: str) -> None:
    assert assert_disposable(f"postgresql://u@localhost:5432/{name}", APPLICATION)


@pytest.mark.parametrize(
    "name", ["prod_test", "test_production", "live_test", "master_test", "primary_test"]
)
def test_a_production_sounding_name_is_rejected_even_with_a_test_token(name: str) -> None:
    """A name that mentions production is not a name to drop tables in, whatever else it says."""
    with pytest.raises(UnsafeTestDatabaseError, match="in its name"):
        assert_disposable(f"postgresql://u@localhost:5432/{name}", APPLICATION)


def test_the_rejection_message_never_prints_a_credential() -> None:
    with pytest.raises(UnsafeTestDatabaseError) as raised:
        assert_disposable("postgresql://user:hunter2@localhost:5432/fintek_prod", APPLICATION)
    assert "hunter2" not in str(raised.value)


# --- configuration resolution -----------------------------------------------------------------


def test_the_two_urls_resolve_independently(monkeypatch: pytest.MonkeyPatch) -> None:
    """Separate variables, separate answers. TEST_DATABASE_URL never shadows DATABASE_URL and
    DATABASE_URL never supplies TEST_DATABASE_URL."""
    from packages.persistence.engine import database_url, test_database_url

    monkeypatch.setenv("DATABASE_URL", APPLICATION)
    monkeypatch.setenv("TEST_DATABASE_URL", DISPOSABLE)
    assert database_url() == APPLICATION
    assert test_database_url() == DISPOSABLE


def test_an_unset_test_url_resolves_to_none_not_to_the_application_url(
    monkeypatch: pytest.MonkeyPatch, tmp_path: object
) -> None:
    """Verified against the real resolver, including its .env fallback: with the variable unset
    and no .env entry, the answer is None — never the application URL."""
    from packages.persistence import engine

    monkeypatch.delenv("TEST_DATABASE_URL", raising=False)
    monkeypatch.setattr(engine, "REPO_ROOT", tmp_path)  # a directory with no .env
    assert engine.test_database_url() is None


def test_this_projects_configured_pair_is_safe() -> None:
    """The real configuration, checked rather than assumed.

    Skips only when no test database is configured at all, which is a developer-machine state.
    It never passes by silently accepting an unsafe pair.
    """
    from packages.persistence.engine import database_url, test_database_url

    configured = test_database_url()
    if configured is None:
        pytest.skip("no TEST_DATABASE_URL configured on this machine")

    assert assert_disposable(configured, database_url()) == configured
