"""Application settings, validated at construction.

FINANCIAL-INVARIANT and SEC-INVARIANT settings are validated eagerly so a misconfigured
deployment fails at startup rather than after generating traffic that will be blocked.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from .errors import MissingModelRegionError
from .user_agent import validate_user_agent


@dataclass(frozen=True)
class SecAccessSettings:
    """SEC access controls.

    Defaults are deliberately below the documented ceiling of ten requests per second. The
    documented limit is aggregate across all machines, and enforcement targets sustained rate
    rather than short bursts, so a burst test that passes proves nothing.
    """

    user_agent: str
    global_requests_per_second: float = 6.0
    efts_requests_per_second: float = 1.0
    throttle_cooldown_seconds: int = 600
    connect_timeout_seconds: float = 10.0
    read_timeout_seconds: float = 60.0
    max_retries: int = 3

    def __post_init__(self) -> None:
        validate_user_agent(self.user_agent)
        if self.global_requests_per_second <= 0 or self.global_requests_per_second > 10:
            raise ValueError(
                "global_requests_per_second must be within (0, 10]; SEC documents a ceiling "
                "of 10 requests per second aggregated across all machines"
            )
        if self.efts_requests_per_second <= 0 or self.efts_requests_per_second > 10:
            raise ValueError("efts_requests_per_second must be within (0, 10]")
        if self.throttle_cooldown_seconds < 600:
            raise ValueError(
                "throttle_cooldown_seconds must be at least 600. SEC requires the request rate "
                "to remain below threshold for ten full minutes before access resumes; a shorter "
                "cooldown keeps the client above threshold and extends the block."
            )


@dataclass(frozen=True)
class StorageSettings:
    """Object storage location and backend selection."""

    backend: str = "filesystem"
    root: str = "./var/objects"
    bucket: str | None = None
    endpoint_url: str | None = None


@dataclass(frozen=True)
class LlmSettings:
    """Model gateway configuration.

    THE REGION HAS NO DEFAULT, AND THAT IS A CORRECTION. It defaulted to a hardcoded `us-east-1`,
    which is the form-family defect with a bill attached: a guessed value in runtime source, no
    reviewed contract behind it, and a silent success when the operator sets nothing. Phase 1
    discovery is what made the cost of that concrete — of the five approved candidates, one is not
    available in `us-east-1` at all, so an unset region would have made a real model appear
    unavailable for a reason nobody could see in the code. `None` means unset; a real provider
    fails closed on it.

    `standard_model_id` and `analysis_model_id` are a TWO-ROLE shape that predates the four-role
    product. They are deliberately not replaced with a guessed four-role shape here: the roles are
    resolved through the reviewed capability snapshot by `packages/model_catalog`, and inventing a
    parallel set of identifier fields would give the same fact two homes.
    """

    provider: str = "mock"
    standard_model_id: str = "mock-model-v1"
    analysis_model_id: str = "mock-model-v1"
    region: str | None = None
    max_output_tokens: int = 4096

    def __post_init__(self) -> None:
        # The mock provider performs no network call and needs no region. Any other provider does,
        # and refusing at startup is the difference between one clear error and a run that reaches
        # the wrong regional endpoint.
        if self.provider != "mock" and not self.region:
            raise MissingModelRegionError(
                f"provider {self.provider!r} requires a region and none is configured. Set "
                "AWS_REGION to a region the selected model was actually verified in; there is no "
                "default, because a default is how a guessed region survives review."
            )


@dataclass(frozen=True)
class Settings:
    """Top-level application settings."""

    sec: SecAccessSettings
    storage: StorageSettings = field(default_factory=StorageSettings)
    llm: LlmSettings = field(default_factory=LlmSettings)
    environment: str = "local"

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> Settings:
        """Build settings from environment variables, validating eagerly."""
        source = env if env is not None else dict(os.environ)
        return cls(
            sec=SecAccessSettings(
                user_agent=source.get("SEC_USER_AGENT", ""),
                global_requests_per_second=float(source.get("SEC_GLOBAL_RPS", "6")),
                efts_requests_per_second=float(source.get("SEC_EFTS_RPS", "1")),
                throttle_cooldown_seconds=int(source.get("SEC_THROTTLE_COOLDOWN_S", "600")),
            ),
            storage=StorageSettings(
                backend=source.get("STORAGE_BACKEND", "filesystem"),
                root=source.get("STORAGE_ROOT", "./var/objects"),
                bucket=source.get("STORAGE_BUCKET") or None,
                endpoint_url=source.get("STORAGE_ENDPOINT_URL") or None,
            ),
            llm=LlmSettings(
                provider=source.get("LLM_PROVIDER", "mock"),
                standard_model_id=source.get("LLM_STANDARD_MODEL_ID", "mock-model-v1"),
                analysis_model_id=source.get("LLM_ANALYSIS_MODEL_ID", "mock-model-v1"),
                # No fallback. An absent AWS_REGION stays absent and is rejected by
                # LlmSettings.__post_init__ for any provider that actually needs one.
                region=source.get("AWS_REGION") or None,
            ),
            environment=source.get("ENVIRONMENT", "local"),
        )
