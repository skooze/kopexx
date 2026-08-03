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
make check           everything the quality job runs except coverage
make coverage        the coverage gate
make test-no-skips   the suite, failing if anything skips
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

**Everything in the quality job is reproducible locally.** The suite has no environmental
precondition — no database, no network, no credentials — so `make check`, `make coverage` and
`make test-no-skips` behave identically on a runner and on a laptop. Before 2026-08-03 the job
also stood up a PostgreSQL service and ran migrations, and those steps were not reproducible
without a local server; the persistence layer they served is deleted.

A failure that reproduces in the bare environment above but not with your own `.venv` is an
environment or dependency-declaration problem, not a code problem. See the next section.

---

## Failure: `Multiple top-level packages discovered in a flat-layout`

```
error: Multiple top-level packages discovered in a flat-layout:
['prompts', 'packages', 'docs', 'tests']
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
grep -rhoE "^\s*(import|from)\s+[a-zA-Z_][a-zA-Z0-9_]*" packages tests \
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

This is exactly how three database dependencies were once found missing: the package-discovery
failure aborted the install before any import could reveal them. The same check run in the other
direction is what found `pydantic` DECLARED and never imported by a single module — an undeclared
import and an unused declaration are both defects, and only one of them fails CI.

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
   job green. After editing the config, prove it did not blind the scanner: create a throwaway
   repository containing a synthetic credential, copy the config in, and confirm the scan still
   exits non-zero. Sprint 3 did exactly this when the `generic-api-key` rule matched the SEC
   document filename `aapl-20250927.htm`.
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

## Failure: `make test-no-skips` — "tests skipped where all tests were expected to run"

**A skip now has no legitimate cause anywhere.** The suite requires no database, no network and no
credentials, so nothing in it can correctly decide it is unable to run. Before 2026-08-03 "no
reachable PostgreSQL" was an available excuse and a real one; it is gone with the database.

The gate prints each skipped test and its reason:

```
FAIL: 1 test(s) skipped where all tests were expected to run.
  tests/unit/test_example.py::test_something
      Skipped: <the reason the test gave>
```

Diagnose by reading the reason, then fix the TEST — do not silence the gate. A skipped test is
indistinguishable from a passing one in the summary line, which is how two live migration tests
went unexecuted for two sprints.

The hook records skips raised during `setup` AND during `call`. Watching only `setup` misses a
`pytest.skip()` inside a test body, which is how the first version of this gate passed a suite
containing a deliberate skip.

Reproduce locally with the same target CI runs:

```bash
make test-no-skips
```

---

## Failure: "packages.<name> still imports; it was deleted and must not return"

The `Verify the deleted packages are gone` step installs the distribution and asserts that
`footnote_extractor`, `footnote_canonicalizer`, `table_parser`, `persistence` and `dera_notes`
CANNOT be imported.

**Cause.** One of the deleted trees was recreated under `packages/`, or something outside
`packages/` was added to `[tool.setuptools.packages.find]`.

**Fix.** Remove it. A deletion the distribution can undo is not a deletion, and ADR-0017 records
why none of these may come back — as runtime, as a benchmark, as an oracle, or as a fixture
generator. Do not resolve this by narrowing the check.

---

## Failure: "a filing-form allowlist is hardcoded in runtime source"

`tests/architecture/test_architecture.py` parses every module under `packages/` and fails if a
string literal matching an SEC 10-family form appears in evaluated code. Comments and docstrings
are exempt, because the AST distinguishes them.

**Cause.** Someone reintroduced a form allowlist instead of supplying the qualifying set.

**Fix.** Pass the qualifying forms in, from the reviewed contract in
`tests/fixtures/form_family.yaml`. `packages/filing_discovery` shipped a guessed hyphenated list
for four sprints that matched none of the small-business or transition families, and the
reconciliation meant to catch that gap applied the same filter, so both sides agreed and reported
a complete history. ADR-0017 section 8.

---

## Escalation

If CI fails and the cause is not in this runbook: do not amend, force-push, or disable the
failing step. Report the failed job, the exact error, and a recommended correction, then wait for
authorization. `rules.md` sections 15 and 16 apply to the fix commit exactly as to any other.
