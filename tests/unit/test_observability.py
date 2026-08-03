"""Observability tests: structured logging, field redaction, and correlation scope.

WHY THIS FILE EXISTS. `packages/observability` had NO test module of any kind. It carries a
SECURITY-INVARIANT — filing text and model-visible payload bodies are never logged, and neither is
credential material — and that invariant was enforced by a frozenset nothing exercised. The
cleanup that deleted the deterministic parser also deleted the only modules that imported this one,
so the package now has no non-test caller at all; leaving it both unwired and untested would make
it dead code by any honest reading.

The redaction list is the security control here, so the tests are written against BEHAVIOUR — what
the formatter actually emits — rather than against the contents of the frozenset. Asserting the set
contains a name proves only that someone typed the name.
"""

from __future__ import annotations

import logging

import pytest

from packages.observability import (
    REDACTED_FIELDS,
    StructuredFormatter,
    correlation_scope,
    get_correlation_id,
    log_event,
    new_correlation_id,
    reset_correlation_id,
    set_correlation_id,
)


def _render(**fields: object) -> str:
    """Format one record exactly as the installed handler would."""
    record = logging.LogRecord(
        name="fintek.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="event",
        args=(),
        exc_info=None,
    )
    record.fields = fields  # type: ignore[attr-defined]
    return StructuredFormatter().format(record)


# --- the security invariant ---------------------------------------------------------------------

SECRET = "THIS-VALUE-MUST-NEVER-BE-EMITTED"


@pytest.mark.security
@pytest.mark.parametrize("field", sorted(REDACTED_FIELDS))
def test_no_redacted_field_value_ever_reaches_the_log(field: str) -> None:
    """SECURITY-INVARIANT: the VALUE is suppressed, and the field name is kept as the signal.

    Parametrized over the whole list rather than a sample, so adding a name without wiring it in
    cannot pass, and every entry is proven rather than assumed.
    """
    rendered = _render(**{field: SECRET})
    assert SECRET not in rendered, f"{field} leaked its value into a log line"
    assert f"{field}=<redacted>" in rendered, f"{field} was dropped instead of being marked"


@pytest.mark.security
def test_model_and_filing_content_fields_are_redacted() -> None:
    """The fields a filing or a model response actually arrives in.

    These may be very large and may carry text a prompt-injection attempt placed inside a filing.
    Bodies go to object storage and are referenced by URI and hash, never inlined into a log.
    """
    for field in ("content", "payload", "request_body", "response_body", "text", "prompt"):
        assert field in REDACTED_FIELDS, f"{field} must never be logged"


@pytest.mark.security
def test_aws_credential_field_names_are_redacted_before_aws_exists() -> None:
    """rules.md section 3: a credential that reaches a log has already been disclosed.

    Kopexx holds no long-lived AWS credential and no AWS integration exists. The redaction is in
    place first on purpose — a log is the one place nobody thinks to check afterwards.

    THE FIELD NAMES ARE BUILT AS DICT KEYS, NOT PASSED AS KEYWORD ARGUMENTS. Passing one of these
    names as a keyword argument is textually indistinguishable from constructing an SDK client with
    an explicit credential, so `tests/architecture/test_aws_identity.py` fails on it — which it did,
    correctly, twice while this file was being written, once for the call and once for a docstring
    that quoted the call. The guard is not allowlisted around: an allowlist entry here would exempt
    a whole test module from the check permanently, and the check is worth more than the phrasing.
    """
    rendered = _render(**{"aws_secret_access_key": SECRET, "aws_session_token": SECRET})
    assert SECRET not in rendered
    assert rendered.count("<redacted>") == 2


@pytest.mark.security
def test_an_unlisted_field_is_emitted_so_redaction_is_not_vacuous() -> None:
    """If everything were redacted the tests above would pass while proving nothing."""
    rendered = _render(accession="0000320193-25-000079", byte_count=1520208)
    assert "0000320193-25-000079" in rendered
    assert "byte_count=1520208" in rendered


# --- structure ------------------------------------------------------------------------------


def test_the_formatter_emits_queryable_key_value_pairs() -> None:
    rendered = _render(status="SUCCEEDED")
    for key in ("ts=", "level=INFO", "logger=fintek.test", "msg=", "status="):
        assert key in rendered, f"missing {key!r} in {rendered!r}"


def test_log_event_passes_fields_through_to_the_formatter(caplog: pytest.LogCaptureFixture) -> None:
    logger = logging.getLogger("fintek.test.event")
    with caplog.at_level(logging.INFO, logger="fintek.test.event"):
        log_event(logger, logging.INFO, "acquired", accession="0000320193-94-000016", secret=SECRET)

    record = caplog.records[-1]
    assert record.fields["accession"] == "0000320193-94-000016"  # type: ignore[attr-defined]
    assert SECRET not in StructuredFormatter().format(record)


def test_a_record_with_no_fields_still_formats() -> None:
    record = logging.LogRecord("fintek.test", logging.WARNING, __file__, 1, "bare", (), None)
    assert "msg='bare'" in StructuredFormatter().format(record)


# --- correlation ----------------------------------------------------------------------------


def test_correlation_identifiers_are_unique() -> None:
    assert new_correlation_id() != new_correlation_id()


def test_correlation_scope_binds_and_restores() -> None:
    assert get_correlation_id() is None
    with correlation_scope("run-0001") as value:
        assert value == "run-0001"
        assert get_correlation_id() == "run-0001"
        assert "correlation_id=run-0001" in _render(step="acquire")
    assert get_correlation_id() is None, "the scope leaked past its block"


def test_nested_correlation_scopes_restore_the_outer_value() -> None:
    """A child job must not overwrite the parent run's identifier for the rest of the process."""
    with correlation_scope("parent"):
        with correlation_scope("child"):
            assert get_correlation_id() == "child"
        assert get_correlation_id() == "parent"


def test_correlation_can_be_set_and_reset_by_token() -> None:
    token = set_correlation_id("explicit")
    assert get_correlation_id() == "explicit"
    reset_correlation_id(token)
    assert get_correlation_id() is None


def test_a_record_without_a_correlation_id_omits_the_field() -> None:
    """An empty `correlation_id=` would be noise on every line emitted outside a scope."""
    assert "correlation_id=" not in _render(step="startup")
