"""Shared test fixtures and the zero-skip gate.

The gate stops a skip from reading as a pass. "203 passed, 2 skipped" is what this suite reported
for two sprints while the only two tests exercising a live schema had never once executed.

WHAT WAS REMOVED HERE, AND WHY IT IS NOT A WEAKENING. This file previously also owned the
disposable-database fixtures and an application-preservation gate that compared row counts in the
`fintek` database before and after every run. Both existed to protect an application PostgreSQL
schema that has been deleted: there is no application database, no ORM, no migration, and no
destructive database test left in this repository. A guard watching a database that cannot exist is
the vacuity trap this project has been bitten by twice, not a safety net. The rule those fixtures
enforced survives in `rules.md` as a forward obligation on whatever persistence is designed once
real model artifacts exist.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES


@pytest.fixture
def valid_user_agent() -> str:
    return "FinTek Research contact@example.com"


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


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    """Fail an otherwise green run when a test skipped where all tests were expected to run.

    Off unless `FINTEK_FORBID_SKIPS` is set, so a developer running a focused subset still gets a
    useful local run. `make test-no-skips` sets it; CI runs that target.
    """
    if not os.environ.get("FINTEK_FORBID_SKIPS") or not _skipped:
        return

    writer = session.config.get_terminal_writer()
    writer.line("")
    writer.line(f"FAIL: {len(_skipped)} test(s) skipped where all tests were expected to run.")
    for nodeid, reason in _skipped:
        writer.line(f"  {nodeid}")
        writer.line(f"      {reason}")
    session.exitstatus = 1
