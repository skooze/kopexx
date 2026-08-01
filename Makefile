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

COV_PACKAGES := --cov=packages.sec_identity --cov=packages.configuration \
                --cov=packages.sec_client --cov=packages.storage \
                --cov=packages.llm_gateway --cov=packages.dera_notes \
                --cov=packages.observability

.PHONY: help install fmt fmt-check lint typecheck test test-unit test-integration \
        test-architecture test-security coverage migration-check check up down clean

help:
	@echo "install          create the virtualenv and install dependencies"
	@echo "check            the sprint gate: format, lint, types, tests, migrations"
	@echo "fmt / fmt-check  apply or verify formatting  ($(PY_PATHS))"
	@echo "lint             ruff                        ($(PY_PATHS))"
	@echo "typecheck        mypy                        ($(MYPY_PATHS))"
	@echo "test             full suite"
	@echo "coverage         suite with a coverage report and the 85% gate"
	@echo "migration-check  offline alembic upgrade and downgrade generation"
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

test:
	$(PYTEST) tests -q

test-unit:
	$(PYTEST) tests/unit -q

test-integration:
	$(PYTEST) tests/integration -q

test-architecture:
	$(PYTEST) tests/architecture -q

coverage:
	$(PYTEST) tests -q $(COV_PACKAGES) --cov-report=term-missing --cov-fail-under=85

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
	rm -rf .pytest_cache .ruff_cache .mypy_cache var/objects
