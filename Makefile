# FinTek developer commands.
#
# These targets are the SINGLE definition of the validation suite. CI invokes the same targets
# rather than repeating the commands, so local pre-commit validation and the GitHub Actions run
# can never drift apart. rules.md section 17 requires exactly this.
#
# Tools resolve from the project virtualenv when one exists, and from PATH otherwise, so the same
# target works locally and on a CI runner that installed into the job environment.
VENV_BIN := $(if $(wildcard ./.venv/bin/python),./.venv/bin/,)
RUFF   := $(VENV_BIN)ruff
MYPY   := $(VENV_BIN)mypy
PYTHON := $(VENV_BIN)python
PYTEST := $(PYTHON) -m pytest
ALEMBIC := $(VENV_BIN)alembic

# Every Python path in the repository. Formatting and linting cover all four.
PY_PATHS := packages tests scripts migrations

# Type checking covers shipped source only. tests/ is excluded deliberately: it exercises
# SQLAlchemy internals where `Model.__table__` is typed as FromClause, producing six errors that
# are typing friction rather than defects. Silencing them with blanket ignores would weaken the
# check for the source that matters. Revisit if the test suite grows logic worth type-checking.
MYPY_PATHS := packages scripts migrations

# Where a suite run records its own output, so the counts can be reported without running the
# suite a second time. Gitignored.
TEST_LOG := .pytest-last-run.log

COV_PACKAGES := --cov=packages.sec_identity --cov=packages.configuration \
                --cov=packages.sec_client --cov=packages.storage \
                --cov=packages.llm_gateway --cov=packages.dera_notes \
                --cov=packages.observability --cov=packages.footnote_extractor \
                --cov=packages.footnote_canonicalizer --cov=packages.table_parser

.PHONY: help install fmt fmt-check lint typecheck test test-unit test-integration \
        test-architecture test-security test-no-skips coverage migration-check db-upgrade \
        db-create-test db-upgrade-test db-verify-isolation test-summary \
        check up down clean

help:
	@echo "install          create the virtualenv and install dependencies"
	@echo "check            the sprint gate: format, lint, types, tests, migrations"
	@echo "fmt / fmt-check  apply or verify formatting  ($(PY_PATHS))"
	@echo "lint             ruff                        ($(PY_PATHS))"
	@echo "typecheck        mypy                        ($(MYPY_PATHS))"
	@echo "test             full suite"
	@echo "test-no-skips    full suite, failing if any test skipped (CI has a database)"
	@echo "coverage         suite with a coverage report and the 85% gate"
	@echo "migration-check  offline alembic upgrade and downgrade generation"
	@echo "db-upgrade       apply migrations to the application database (DATABASE_URL)"
	@echo "db-create-test   create the disposable database for destructive tests"
	@echo "db-upgrade-test  apply migrations to the disposable test database"
	@echo "db-verify-isolation  prove the destructive target is not the application database"
	@echo "up / down        local stack"
	@echo ""
	@echo "CI runs these same targets. Do not duplicate the commands in the workflow."

install:
	python3 -m venv .venv
	./.venv/bin/pip install --upgrade pip
	./.venv/bin/pip install -e ".[dev]"

fmt:
	$(RUFF) format $(PY_PATHS)

fmt-check:
	$(RUFF) format --check $(PY_PATHS)

lint:
	$(RUFF) check $(PY_PATHS)

typecheck:
	$(MYPY) $(MYPY_PATHS) --ignore-missing-imports

# -ra prints a short summary of every non-passing outcome WITH ITS REASON. Without it a skip is a
# bare 's' in a progress line, and "203 passed, 2 skipped" reads as success while the two tests
# that would have caught a schema defect never ran. Verbosity flags live here rather than in
# pyproject addopts so the Makefile stays the single definition of how the suite is invoked.
#
# Output is recorded to $(TEST_LOG) as well as shown, so `test-summary` can report the counts from
# THIS run instead of starting another one. Redirect-then-cat rather than a pipe: it preserves
# pytest's exit status exactly, with no dependence on pipefail or on which shell make chose.
test:
	@$(PYTEST) tests -ra > $(TEST_LOG) 2>&1; status=$$?; cat $(TEST_LOG); exit $$status

test-unit:
	$(PYTEST) tests/unit -ra

test-integration:
	$(PYTEST) tests/integration -ra

test-architecture:
	$(PYTEST) tests/architecture -ra

# ANTI-VACUITY GATE for environments that have a database. A skip here is a guard that quietly
# stopped being enforced, so it fails the run instead of being reported as a pass. The variable is
# read by a hook in tests/conftest.py, which names every skipped test and its reason.
test-no-skips:
	@FINTEK_FORBID_SKIPS=1 $(PYTEST) tests -ra > $(TEST_LOG) 2>&1; status=$$?; cat $(TEST_LOG); exit $$status

coverage:
	$(PYTEST) tests -q $(COV_PACKAGES) --cov-report=term-missing --cov-fail-under=85

# Apply migrations to the APPLICATION database. The URL is resolved by
# packages/persistence/engine, which is its single home.
db-upgrade:
	$(ALEMBIC) upgrade head

# The disposable database destructive tests run against. Idempotent; refuses a target that cannot
# be proven separate from the application database.
db-create-test:
	$(PYTHON) scripts/create_test_database.py

# Migrations against the disposable database. The destructive tests reset it themselves, so this
# target is only for inspecting the test schema by hand. The URL goes through assert_disposable,
# so this can never be pointed at the application database by editing one variable.
db-upgrade-test:
	DATABASE_URL="$$($(PYTHON) scripts/create_test_database.py --print-url)" $(ALEMBIC) upgrade head

# Fails if the destructive target is not provably a separate, disposable, test-designated
# database. Run BEFORE the suite so a misconfiguration is caught before anything drops a table.
db-verify-isolation:
	@$(PYTHON) scripts/create_test_database.py --verify

# Exact pass and skip counts on one line, for a CI log a reviewer reads rather than expands.
#
# Reads the log written by the LAST suite run. It used to invoke pytest itself, which meant CI ran
# all 330 tests a second time purely to print a number, and — worse — reported counts from a
# different execution than the one the zero-skip gate had just enforced.
#
# Greps for the outcome line rather than taking the last one: pytest's progress dots carry no
# trailing newline, so `tail -1` returns the dots and not the counts.
test-summary:
	@test -f $(TEST_LOG) || { echo "no recorded run; run 'make test' or 'make test-no-skips' first" >&2; exit 1; }
	@grep -E '^=*[0-9]+ (passed|failed|error)|[0-9]+ (passed|failed|error).* in ' $(TEST_LOG) | tail -1

# Offline migration reversibility. Needs no database: --sql generates DDL without connecting.
migration-check:
	$(ALEMBIC) upgrade head --sql > /dev/null
	$(ALEMBIC) downgrade 0001_initial:base --sql > /dev/null

# The gate a sprint must pass. Documentation synchronization is verified by review, not by make.
check: fmt-check lint typecheck test migration-check

up:
	docker compose up -d

down:
	docker compose down

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	rm -rf .pytest_cache .ruff_cache .mypy_cache var/objects $(TEST_LOG)
