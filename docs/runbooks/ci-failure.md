# Runbook: CI Failure

IMPLEMENTATION STATUS: IMPLEMENTED
WORKFLOW: `.github/workflows/ci.yml`
COMMAND DEFINITIONS: `Makefile` — CI invokes these targets, never its own copies

---

## Principle

Every CI command is a Makefile target. **Reproduce a CI failure by running the same target
locally**, not by reading the workflow and retyping the command. If you find yourself retyping,
the workflow has drifted and that is itself the defect to fix.

```
make check            everything the quality job runs except coverage
make coverage         the coverage gate
make migration-check  offline Alembic upgrade and downgrade
```

Tools resolve from `./.venv/bin` when present and from `PATH` otherwise, so the same target
behaves identically locally and on a runner.

---

## Reproducing the quality job exactly

CI installs into a bare environment. To match it, hide the project virtualenv so the Makefile
falls back to `PATH`:

```bash
python3 -m venv /tmp/ci-venv
/tmp/ci-venv/bin/pip install -e ".[dev]"
mv .venv .venv-hidden
PATH=/tmp/ci-venv/bin:$PATH make check
mv .venv-hidden .venv          # ALWAYS restore
```

A failure that reproduces this way but not with `make check` alone is an environment or
dependency-declaration problem, not a code problem. See the next section.

---

## Failure: `Multiple top-level packages discovered in a flat-layout`

```
error: Multiple top-level packages discovered in a flat-layout:
['prompts', 'packages', 'artifacts', 'migrations', 'metric_definitions']
```

Setuptools cannot guess which root directories are Python packages.

**Cause.** Something removed or broke `[tool.setuptools.packages.find]` in `pyproject.toml`, or a
new top-level directory was added.

**Fix.** Restore explicit discovery. Do not switch to automatic discovery and do not move
directories to satisfy it:

```toml
[tool.setuptools.packages.find]
include = ["packages*"]
namespaces = false
```

**Note.** A local checkout also contains the gitignored `var/`, so the local error lists one more
directory than CI does. That difference is expected and is a reason never to rely on
auto-discovery here.

---

## Failure: `ModuleNotFoundError` in CI but not locally

The project virtualenv has accumulated a package that `pyproject.toml` does not declare. CI
installs only what is declared, so it fails where you do not.

**Diagnose:**

```bash
# every third-party import in the repository
grep -rhoE "^\s*(import|from)\s+[a-zA-Z_][a-zA-Z0-9_]*" packages scripts migrations tests \
  --include=*.py | sed -E 's/^\s*(import|from)\s+//' | sort -u
```

Compare against `[project].dependencies`. Anything imported by shipped code and missing from that
list is the bug.

**Fix.** Declare it in `pyproject.toml`, then prove it in a clean environment before pushing:

```bash
python3 -m venv /tmp/verify && /tmp/verify/bin/pip install -e ".[dev]"
/tmp/verify/bin/python -c "import packages"
/tmp/verify/bin/python -m pytest tests
```

This is exactly how `sqlalchemy`, `alembic`, and `psycopg` were found missing: the
package-discovery failure aborted the install before any import could reveal them.

---

## Failure: gitleaks

### `unknown revision` naming the parent of the root commit

```
git log -p -U0 --no-merges --first-parent <root>^..<head>
fatal: ambiguous argument '<root>^..<head>': unknown revision
scanned ~0 bytes (0)
```

**Cause.** Something reverted the workflow to the gitleaks GitHub Action, which derives a commit
range from the push event. On a first push the "before" SHA is all zeros and resolves to the
parent of the root commit, which cannot exist.

**Fix.** Use the pinned CLI over all reachable history, never an event-derived range:

```bash
gitleaks git . --log-opts="--all --full-history" --redact --no-banner --exit-code 1
gitleaks dir . --redact --no-banner --exit-code 1
```

and keep `fetch-depth: 0` on checkout. A shallow clone has no history to scan.

### `leaks found: N`

A real or apparent secret is in the repository.

1. **Do not** print the finding into a shared channel; the log is redacted for a reason.
2. Identify it locally: `gitleaks git . --log-opts="--all --full-history" --report-path /tmp/gl.json`
3. If it is a **real credential**: rotate it first. Rotation comes before any repository cleanup,
   because the value is already published to everyone with read access.
4. If it is a **false positive**: add a narrowly scoped entry to `.gitleaks.toml` covering that
   path and rule only. **Never** disable a rule globally and never delete the finding to make the
   job green.
5. Record the decision in the sprint record.

### `scanned ~0 bytes`

Treat as a **failure to scan**, never as a pass. The scanner did not inspect anything. Check
`fetch-depth` and the `--log-opts` argument.

---

## Failure: `pip-audit`

The dependency scan is **enforcing**, not advisory.

```
Found N known vulnerabilities in M packages
```

**Fix.** Upgrade the affected dependency and re-run. If no fixed version exists, do not suppress
the check silently: record the advisory, the exposure, and the mitigation in the risk register
and request an explicit exception.

If the failure is instead `fintek: Dependency not found on PyPI`, the `--skip-editable` flag was
dropped. The local project is not published and must be excluded.

---

## Failure: coverage below the gate

```
Required test coverage of 85% not reached
```

Add the missing tests. **Do not** lower `--cov-fail-under`, and do not add packages to the
coverage exclusion list to raise the percentage. `rules.md` section 16 prohibits weakening a gate
to make a commit pass.

---

## Failure: the two live migration tests

They **skip**, they do not fail, when no PostgreSQL is reachable:

```
SKIPPED - no reachable PostgreSQL; live migration tests require one
```

This is expected until Sprint 3 stands up a database. A skip is reported as a skip. If they ever
report as passes without a database, that is a defect in the guard.

---

## Escalation

If CI fails and the cause is not in this runbook: do not amend, force-push, or disable the
failing step. Report the failed job, the exact error, and a recommended correction, then wait for
authorization. `rules.md` sections 15 and 16 apply to the fix commit exactly as to any other.
