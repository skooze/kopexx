# FinTek developer commands. Every target runs inside the project virtualenv.
VENV := ./.venv/bin

.PHONY: help install fmt fmt-check lint typecheck test test-unit test-integration \
        test-architecture test-security coverage check up down clean

help:
	@echo "install          create the virtualenv and install dependencies"
	@echo "check            run every gate: format, lint, types, tests"
	@echo "fmt / fmt-check  apply or verify formatting"
	@echo "lint             ruff"
	@echo "typecheck        mypy"
	@echo "test             full suite"
	@echo "coverage         suite with a coverage report"
	@echo "up / down        local stack"

install:
	python3 -m venv .venv
	$(VENV)/pip install --upgrade pip
	$(VENV)/pip install -e ".[dev]"

fmt:
	$(VENV)/ruff format packages tests

fmt-check:
	$(VENV)/ruff format --check packages tests

lint:
	$(VENV)/ruff check packages tests

typecheck:
	$(VENV)/mypy packages --ignore-missing-imports

test:
	$(VENV)/python -m pytest tests -q

test-unit:
	$(VENV)/python -m pytest tests/unit -q

test-integration:
	$(VENV)/python -m pytest tests/integration -q

test-architecture:
	$(VENV)/python -m pytest tests/architecture -q

coverage:
	$(VENV)/python -m pytest tests -q \
	  --cov=packages.sec_identity --cov=packages.configuration --cov=packages.sec_client \
	  --cov=packages.storage --cov=packages.llm_gateway --cov=packages.dera_notes \
	  --cov=packages.observability --cov-report=term-missing

# The gate a sprint must pass. Documentation synchronization is verified by review, not by make.
check: fmt-check lint typecheck test

up:
	docker compose up -d

down:
	docker compose down

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	rm -rf .pytest_cache .ruff_cache .mypy_cache var/objects
