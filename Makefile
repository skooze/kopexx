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

# Every Python path in the repository. Formatting and linting cover both.
#
# `scripts` and `migrations` were removed from this list because those directories no longer
# exist. Every script was an entry point for the deterministic parser, the application database,
# or the DERA fact loader, and all three are deleted; Alembic and its revisions went with the
# application schema they described.
PY_PATHS := packages tests

# Type checking covers shipped source only. tests/ is excluded deliberately, so a test may use the
# loose idioms tests use without weakening the check on the source that matters.
MYPY_PATHS := packages

# Where a suite run records its own output, so the counts can be reported without running the
# suite a second time. Gitignored.
TEST_LOG := .pytest-last-run.log

# Every implemented package. A package absent from this list is not measured, so its coverage
# gap is invisible and the gate passes without it — which is the same vacuity trap as an
# architecture test scanning an empty directory. Add a package here in the change that creates it.
COV_PACKAGES := --cov=packages.sec_identity --cov=packages.configuration \
                --cov=packages.sec_client --cov=packages.storage \
                --cov=packages.llm_gateway --cov=packages.observability \
                --cov=packages.filing_acquisition --cov=packages.filing_discovery \
                --cov=packages.model_catalog --cov=packages.evaluation_store \
                --cov=packages.source_transport --cov=packages.coverage_validation \
                --cov=packages.prompt_registry --cov=packages.orchestrator \
                --cov=packages.review_api --cov=packages.review_web \
                --cov=packages.multipart

.PHONY: help install fmt fmt-check lint typecheck test test-unit \
        test-architecture test-integration test-security test-no-skips coverage test-summary \
        check clean review

help:
	@echo "install          create the virtualenv and install dependencies"
	@echo "check            the gate: format, lint, types, tests"
	@echo "fmt / fmt-check  apply or verify formatting  ($(PY_PATHS))"
	@echo "lint             ruff                        ($(PY_PATHS))"
	@echo "typecheck        mypy                        ($(MYPY_PATHS))"
	@echo "test             full suite"
	@echo "test-no-skips    full suite, failing if any test skipped"
	@echo "review           start the parser-review application on 127.0.0.1"
	@echo "coverage         suite with a coverage report and the 85% gate"
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
# that would have caught a defect never ran. Verbosity flags live here rather than in pyproject
# addopts so the Makefile stays the single definition of how the suite is invoked.
#
# Output is recorded to $(TEST_LOG) as well as shown, so `test-summary` can report the counts from
# THIS run instead of starting another one. Redirect-then-cat rather than a pipe: it preserves
# pytest's exit status exactly, with no dependence on pipefail or on which shell make chose.
test:
	@$(PYTEST) tests -ra > $(TEST_LOG) 2>&1; status=$$?; cat $(TEST_LOG); exit $$status

test-unit:
	$(PYTEST) tests/unit -ra

test-architecture:
	$(PYTEST) tests/architecture -ra

test-integration:
	$(PYTEST) tests/integration -ra

test-security:
	$(PYTEST) -m security -ra

# ANTI-VACUITY GATE. A skip is a guard that quietly stopped being enforced, so it fails the run
# instead of being reported as a pass. The variable is read by a hook in tests/conftest.py, which
# names every skipped test and its reason.
#
# THE SUITE NOW HAS NO ENVIRONMENTAL PRECONDITION AT ALL. It previously needed two live PostgreSQL
# databases, and every database test skipped without them. There is no application database, no
# ORM and no migration left in this repository, so every test runs everywhere — which is why this
# target is the same suite as `test`, not a privileged variant of it.
test-no-skips:
	@FINTEK_FORBID_SKIPS=1 $(PYTEST) tests -ra > $(TEST_LOG) 2>&1; status=$$?; cat $(TEST_LOG); exit $$status

coverage:
	$(PYTEST) tests -q $(COV_PACKAGES) --cov-report=term-missing --cov-fail-under=85

# Exact pass and skip counts on one line, for a CI log a reviewer reads rather than expands.
#
# Reads the log written by the LAST suite run. It used to invoke pytest itself, which meant CI ran
# the whole suite a second time purely to print a number, and — worse — reported counts from a
# different execution than the one the zero-skip gate had just enforced.
#
# Greps for the outcome line rather than taking the last one: pytest's progress dots carry no
# trailing newline, so `tail -1` returns the dots and not the counts.
test-summary:
	@test -f $(TEST_LOG) || { echo "no recorded run; run 'make test' or 'make test-no-skips' first" >&2; exit 1; }
	@grep -E '^=*[0-9]+ (passed|failed|error)|[0-9]+ (passed|failed|error).* in ' $(TEST_LOG) | tail -1

# The gate a change must pass. Documentation synchronization is verified by review, not by make.
#
# `migration-check` was removed with the migrations. It generated Alembic DDL offline across
# base:head and head:base for an application schema that no longer exists.
check: fmt-check lint typecheck test

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	rm -rf .pytest_cache .ruff_cache .mypy_cache build dist *.egg-info $(TEST_LOG)

# Start the parser-review application. Loopback only unless REVIEW_BIND_HOST says otherwise, and
# `packages/configuration.ReviewSettings` refuses a non-loopback bind without an authentication
# secret from ignored environment state.
#
# The default provider is the in-process mock, which needs no credentials and no network. Reaching
# a real model is an explicit choice: LLM_PROVIDER=bedrock, an AWS_REGION, federated credentials
# resolved by the SDK's own provider chain, and `pip install -e '.[aws]'`.
review:
	$(PYTHON) -c "from packages.review_api import serve; serve()"
