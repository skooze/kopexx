"""Migration structure and reversibility tests.

Three layers.

STRUCTURAL tests read the migration source and run everywhere, proving it is complete and
symmetric without a server.

OFFLINE tests generate DDL with `--sql`, which needs no connection.

LIVE tests apply and drop the whole schema. They run against TEST_DATABASE_URL — a disposable
database — never against DATABASE_URL, which holds real loaded facts. See the section header
further down for what happened when they did not.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from packages.persistence.engine import database_url as _database_url  # noqa: E402

MIGRATION = REPO_ROOT / "migrations" / "versions" / "0001_initial_control_plane_schema.py"
# The interpreter that runs alembic in a subprocess. The project virtualenv when there is one,
# and the interpreter running the tests otherwise.
#
# This used to be `.venv/bin/python` unconditionally, guarded by a skipif. CI installs into the job
# environment and has no `.venv`, so all four alembic-invoking tests — including both destructive
# ones — would have SKIPPED there, and `make test-no-skips` would have failed the job with a reason
# that pointed at a missing virtualenv rather than at the real cause. Caught by reproducing the CI
# environment locally, not by reading the workflow.
VENV_PY = (
    REPO_ROOT / ".venv" / "bin" / "python"
    if (REPO_ROOT / ".venv" / "bin" / "python").exists()
    else Path(sys.executable)
)

# Both URLs are resolved by packages/persistence/engine, which is their single home. This module
# used to carry its own copy, whose last-resort default embedded a username and password — a
# credential shape in a tracked file, which this project prohibits — and pointed at localhost:5432
# over TCP. Against a
# cluster using peer authentication over a Unix socket, that default made the reachability probe
# succeed, so the test RAN instead of skipping and then failed on authentication, which reads as a
# broken database rather than a wrong URL.


def _migration_source() -> str:
    return MIGRATION.read_text(encoding="utf-8")


def _model_table_names() -> set[str]:
    sys.path.insert(0, str(REPO_ROOT))
    from packages.persistence import Base

    return set(Base.metadata.tables)


# --- structural ---------------------------------------------------------------------------------


def test_initial_migration_exists() -> None:
    assert MIGRATION.exists(), f"initial migration missing at {MIGRATION}"


def test_migration_creates_every_model_table() -> None:
    """A model table absent from the migration would exist in code and not in the database."""
    source = _migration_source()
    created = set(re.findall(r'op\.create_table\(\s*"([^"]+)"', source))
    missing = _model_table_names() - created
    assert not missing, f"tables defined in models but never created by the migration: {missing}"


def test_migration_drops_every_table_it_creates() -> None:
    """Downgrade must be complete, or a rollback leaves orphaned tables behind."""
    source = _migration_source()
    created = set(re.findall(r'op\.create_table\(\s*"([^"]+)"', source))
    dropped = set(re.findall(r'op\.drop_table\("([^"]+)"\)', source))
    assert created == dropped, (
        f"create/drop asymmetry. only created: {created - dropped}; "
        f"only dropped: {dropped - created}"
    )


def test_downgrade_drops_in_reverse_dependency_order() -> None:
    """Dropping a parent before its children fails on the foreign key."""
    source = _migration_source()
    created = re.findall(r'op\.create_table\(\s*"([^"]+)"', source)
    dropped = re.findall(r'op\.drop_table\("([^"]+)"\)', source)
    assert dropped == list(reversed(created)), "drop order must be the reverse of create order"


def test_migration_declares_no_down_revision() -> None:
    assert re.search(r"^down_revision\s*=\s*None", _migration_source(), re.M)


def test_fact_table_has_append_only_trigger() -> None:
    """FINANCIAL-INVARIANT: immutability of a filed fact is enforced in the database.

    An application-level guarantee is not enough, because a direct SQL session bypasses it.
    """
    source = _migration_source()
    assert "trg_xbrl_fact_append_only" in source
    assert "BEFORE UPDATE ON xbrl_fact" in source
    assert "append-only" in source
    # The downgrade must remove it, or a re-upgrade fails on a duplicate trigger.
    assert "DROP TRIGGER IF EXISTS trg_xbrl_fact_append_only" in source


def test_listing_is_not_unique_on_ticker_alone() -> None:
    """FINANCIAL-INVARIANT: BBBY maps to two different issuers by date.

    A unique constraint on ticker alone would silently merge them.
    """
    sys.path.insert(0, str(REPO_ROOT))
    from packages.persistence import Listing

    for constraint in Listing.__table__.constraints:
        columns = {c.name for c in getattr(constraint, "columns", [])}
        assert columns != {"ticker"}, "listing must never be unique on ticker alone"


def test_summary_has_one_active_version_per_footnote() -> None:
    sys.path.insert(0, str(REPO_ROOT))
    from packages.persistence import FootnoteSummary

    partial_unique = [
        index
        for index in FootnoteSummary.__table__.indexes
        if index.unique and index.dialect_options.get("postgresql", {}).get("where") is not None
    ]
    assert partial_unique, "a partial unique index must enforce one active summary per footnote"


def test_source_block_parent_is_nullable() -> None:
    """An orphaned block must be visible as a defect, not force-attached or dropped."""
    sys.path.insert(0, str(REPO_ROOT))
    from packages.persistence import FootnoteSourceBlock

    assert FootnoteSourceBlock.__table__.c.footnote_id.nullable is True


def test_source_block_records_its_own_attachment_decision() -> None:
    """The grouping audit is per child block, so it must be storable on the child.

    docs/footnotes/canonicalization-algorithm.md requires every attachment to be answerable:
    which stage, on what evidence, against which alternatives. Recording that only on the parent
    footnote cannot answer it, because stages 3 and 6 through 10 decide per child.
    """
    sys.path.insert(0, str(REPO_ROOT))
    from packages.persistence import FootnoteSourceBlock

    columns = FootnoteSourceBlock.__table__.c
    for name in (
        "grouping_method",
        "grouping_confidence",
        "grouping_evidence",
        "competing_candidates",
        "extraction_run_id",
        "grouping_parser_version",
        "grouping_decided_at",
    ):
        assert name in columns, f"footnote_source_block cannot record {name}"


def test_filing_stores_only_non_derivable_completeness_state() -> None:
    """Counts are derived; judgements are stored.

    Eleven of the thirteen counters in docs/footnotes/completeness.md are COUNT() queries over
    child tables. Storing a copy would create a second source of truth that goes stale. The two
    that cannot be recomputed from child rows are stored.
    """
    sys.path.insert(0, str(REPO_ROOT))
    from packages.persistence import Filing

    columns = Filing.__table__.c
    assert "completeness_confidence" in columns
    assert "reconciliation_status" in columns
    for derivable in (
        "canonical_footnotes_extracted",
        "source_blocks_associated",
        "source_blocks_orphaned",
        "summaries_accepted",
    ):
        assert derivable not in columns, (
            f"{derivable} is a COUNT() over child rows; storing it duplicates the source of truth"
        )


def test_reconciliation_status_is_constrained() -> None:
    """A TOC mismatch must be recordable as MISMATCH, and nothing outside the vocabulary."""
    sys.path.insert(0, str(REPO_ROOT))
    from packages.persistence import Filing

    checks = " ".join(str(c.sqltext) for c in Filing.__table__.constraints if hasattr(c, "sqltext"))
    assert "RECONCILED" in checks and "MISMATCH" in checks and "NOT_ATTEMPTED" in checks


def test_llm_invocation_constrains_content_format() -> None:
    """LLM-SERIALIZATION-INVARIANT enforced at the database level."""
    sys.path.insert(0, str(REPO_ROOT))
    from packages.persistence import LlmInvocation

    checks = " ".join(
        str(c.sqltext) for c in LlmInvocation.__table__.constraints if hasattr(c, "sqltext")
    )
    assert "plain_text" in checks and "yaml" in checks
    assert "json" not in checks.lower().replace("jsonb", "")


# --- offline SQL generation ---------------------------------------------------------------------


def _alembic(*args: str) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env.setdefault("DATABASE_URL", _database_url())
    return subprocess.run(
        [str(VENV_PY), "-m", "alembic", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        env=env,
        timeout=180,
    )


def test_upgrade_generates_complete_ddl_offline() -> None:
    """Offline generation proves the migration is complete without needing a server."""
    result = _alembic("upgrade", "head", "--sql")
    assert result.returncode == 0, result.stderr[-2000:]
    sql = result.stdout
    assert sql.count("CREATE TABLE") >= 24
    assert "CREATE TRIGGER" in sql
    assert "FOREIGN KEY" in sql
    assert "CHECK (" in sql


def test_downgrade_generates_complete_ddl_offline() -> None:
    result = _alembic("downgrade", "head:base", "--sql")
    assert result.returncode == 0, result.stderr[-2000:]
    sql = result.stdout
    assert sql.count("DROP TABLE") >= 24
    assert "DROP TRIGGER" in sql


# --- the offline range must not go stale ----------------------------------------------------------
#
# `make migration-check` generated `downgrade 0001_initial:base` for as long as 0001 was the only
# revision. Adding 0002 did not break it and did not fail it — alembic renders only the revisions
# inside the range it is given, so the target kept exiting 0 while generating 25 statements, none of
# which dropped an ownership column, constraint, or index. A reversibility check that silently stops
# covering the newest migration is worse than none: it reports the property it no longer tests.
#
# The fix is a derived range, `head:base`. These tests hold it there.


def _script_directory():
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    return ScriptDirectory.from_config(Config(str(REPO_ROOT / "alembic.ini")))


def _all_revisions() -> list[str]:
    """Every revision from head down to base, newest first. Derived, never listed."""
    script = _script_directory()
    return [
        revision.revision for revision in script.walk_revisions("base", script.get_current_head())
    ]


def _migration_check_recipe() -> list[str]:
    """The command lines of the Makefile's migration-check target.

    Read from the Makefile because the Makefile is the single definition of the suite: a test that
    reimplemented the command would pass while CI ran something else.
    """
    lines = (REPO_ROOT / "Makefile").read_text(encoding="utf-8").splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith("migration-check:"))
    recipe = []
    for line in lines[start + 1 :]:
        if not line.startswith("\t"):
            break
        recipe.append(line.strip())
    assert recipe, "migration-check has no recipe"
    return recipe


def test_migration_check_names_no_revision_id() -> None:
    """THE ANTI-DRIFT GUARD. A hardcoded revision is how the previous range went stale.

    Any migration id appearing in the recipe would pin the range to the revisions that exist today,
    and the next migration would be excluded without a single test failing.
    """
    recipe = " ".join(_migration_check_recipe())
    for revision in _all_revisions():
        assert revision not in recipe, (
            f"migration-check hardcodes revision {revision}; use a derived range such as head:base"
        )
    assert "head:base" in recipe, "the downgrade range must start at head"
    assert "base:head" in recipe, "the upgrade range must end at head"


def test_migration_check_downgrade_starts_at_the_current_head() -> None:
    """The range the Makefile uses must resolve to the head alembic reports right now."""
    head = _script_directory().get_current_head()
    assert head == "0002_table_ownership", "head moved; the expectations below need re-measuring"

    from_head = _alembic("downgrade", "head:base", "--sql")
    from_explicit = _alembic("downgrade", f"{head}:base", "--sql")
    assert from_head.returncode == 0, from_head.stderr[-2000:]
    assert from_explicit.returncode == 0, from_explicit.stderr[-2000:]
    assert from_head.stdout == from_explicit.stdout


def test_every_revision_contributes_downgrade_sql() -> None:
    """Not "the newest one is included" — every revision between head and base."""
    result = _alembic("downgrade", "head:base", "--sql")
    assert result.returncode == 0, result.stderr[-2000:]

    revisions = _all_revisions()
    assert len(revisions) >= 2, "with one revision this test cannot detect an omitted range"
    for revision in revisions:
        assert f"Running downgrade {revision}" in result.stdout, (
            f"{revision} contributes no downgrade SQL; the offline range excludes it"
        )


def test_the_offline_downgrade_removes_the_table_ownership_objects() -> None:
    """0002's own operations, named. This is what the previous range omitted entirely."""
    sql = _alembic("downgrade", "head:base", "--sql").stdout

    assert "DROP INDEX ix_footnote_table_unresolved" in sql
    for constraint in (
        "ck_footnote_table_ownership_matches_footnote",
        "ck_footnote_table_ownership_kind_is_known",
    ):
        assert f"DROP CONSTRAINT {constraint}" in sql
    for column in ("ownership_evidence", "ownership_method", "ownership_kind"):
        assert f"DROP COLUMN {column}" in sql

    # Reverse dependency order: 0002 unwinds before 0001 drops the table it altered.
    assert sql.index("Running downgrade 0002_table_ownership") < sql.index(
        "Running downgrade 0001_initial"
    )
    assert sql.index("DROP COLUMN ownership_kind") < sql.index("DROP TABLE footnote_table")


def test_the_superseded_range_is_demonstrably_insufficient() -> None:
    """Non-vacuity. The old command must be shown to omit what the new one covers.

    Without this, `head:base` passing proves only that some range works, not that the range it
    replaced was broken.
    """
    superseded = _alembic("downgrade", "0001_initial:base", "--sql")
    corrected = _alembic("downgrade", "head:base", "--sql")
    assert superseded.returncode == 0, "the old command exited non-zero for an unrelated reason"

    assert "ownership_kind" not in superseded.stdout
    assert "Running downgrade 0002_table_ownership" not in superseded.stdout
    assert "ownership_kind" in corrected.stdout
    assert len(corrected.stdout) > len(superseded.stdout)


# --- live database, ISOLATED TARGET ---------------------------------------------------------------
#
# Everything below runs against TEST_DATABASE_URL, never DATABASE_URL. Both tests apply and drop
# the whole schema, and the application database holds real loaded facts.
#
# The earlier arrangement pointed them at DATABASE_URL. `alembic downgrade base` then dropped every
# application table on this development host, deleting 2,845 loaded facts, while `make check`
# reported green. Skipping when data was present stopped the deletion but left the tests unrun,
# which is the failure this suite has already made twice. A separate target runs them AND keeps the
# data.


def _alembic_against(url: str, *args: str) -> subprocess.CompletedProcess[str]:
    """Run alembic against an explicit URL.

    The URL is passed rather than inherited, so a destructive command can never silently pick up
    the application database from the ambient environment.
    """
    env = dict(os.environ)
    env["DATABASE_URL"] = url
    return subprocess.run(
        [str(VENV_PY), "-m", "alembic", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        env=env,
        timeout=180,
    )


def _reset_to_base(url: str) -> None:
    """Bring the disposable database to a known empty state.

    A run killed midway leaves the schema at an unknown revision, and `upgrade head` from there
    proves nothing about a migration applying to an empty database.
    """
    _alembic_against(url, "downgrade", "base")


def test_the_destructive_target_is_not_the_application_database(test_database_url: str) -> None:
    """The invariant, asserted before either destructive test is allowed to touch anything.

    This is the guard, not a restatement of it: `assert_disposable` already ran inside the fixture
    and would have failed the test. What this adds is an explicit, readable record that the two
    URLs resolve to different databases, and that the difference is not merely one of spelling.
    """
    from packages.persistence.engine import parse_identity

    application = parse_identity(_database_url())
    target = parse_identity(test_database_url)

    assert target != application, (
        f"destructive tests would run against the application database {application.endpoint}"
    )
    assert target.database != application.database
    assert "test" in target.database.lower()


def test_upgrade_then_downgrade_round_trips(
    test_database_url: str,
    disposable_engine: object,
) -> None:
    """Apply, verify the tables and the trigger exist, roll back, verify they are gone.

    DESTRUCTIVE. Runs only against the disposable database, whose separateness the fixture proved
    before this body ran.
    """
    from sqlalchemy import inspect, text

    _reset_to_base(test_database_url)

    upgrade = _alembic_against(test_database_url, "upgrade", "head")
    assert upgrade.returncode == 0, upgrade.stderr[-2000:]

    tables = set(inspect(disposable_engine).get_table_names())
    assert _model_table_names() <= tables, f"missing after upgrade: {_model_table_names() - tables}"

    with disposable_engine.connect() as connection:  # type: ignore[attr-defined]
        trigger = connection.execute(
            text("SELECT 1 FROM pg_trigger WHERE tgname = 'trg_xbrl_fact_append_only'")
        ).fetchone()
        assert trigger is not None, "append-only trigger was not created"

    downgrade = _alembic_against(test_database_url, "downgrade", "base")
    assert downgrade.returncode == 0, downgrade.stderr[-2000:]

    remaining = set(inspect(disposable_engine).get_table_names()) - {"alembic_version"}
    assert not (_model_table_names() & remaining), f"tables survived downgrade: {remaining}"


def test_filed_fact_cannot_be_updated(
    test_database_url: str,
    disposable_engine: object,
) -> None:
    """FINANCIAL-INVARIANT proven against a real database, not merely asserted in a comment.

    CORRECTED THREE TIMES, each correction exposed by the previous one.

    1. The original body was:

           with engine.begin() as connection, pytest.raises(Exception, match="append-only"):
               connection.execute(text("UPDATE xbrl_fact SET value_as_filed = '1' WHERE false"))

       `WHERE false` matches zero rows, and the guard is a FOR EACH ROW trigger, so it never fired
       and the statement succeeded. The test could not fail no matter what the schema did, and had
       never run, because no PostgreSQL was reachable until Sprint 3.

    2. The replacement inserted its fixture using Apple's real CIK and accession, both UNIQUE, so
       it failed the moment the application database held a real load. It had only ever passed
       because the destructive round-trip test ran first and emptied every table — an inter-test
       dependency invisible while the database was always empty.

    3. It ran against the application database at all. Now it runs against the disposable one and
       builds its own schema, so it depends on no other test and destroys no real data.
    """
    import uuid

    from sqlalchemy import text

    _reset_to_base(test_database_url)
    upgrade = _alembic_against(test_database_url, "upgrade", "head")
    assert upgrade.returncode == 0, upgrade.stderr[-2000:]

    issuer_id, filing_id, fact_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    original = "416161000000"
    cik, accession = "9999999998", "9999999998-25-000001"
    engine = disposable_engine

    with engine.begin() as connection:  # type: ignore[attr-defined]
        connection.execute(
            text(
                "INSERT INTO issuer (issuer_id, cik, legal_name, is_active) "
                "VALUES (:i, :cik, 'Trigger Fixture Corp', true)"
            ),
            {"i": issuer_id, "cik": cik},
        )
        connection.execute(
            text(
                "INSERT INTO filing (filing_id, issuer_id, cik, accession, form, filing_date,"
                " is_amendment, is_xbrl, is_inline_xbrl, era, processing_state,"
                " footnote_status, reconciliation_status)"
                " VALUES (:f, :i, :cik, :a, '10-K', '2025-10-31',"
                " false, true, true, 'inline_xbrl', 'DISCOVERED', 'NOT_STARTED', 'NOT_ATTEMPTED')"
            ),
            {"f": filing_id, "i": issuer_id, "cik": cik, "a": accession},
        )
        connection.execute(
            text(
                "INSERT INTO xbrl_fact (fact_id, issuer_id, cik, filing_id, accession, form,"
                " filing_date, taxonomy, namespace, concept, value_as_filed, unit, scale,"
                " sign, period_type, period_start, period_end, source_dataset, filed_at,"
                " is_latest_selected, validation_status)"
                " VALUES (:x, :i, :cik, :f, :a, '10-K',"
                " '2025-10-31', 'us-gaap', 'http://fasb.org/us-gaap/2025', 'Revenues',"
                " :v, 'USD', 1, 1, 'duration', '2024-09-29', '2025-09-27', 'trigger_fixture',"
                " '2025-10-31T00:00:00Z', true, 'VALID')"
            ),
            {
                "x": fact_id,
                "i": issuer_id,
                "f": filing_id,
                "v": original,
                "cik": cik,
                "a": accession,
            },
        )

    # Confirm the row is really there and committed before attacking it. Without this the test
    # could pass against an empty table, which is exactly how the original failed.
    with engine.connect() as connection:  # type: ignore[attr-defined]
        before = connection.execute(
            text("SELECT value_as_filed FROM xbrl_fact WHERE fact_id = :x"), {"x": fact_id}
        ).scalar()
    assert before == original, "the fact was not committed; the update would target no row"

    # The filed value is immutable. A restatement appends a new row instead.
    with engine.begin() as connection, pytest.raises(Exception, match="append-only"):  # type: ignore[attr-defined]
        connection.execute(
            text("UPDATE xbrl_fact SET value_as_filed = '1' WHERE fact_id = :x"), {"x": fact_id}
        )

    with engine.begin() as connection:  # type: ignore[attr-defined]
        stored = connection.execute(
            text("SELECT value_as_filed FROM xbrl_fact WHERE fact_id = :x"), {"x": fact_id}
        ).scalar()
        assert stored == original, "the filed value changed despite the trigger"

        # The guard protects the FILED value, not the whole row: selection bookkeeping must still
        # be updatable or restatement handling could never record a winner.
        connection.execute(
            text("UPDATE xbrl_fact SET is_latest_selected = false WHERE fact_id = :x"),
            {"x": fact_id},
        )

    _reset_to_base(test_database_url)
