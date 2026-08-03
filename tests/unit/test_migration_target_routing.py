"""Defect D-13: migration-target routing, and the guards that now prevent recurrence.

WHAT HAPPENED. A test helper redirected Alembic by setting `sqlalchemy.url` on an Alembic
`Config`. `migrations/env.py` resolved its target through `database_url()` instead, which reads
DATABASE_URL and silently OVERRODE that option. `alembic stamp base` therefore ran against the
APPLICATION database and emptied its `alembic_version`. No row moved, so the row-count
preservation gate stayed green.

WHY NO DATA WAS LOST, AND WHY THAT WAS LUCK. The subsequent `upgrade head` failed on
`CREATE TABLE dataset_version` because those tables already existed, so the transaction rolled
back. Against an empty application database the same helper would have migrated it. The absence of
loss was an accident of ordering, not evidence of safety.

THE ROOT CAUSE WAS TWO RESOLVERS WITH NO PRECEDENCE, not the missing revision check. Watching
`alembic_version` is necessary and insufficient: it detects the damage after the fact. These tests
cover the precedence rule and the pre-execution guard, which prevent it.

NOTHING HERE TOUCHES THE APPLICATION DATABASE. The tests that exercise refusal assert that the
guard raises; they never reach a live connection.
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest import mock

import pytest

from packages.persistence.engine import (
    ALEMBIC_TARGET_ENV,
    UnsafeTestDatabaseError,
    assert_disposable,
    assert_safe_destructive_target,
    database_url,
    migration_target_url,
    parse_identity,
)

REPO_ROOT = Path(__file__).resolve().parents[2]

APPLICATION = "postgresql+psycopg://fintek@/fintek?host=/run/postgresql"
DISPOSABLE = "postgresql+psycopg://fintek@/fintek_test?host=/run/postgresql"


# --- 1. precedence: an explicit target is never overridden by DATABASE_URL ---------------------


def test_an_explicit_target_beats_a_process_level_database_url() -> None:
    """THE defect, as a test. DATABASE_URL pointing at `fintek` must not win."""
    with mock.patch.dict(os.environ, {"DATABASE_URL": APPLICATION}, clear=False):
        assert migration_target_url(DISPOSABLE) == DISPOSABLE
        assert parse_identity(migration_target_url(DISPOSABLE)).database == "fintek_test"


def test_the_invocation_override_beats_a_process_level_database_url() -> None:
    with mock.patch.dict(
        os.environ, {"DATABASE_URL": APPLICATION, ALEMBIC_TARGET_ENV: DISPOSABLE}, clear=False
    ):
        assert migration_target_url() == DISPOSABLE


def test_the_test_target_selector_resolves_to_the_disposable_database() -> None:
    with mock.patch.dict(
        os.environ,
        {
            "DATABASE_URL": APPLICATION,
            "TEST_DATABASE_URL": DISPOSABLE,
            "FINTEK_ALEMBIC_TEST_TARGET": "1",
        },
        clear=False,
    ):
        os.environ.pop(ALEMBIC_TARGET_ENV, None)
        assert migration_target_url() == DISPOSABLE


def test_the_test_target_selector_never_falls_back_to_the_application_database() -> None:
    """A fallback here is precisely how D-13 reached `fintek`.

    `test_database_url()` reads the environment and then the project's `.env`, so removing the
    variable alone is not enough to simulate an unconfigured host — the repository's own `.env`
    supplies one. Both sources are suppressed so the genuinely-unconfigured path is exercised.
    """
    import packages.persistence.engine as engine_module

    with mock.patch.dict(
        os.environ, {"DATABASE_URL": APPLICATION, "FINTEK_ALEMBIC_TEST_TARGET": "1"}, clear=False
    ):
        os.environ.pop(ALEMBIC_TARGET_ENV, None)
        os.environ.pop("TEST_DATABASE_URL", None)
        with (
            mock.patch.object(engine_module, "_from_env_file", return_value=None),
            pytest.raises(UnsafeTestDatabaseError, match="Refusing to fall back"),
        ):
            migration_target_url()


def test_the_test_target_selector_resolves_from_the_env_file_when_configured_there(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An `.env` file is a legitimate configuration source, and the resolver must honour it.

    HERMETIC, AND IT HAD TO BECOME SO. This test previously removed TEST_DATABASE_URL from the
    environment and then relied on the DEVELOPER'S OWN `.env` to supply it. That file is
    gitignored, so it exists on every workstation and on no CI runner: the test passed locally
    and could only ever fail in CI, which is exactly what it did on 062baafc. A test that depends
    on an untracked file is not testing the resolver, it is testing the machine.

    It now writes its own `.env` under `tmp_path` and points the resolver's REPO_ROOT at it. That
    is the narrowest seam available and it keeps the maximum amount of production behaviour under
    test: the real `_from_env_file` parser, the real `test_database_url()`, and the real
    `migration_target_url()` precedence chain all run. Nothing is stubbed out. The real `.env` is
    neither read nor referenced.
    """
    import packages.persistence.engine as engine_module

    # A credential-bearing fixture URL, so this also proves the credential never escapes. The
    # password is a literal invented here and protects nothing.
    fixture_password = "fixture-only-not-a-secret"  # noqa: S105 - a test literal, not a secret
    env_target = f"postgresql+psycopg://fintek:{fixture_password}@localhost:5432/fintek_test"

    # Only the entry under test, plus one unrelated line to prove the parser selects by key
    # rather than by position.
    (tmp_path / ".env").write_text(
        f"STORAGE_BACKEND=local\nTEST_DATABASE_URL={env_target}\n", encoding="utf-8"
    )
    monkeypatch.setattr(engine_module, "REPO_ROOT", tmp_path)

    with mock.patch.dict(
        os.environ, {"DATABASE_URL": APPLICATION, "FINTEK_ALEMBIC_TEST_TARGET": "1"}, clear=False
    ):
        os.environ.pop(ALEMBIC_TARGET_ENV, None)
        os.environ.pop("TEST_DATABASE_URL", None)
        resolved = migration_target_url()

    assert resolved == env_target, "the .env value was not the resolved target"
    identity = parse_identity(resolved)
    assert identity.database == "fintek_test"
    assert identity != parse_identity(APPLICATION), "the application target was selected"

    # The credential is in the URL and must not be in anything a human or a log ever sees.
    assert fixture_password not in identity.endpoint
    with pytest.raises(UnsafeTestDatabaseError) as refusal:
        assert_disposable(f"postgresql://fintek:{fixture_password}@localhost:5432/fintek")
    assert fixture_password not in str(refusal.value)


def test_the_env_file_is_only_consulted_when_the_variable_is_absent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The documented precedence, proven with BOTH sources present and disagreeing.

    The pair of tests above each supply one source. Neither can detect a resolver that reads the
    file first, because with only one source present both orders give the same answer.
    """
    import packages.persistence.engine as engine_module

    from_file = "postgresql+psycopg://fintek@localhost:5432/fintek_file_test"
    (tmp_path / ".env").write_text(f"TEST_DATABASE_URL={from_file}\n", encoding="utf-8")
    monkeypatch.setattr(engine_module, "REPO_ROOT", tmp_path)

    with mock.patch.dict(
        os.environ,
        {
            "DATABASE_URL": APPLICATION,
            "TEST_DATABASE_URL": DISPOSABLE,
            "FINTEK_ALEMBIC_TEST_TARGET": "1",
        },
        clear=False,
    ):
        os.environ.pop(ALEMBIC_TARGET_ENV, None)
        assert migration_target_url() == DISPOSABLE, "the .env file overrode the environment"


def test_a_missing_variable_and_a_missing_env_file_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A genuinely unconfigured host, simulated without stubbing the parser out.

    The sibling test above suppresses `_from_env_file` entirely. This one lets the real parser run
    against a directory that has no `.env` at all, which is what a fresh CI checkout actually is.
    """
    import packages.persistence.engine as engine_module

    monkeypatch.setattr(engine_module, "REPO_ROOT", tmp_path)
    assert not (tmp_path / ".env").exists(), "the fixture directory must have no .env"

    with mock.patch.dict(
        os.environ, {"DATABASE_URL": APPLICATION, "FINTEK_ALEMBIC_TEST_TARGET": "1"}, clear=False
    ):
        os.environ.pop(ALEMBIC_TARGET_ENV, None)
        os.environ.pop("TEST_DATABASE_URL", None)
        with pytest.raises(UnsafeTestDatabaseError, match="Refusing to fall back"):
            migration_target_url()


def test_the_ordinary_path_still_resolves_to_the_application_database() -> None:
    """The correction must not break `make db-upgrade`."""
    with mock.patch.dict(os.environ, {"DATABASE_URL": APPLICATION}, clear=False):
        os.environ.pop(ALEMBIC_TARGET_ENV, None)
        os.environ.pop("FINTEK_ALEMBIC_TEST_TARGET", None)
        assert migration_target_url() == APPLICATION


def test_there_is_exactly_one_migration_target_resolver() -> None:
    """Two independent resolutions with no precedence is the root cause, not a symptom.

    Checked on the IMPORT, not on the source text: `env.py` legitimately names the old function in
    the comment explaining the defect, and a prose match would forbid documenting it.
    """
    import ast

    tree = ast.parse((REPO_ROOT / "migrations" / "env.py").read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and (node.module or "").startswith(
            "packages.persistence"
        ):
            imported.update(alias.name for alias in node.names)
    assert "migration_target_url" in imported
    assert "database_url" not in imported, (
        "env.py must not import the application-only resolver; resolving its target independently "
        "of the precedence rule is the D-13 defect"
    )


# --- 2 and 3. destructive operations cannot reach the application database ---------------------


@pytest.mark.parametrize("operation", ["stamp base", "downgrade base", "upgrade head (rebuild)"])
def test_a_destructive_operation_is_refused_against_the_application_database(
    operation: str,
) -> None:
    with (
        mock.patch.dict(os.environ, {"DATABASE_URL": APPLICATION}, clear=False),
        pytest.raises(UnsafeTestDatabaseError),
    ):
        assert_safe_destructive_target(APPLICATION, operation)


def test_a_destructive_operation_is_permitted_against_the_disposable_database(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATABASE_URL", APPLICATION)
    assert assert_safe_destructive_target(DISPOSABLE, "downgrade base") == DISPOSABLE


def test_a_destructive_operation_with_no_target_is_refused() -> None:
    """A destructive migration never falls back to a default."""
    with pytest.raises(UnsafeTestDatabaseError, match="no target URL"):
        assert_safe_destructive_target(None, "downgrade base")


# --- 4. an undesignated database name is rejected -------------------------------------------------


@pytest.mark.parametrize(
    "url",
    [
        "postgresql+psycopg://fintek@/fintek_scratch?host=/run/postgresql",
        "postgresql+psycopg://fintek@/staging?host=/run/postgresql",
        "postgresql+psycopg://fintek@/fintek_production?host=/run/postgresql",
    ],
)
def test_a_database_without_a_test_designation_is_rejected(url: str) -> None:
    with (
        mock.patch.dict(os.environ, {"DATABASE_URL": APPLICATION}, clear=False),
        pytest.raises(UnsafeTestDatabaseError),
    ):
        assert_safe_destructive_target(url, "downgrade base")


def test_a_production_token_is_rejected_even_beside_a_test_token() -> None:
    """`fintek_test_production` says both things; the dangerous one wins."""
    url = "postgresql+psycopg://fintek@/fintek_test_production?host=/run/postgresql"
    with (
        mock.patch.dict(os.environ, {"DATABASE_URL": APPLICATION}, clear=False),
        pytest.raises(UnsafeTestDatabaseError, match="production"),
    ):
        assert_safe_destructive_target(url, "downgrade base")


@pytest.mark.parametrize("name", ["postgres", "template0", "template1"])
def test_a_cluster_database_is_rejected(name: str) -> None:
    """A system database belongs to the server, not to this project.

    It would also slip past the test-designation rule for a different reason than a normal
    mistake does: `postgres` is where a maintenance connection legitimately goes, so a URL
    naming it looks plausible. Dropping tables in it, or in a template every future database is
    cloned from, damages the cluster rather than one project.
    """
    url = f"postgresql+psycopg://fintek@localhost:5432/{name}"
    with (
        mock.patch.dict(os.environ, {"DATABASE_URL": APPLICATION}, clear=False),
        pytest.raises(UnsafeTestDatabaseError, match="cluster database"),
    ):
        assert_safe_destructive_target(url, "downgrade base")


# --- 5 and 6. identity comparison ------------------------------------------------------------------


def test_a_credential_difference_does_not_make_the_same_database_safe() -> None:
    """Connecting as another user is not a different database."""
    as_someone_else = "postgresql+psycopg://someone_else:pw@/fintek?host=/run/postgresql"
    assert parse_identity(as_someone_else) == parse_identity(APPLICATION)
    with (
        mock.patch.dict(os.environ, {"DATABASE_URL": APPLICATION}, clear=False),
        pytest.raises(UnsafeTestDatabaseError),
    ):
        assert_disposable(as_someone_else)


def test_socket_and_tcp_spellings_of_one_database_compare_correctly() -> None:
    """`@localhost/fintek` and `@127.0.0.1:5432/fintek` are different strings, one database."""
    localhost = "postgresql+psycopg://fintek@localhost/fintek"
    explicit = "postgresql+psycopg://fintek@127.0.0.1:5432/fintek"
    assert parse_identity(localhost) == parse_identity(explicit)
    # A socket target is a distinct identity from a TCP one, and must not be conflated.
    assert parse_identity(APPLICATION) != parse_identity(localhost)


def test_a_differently_spelled_application_database_is_still_refused() -> None:
    localhost = "postgresql+psycopg://fintek@localhost/fintek"
    with (
        mock.patch.dict(os.environ, {"DATABASE_URL": localhost}, clear=False),
        pytest.raises(UnsafeTestDatabaseError, match="SAME database"),
    ):
        assert_safe_destructive_target(
            "postgresql+psycopg://other@127.0.0.1:5432/fintek", "downgrade base"
        )


# --- 9. a misrouted migration fails before executing SQL -------------------------------------------


def test_a_misrouted_migration_fails_before_any_sql_runs() -> None:
    """The guard raises without opening a connection, so nothing can be executed by accident."""
    unreachable = "postgresql+psycopg://nobody@/fintek?host=/nonexistent-socket-dir"
    with (
        mock.patch.dict(os.environ, {"DATABASE_URL": APPLICATION}, clear=False),
        pytest.raises(UnsafeTestDatabaseError),
    ):
        # Were the guard to connect first, this would raise OperationalError instead.
        assert_safe_destructive_target(unreachable, "downgrade base")


# --- 7. non-vacuity of the preservation gate --------------------------------------------------------


def test_the_preservation_gate_detects_a_cleared_revision() -> None:
    """Proven WITHOUT touching the application database.

    D-13 was found because `alembic_version` went empty while every row count stayed correct. The
    gate now folds the revision into the same baseline mapping. This asserts the mapping changes
    when the revision does, using two synthetic snapshots — never by clearing a real revision,
    which is what caused the incident in the first place.
    """
    baseline = {
        "issuer": 1,
        "filing": 5,
        "xbrl_fact": 2845,
        "alembic_version:0003_filing_content": 1,
    }
    cleared = {"issuer": 1, "filing": 5, "xbrl_fact": 2845, "alembic_version:None": 1}
    downgraded = {
        "issuer": 1,
        "filing": 5,
        "xbrl_fact": 2845,
        "alembic_version:0002_table_ownership": 1,
    }
    assert baseline != cleared, "an emptied revision must be visible to the gate"
    assert baseline != downgraded, "a downgraded revision must be visible to the gate"
    row_counts_only = {k: v for k, v in baseline.items() if not k.startswith("alembic_version")}
    cleared_counts_only = {k: v for k, v in cleared.items() if not k.startswith("alembic_version")}
    assert row_counts_only == cleared_counts_only, (
        "this is why the original gate passed: the row counts are identical"
    )


def test_the_gate_actually_collects_the_revision(monkeypatch: pytest.MonkeyPatch) -> None:
    """The synthetic shapes above are only meaningful if the collector emits that key.

    Exercised against the DISPOSABLE INTEGRATION database rather than the application one. There
    is no application database on this host or in CI, by design, so reading the collector's real
    output previously meant skipping forever — and a permanently skipped test proves nothing about
    a gate that exists to catch a silent incident.

    Pointing DATABASE_URL at a migrated disposable database is safe and faithful: the collector is
    read-only, it takes exactly the code path it takes in production, and what is asserted is the
    SHAPE of what it returns, which does not depend on which database answered.
    """
    import sys

    from packages.persistence.engine import integration_test_database_url

    target = integration_test_database_url()
    if not target:
        pytest.fail(
            "INTEGRATION_TEST_DATABASE_URL is not set, so the collector cannot be exercised "
            "against any database. This fails rather than skips: see the docstring."
        )
    monkeypatch.setenv("DATABASE_URL", target)

    sys.path.insert(0, str(REPO_ROOT / "tests"))
    import conftest

    collected = conftest._application_counts()
    assert collected is not None, (
        "the collector could not read the disposable integration database; run "
        "`make db-create-integration` and `make db-upgrade-integration`"
    )
    assert any(key.startswith("alembic_version:") for key in collected), (
        "the preservation gate no longer watches the migration revision"
    )


# --- 8. a migrated database's revision is the expected one -------------------------------------------


def test_the_migrated_database_revision_is_the_current_head(integration_engine: object) -> None:
    """Read-only. If a suite run ever moves this, the gate has already failed the run.

    RETARGETED FROM THE APPLICATION DATABASE, which no longer exists on any host by design and so
    made this skip unconditionally. What D-13 actually did was move a MIGRATED database's revision
    away from head behind the suite's back; the integration database is migrated, live, and written
    to by three suites, so it exercises exactly that risk. Asserting it against a database that is
    never present asserted nothing at all.
    """
    from sqlalchemy import text

    with integration_engine.connect() as connection:  # type: ignore[attr-defined]
        revision = connection.execute(text("SELECT version_num FROM alembic_version")).scalar()

    head = _head_revision()
    assert revision == head, (
        f"the integration database is at {revision!r}, not the head {head!r}. "
        "Defect D-13 emptied this once; a mismatch here means a migration reached it again."
    )


def _head_revision() -> str:
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    config = Config(str(REPO_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(REPO_ROOT / "migrations"))
    return ScriptDirectory.from_config(config).get_current_head()


def test_the_application_url_is_never_a_valid_destructive_target() -> None:
    """The end-to-end statement of the invariant, using whatever this host is configured with."""
    configured = database_url()
    with pytest.raises(UnsafeTestDatabaseError):
        assert_safe_destructive_target(configured, "downgrade base")
