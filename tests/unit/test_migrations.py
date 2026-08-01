"""Migration structure and reversibility tests.

Two layers. The structural tests run everywhere and prove the migration is complete and
symmetric. The live upgrade/downgrade tests require a reachable PostgreSQL and SKIP with a clear
reason when there is none, so a missing database never masquerades as a pass.
"""

from __future__ import annotations

import os
import re
import socket
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
MIGRATION = REPO_ROOT / "migrations" / "versions" / "0001_initial_control_plane_schema.py"
VENV_PY = REPO_ROOT / ".venv" / "bin" / "python"
DEFAULT_URL = "postgresql+psycopg://fintek:fintek@localhost:5432/fintek"


def _database_reachable() -> bool:
    url = os.environ.get("DATABASE_URL", DEFAULT_URL)
    parsed = urlparse(url.replace("postgresql+psycopg", "postgresql"))
    host, port = parsed.hostname or "localhost", parsed.port or 5432
    try:
        with socket.create_connection((host, port), timeout=2):
            return True
    except OSError:
        return False


requires_database = pytest.mark.skipif(
    not _database_reachable(),
    reason="no reachable PostgreSQL; live migration tests require one (see SPRINT-0002 blockers)",
)


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
    env.setdefault("DATABASE_URL", DEFAULT_URL)
    return subprocess.run(
        [str(VENV_PY), "-m", "alembic", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        env=env,
        timeout=180,
    )


@pytest.mark.skipif(not VENV_PY.exists(), reason="project virtualenv not present")
def test_upgrade_generates_complete_ddl_offline() -> None:
    """Offline generation proves the migration is complete without needing a server."""
    result = _alembic("upgrade", "head", "--sql")
    assert result.returncode == 0, result.stderr[-2000:]
    sql = result.stdout
    assert sql.count("CREATE TABLE") >= 24
    assert "CREATE TRIGGER" in sql
    assert "FOREIGN KEY" in sql
    assert "CHECK (" in sql


@pytest.mark.skipif(not VENV_PY.exists(), reason="project virtualenv not present")
def test_downgrade_generates_complete_ddl_offline() -> None:
    result = _alembic("downgrade", "0001_initial:base", "--sql")
    assert result.returncode == 0, result.stderr[-2000:]
    sql = result.stdout
    assert sql.count("DROP TABLE") >= 24
    assert "DROP TRIGGER" in sql


# --- live database ------------------------------------------------------------------------------


@requires_database
def test_upgrade_then_downgrade_round_trips() -> None:
    """Apply, verify tables exist, roll back, verify they are gone."""
    from sqlalchemy import create_engine, inspect, text

    url = os.environ.get("DATABASE_URL", DEFAULT_URL)
    engine = create_engine(url)

    assert _alembic("upgrade", "head").returncode == 0
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    assert _model_table_names() <= tables

    with engine.connect() as connection:
        trigger = connection.execute(
            text("SELECT 1 FROM pg_trigger WHERE tgname = 'trg_xbrl_fact_append_only'")
        ).fetchone()
        assert trigger is not None, "append-only trigger was not created"

    assert _alembic("downgrade", "base").returncode == 0
    remaining = set(inspect(engine).get_table_names()) - {"alembic_version"}
    assert not (_model_table_names() & remaining), f"tables survived downgrade: {remaining}"


@requires_database
def test_filed_fact_cannot_be_updated() -> None:
    """FINANCIAL-INVARIANT proven against a real database, not merely asserted in a comment."""
    from sqlalchemy import create_engine, text

    url = os.environ.get("DATABASE_URL", DEFAULT_URL)
    engine = create_engine(url)
    assert _alembic("upgrade", "head").returncode == 0
    with engine.begin() as connection, pytest.raises(Exception, match="append-only"):
        connection.execute(text("UPDATE xbrl_fact SET value_as_filed = '1' WHERE false"))
