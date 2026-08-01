"""Application settings, validated at construction.

FINANCIAL-INVARIANT and SEC-INVARIANT settings are validated eagerly so a misconfigured
deployment fails at startup rather than after generating traffic that will be blocked.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

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
    """Model gateway configuration."""

    provider: str = "mock"
    standard_model_id: str = "mock-model-v1"
    analysis_model_id: str = "mock-model-v1"
    region: str = "us-east-1"
    max_output_tokens: int = 4096


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
                region=source.get("AWS_REGION", "us-east-1"),
            ),
            environment=source.get("ENVIRONMENT", "local"),
        )
