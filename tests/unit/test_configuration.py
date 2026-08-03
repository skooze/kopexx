"""Configuration and SEC User-Agent validation tests."""

from __future__ import annotations

import pytest

from packages.configuration import (
    InvalidUserAgentError,
    LlmSettings,
    MissingModelRegionError,
    SecAccessSettings,
    Settings,
    is_valid_user_agent,
    validate_user_agent,
)


def test_sec_user_agent_required() -> None:
    """Startup must fail closed when no User-Agent is configured."""
    for missing in (None, "", "   "):
        with pytest.raises(InvalidUserAgentError):
            validate_user_agent(missing)


def test_default_library_user_agent_rejected() -> None:
    """SEC denylists library defaults and answers with HTTP 403."""
    for denied in (
        "python-requests/2.31.0",
        "Python-urllib/3.12",
        "curl/8.5.0",
        "Wget/1.21",
        "Go-http-client/1.1",
        "axios/1.6.0",
        "okhttp/4.12.0",
    ):
        assert not is_valid_user_agent(denied), f"{denied} must be rejected"


def test_user_agent_requires_contact_email() -> None:
    """SEC access policy requires a contact address."""
    with pytest.raises(InvalidUserAgentError):
        validate_user_agent("FinTek Research Platform")
    assert is_valid_user_agent("FinTek Research contact@example.com")


def test_settings_reject_rate_above_sec_ceiling() -> None:
    """The documented ceiling is ten requests per second aggregated across all machines."""
    with pytest.raises(ValueError):
        SecAccessSettings(user_agent="FinTek a@b.co", global_requests_per_second=25.0)


def test_settings_reject_short_cooldown() -> None:
    """SEC-INVARIANT: recovery requires ten full minutes below threshold."""
    with pytest.raises(ValueError):
        SecAccessSettings(user_agent="FinTek a@b.co", throttle_cooldown_seconds=30)


def test_settings_defaults_are_conservative() -> None:
    settings = Settings.from_env({"SEC_USER_AGENT": "FinTek Research contact@example.com"})
    assert settings.sec.global_requests_per_second <= 10
    assert settings.sec.efts_requests_per_second <= settings.sec.global_requests_per_second
    assert settings.sec.throttle_cooldown_seconds >= 600


def test_the_model_region_has_no_default() -> None:
    """It defaulted to a hardcoded us-east-1, and Phase 1 showed why that is unsafe.

    One of the five approved candidates is not offered in us-east-1 at all, so a silent default
    would report a real model as unavailable with nothing in the code to point at. An unset region
    now stays unset.
    """
    settings = Settings.from_env({"SEC_USER_AGENT": "FinTek Research contact@example.com"})
    assert settings.llm.region is None
    assert LlmSettings().region is None


def test_a_real_provider_without_a_region_fails_closed() -> None:
    """The mock needs no region; anything that reaches a network endpoint does."""
    with pytest.raises(MissingModelRegionError):
        LlmSettings(provider="bedrock")
    with pytest.raises(MissingModelRegionError):
        Settings.from_env(
            {"SEC_USER_AGENT": "FinTek Research contact@example.com", "LLM_PROVIDER": "bedrock"}
        )


def test_a_supplied_region_is_carried_verbatim() -> None:
    """Supplied, never normalized, never substituted."""
    settings = Settings.from_env(
        {
            "SEC_USER_AGENT": "FinTek Research contact@example.com",
            "LLM_PROVIDER": "bedrock",
            "AWS_REGION": "somewhere-central-1",
        }
    )
    assert settings.llm.region == "somewhere-central-1"


def test_the_mock_provider_still_needs_no_region() -> None:
    """The default suite must never require a provider configuration to run."""
    assert LlmSettings().provider == "mock"
    assert Settings.from_env({"SEC_USER_AGENT": "FinTek Research contact@example.com"}).llm
