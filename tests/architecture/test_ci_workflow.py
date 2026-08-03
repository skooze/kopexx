"""Invariants of the CI workflow itself, enforced by parsing it.

Every check here reads the PARSED YAML — the `uses:`, `with:`, and `permissions:` values GitHub
actually acts on — rather than searching the file for text. A comment promising `fetch-depth: 0`
scans identically to the setting, and only one of them clones any history.

WHY THIS FILE EXISTS. CI ran for four commits emitting a Node 20 deprecation notice on every step
that used `actions/checkout@v4` or `actions/setup-python@v5`. Nothing failed, so nothing surfaced
it until a human read the raw log. A deprecated runtime is not a formatting preference: when
GitHub retires it, the affected steps stop working and the whole suite goes with them.
"""

from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

import pytest
from ruamel.yaml import YAML

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"

pytestmark = pytest.mark.architecture

# The FIRST major of each official action that declares `runs.using: node24`, verified against the
# action.yml at each tag in the official repository rather than taken from release prose:
#
#   actions/checkout       v4 node20   v5 node24   v6 node24   v7 node24
#   actions/setup-python   v5 node20   v6 node24   v7 node24
#
# A floor rather than an exact version. Pinning the exact current major would fail on the next
# legitimate bump, which is a different problem from reintroducing a retired runtime.
MINIMUM_MAJOR = {
    "actions/checkout": 5,
    "actions/setup-python": 6,
}


@pytest.fixture(scope="module")
def workflow() -> dict:
    return YAML(typ="safe", pure=True).load(WORKFLOW.read_text(encoding="utf-8"))


def _steps(workflow: dict) -> list[tuple[str, dict]]:
    """Every step in every job, labelled with its job name."""
    steps = []
    for job_name, job in workflow["jobs"].items():
        for step in job.get("steps", []):
            steps.append((job_name, step))
    return steps


def _action_uses(workflow: dict) -> list[tuple[str, str, str]]:
    """(job, action, version) for every `uses:` naming an official action we pin a floor for."""
    found = []
    for job_name, step in _steps(workflow):
        uses = step.get("uses")
        if not uses:
            continue
        action, _, version = uses.partition("@")
        if action in MINIMUM_MAJOR:
            found.append((job_name, action, version))
    return found


def test_the_workflow_parses_and_has_both_jobs(workflow: dict) -> None:
    """Anti-vacuity. Every check below reads this structure; an empty one enforces nothing."""
    assert set(workflow["jobs"]) == {"quality", "security"}
    assert len(_steps(workflow)) >= 15


def test_every_official_action_is_used_at_least_once(workflow: dict) -> None:
    """A guard over actions the workflow stopped using would silently enforce nothing."""
    used = {action for _, action, _ in _action_uses(workflow)}
    assert used == set(MINIMUM_MAJOR), f"expected {set(MINIMUM_MAJOR)}, workflow uses {used}"
    assert len(_action_uses(workflow)) == 4, "two checkouts and two Python setups"


def test_no_official_action_runs_on_a_deprecated_node_runtime(workflow: dict) -> None:
    """THE GUARD. checkout below v5 and setup-python below v6 declare node20."""
    for job_name, action, version in _action_uses(workflow):
        assert version, f"{job_name}: {action} is used with no version at all"
        assert version.startswith("v"), (
            f"{job_name}: {action}@{version} is not a reviewed major tag; "
            "this repository pins official actions to a major tag"
        )
        major = int(version[1:].split(".")[0])
        assert major >= MINIMUM_MAJOR[action], (
            f"{job_name}: {action}@{version} runs on Node 20, which GitHub has deprecated. "
            f"Use v{MINIMUM_MAJOR[action]} or later."
        )


def test_official_actions_come_from_the_official_repositories(workflow: dict) -> None:
    """A fork or a lookalike namespace running in CI has the same access the real one would."""
    for job_name, step in _steps(workflow):
        uses = step.get("uses")
        if uses and not uses.startswith("./"):
            owner = uses.split("/")[0]
            assert owner == "actions", (
                f"{job_name} uses a third-party action {uses!r}. Third-party tooling in this "
                "workflow is installed from a checksum-verified release instead."
            )


def test_the_security_checkout_still_fetches_full_history(workflow: dict) -> None:
    """SECURITY-INVARIANT. A shallow clone cannot be scanned for secrets in history.

    Asserted on the parsed value because an action bump is exactly the kind of edit that drops a
    `with:` block, and the resulting scan would still pass while inspecting one commit.
    """
    checkouts = [
        step
        for job_name, step in _steps(workflow)
        if job_name == "security" and str(step.get("uses", "")).startswith("actions/checkout@")
    ]
    assert len(checkouts) == 1
    assert checkouts[0].get("with", {}).get("fetch-depth") == 0


def test_python_is_pinned_to_the_supported_version_in_both_jobs(workflow: dict) -> None:
    setups = [
        step
        for _, step in _steps(workflow)
        if str(step.get("uses", "")).startswith("actions/setup-python@")
    ]
    assert len(setups) == 2
    for step in setups:
        assert str(step.get("with", {}).get("python-version")) == "3.12"


def test_the_workflow_keeps_least_privilege_permissions(workflow: dict) -> None:
    """Neither job writes to the repository, opens issues, or publishes packages."""
    assert workflow["permissions"] == {"contents": "read"}
    for _, job in workflow["jobs"].items():
        assert "permissions" not in job or job["permissions"] == {"contents": "read"}


# --- no database, and no way for one to come back ----------------------------------------------
#
# These five checks replaced five that verified the OPPOSITE: that the job stood up a postgres:18
# service, created two disposable databases, proved their identities distinct, and applied Alembic
# migrations before any test ran. Those were correct while an application schema existed. It does
# not: the ORM, the migrations, and every test that opened a connection are deleted. The guard is
# inverted rather than dropped, because "no database" is exactly the kind of property that erodes
# by accident — one service block copied back from an old workflow and the suite is coupled to a
# server again.


def _database_name(url: str) -> str:
    return urlparse(url.replace("postgresql+psycopg", "postgresql")).path.lstrip("/")


def test_no_job_stands_up_a_database_service(workflow: dict) -> None:
    """No surviving test opens a database connection, so no job may provision one."""
    for job_name, job in workflow["jobs"].items():
        assert "services" not in job, (
            f"{job_name} declares a service container. The application persistence layer and every "
            "database test were deleted; a service here is a dependency nothing needs."
        )


def test_no_job_configures_a_database_url(workflow: dict) -> None:
    """Not the application database, and not a disposable one either.

    Checked on every environment mapping in the file rather than on a known set of names, so a
    differently-named variable carrying a connection string is caught too.
    """
    scopes: list[tuple[str, dict]] = [("workflow", workflow.get("env") or {})]
    for job_name, job in workflow["jobs"].items():
        scopes.append((job_name, job.get("env") or {}))
        for step in job.get("steps", []):
            scopes.append((f"{job_name} step", step.get("env") or {}))

    for scope, env in scopes:
        for variable, value in env.items():
            assert "postgres" not in str(value).lower(), (
                f"{scope}: {variable} carries a PostgreSQL connection string "
                f"({_database_name(str(value))!r}); ordinary CI has no database"
            )
            assert "DATABASE_URL" not in variable, f"{scope}: {variable} names a database"


def test_no_step_runs_a_deleted_database_or_migration_target(workflow: dict) -> None:
    """The Make targets these steps invoked no longer exist; a reference would fail obscurely."""
    deleted_targets = (
        "db-create-test",
        "db-create-integration",
        "db-upgrade",
        "db-upgrade-test",
        "db-upgrade-integration",
        "db-verify-isolation",
        "migration-check",
        "test-integration",
    )
    for job_name, step in _steps(workflow):
        command = str(step.get("run", ""))
        for target in deleted_targets:
            assert f"make {target}" not in command, (
                f"{job_name} invokes `make {target}`, which was deleted with the application "
                "database and its migrations"
            )


def test_the_quality_job_proves_the_deleted_packages_cannot_be_imported(workflow: dict) -> None:
    """A deletion that the distribution can undo is not a deletion.

    The rejected deterministic parser, the application ORM and the DERA fact loader must fail to
    import from an installed distribution. Asserting it in CI is what stops a reintroduction from
    being silent.
    """
    commands = " ".join(str(step.get("run", "")) for step in workflow["jobs"]["quality"]["steps"])
    for module in (
        "footnote_extractor",
        "footnote_canonicalizer",
        "table_parser",
        "persistence",
        "dera_notes",
    ):
        assert module in commands, f"CI does not prove packages.{module} is absent"


def test_the_zero_skip_gate_still_runs(workflow: dict) -> None:
    """The gate that survived the database removal, and is stronger without it.

    Every skip previously had a legitimate cause available — no reachable PostgreSQL. The suite now
    has no environmental precondition at all, so a skip here has no legitimate cause whatsoever.
    """
    commands = [str(step.get("run", "")) for step in workflow["jobs"]["quality"]["steps"]]
    assert any("make test-no-skips" in c for c in commands), "the zero-skip gate is not run"
    assert any("make test-unit" in c for c in commands)
    assert any("make test-architecture" in c for c in commands)
    assert any("make coverage" in c for c in commands)


def test_the_workflow_runs_the_makefile_rather_than_its_own_commands(workflow: dict) -> None:
    """rules.md section 17: the Makefile is the single definition of the validation suite.

    The two exceptions are explicit — installing the package, and installing the checksum-verified
    third-party scanner — because neither is part of the suite the Makefile defines.
    """
    allowed_without_make = ("pip install", "pip-audit", "gitleaks", "python -c", "curl", "set -e")
    for job_name, step in _steps(workflow):
        command = str(step.get("run", "")).strip()
        if not command:
            continue
        if "make " in command:
            continue
        assert any(marker in command for marker in allowed_without_make), (
            f"{job_name} runs a validation command directly instead of a make target: {command!r}"
        )


def test_ordinary_ci_acquires_no_aws_identity(workflow: dict) -> None:
    """Restated on the parsed structure. The text-level guard lives in test_aws_identity.py."""
    for job_name, step in _steps(workflow):
        uses = str(step.get("uses", ""))
        assert "aws-actions/" not in uses, f"{job_name} configures AWS identity"
        assert "role-to-assume" not in str(step.get("with", {}))
    assert "id-token" not in str(workflow.get("permissions", {}))
