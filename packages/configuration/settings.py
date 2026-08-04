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
class ReviewSettings:
    """The parser-review application: where it binds, what it may spend, where evidence goes.

    LOOPBACK IS THE DEFAULT AND BINDING BEYOND IT IS A DELIBERATE ACT. `docs/architecture` and
    roadmap.md Phase 6 both require the same minimum before anything leaves the loopback interface:
    a development authentication secret from ignored environment state, server-side sessions, CSRF
    protection on state-changing requests, same-origin requests, no permissive CORS, and no
    provider credential in the browser. `__post_init__` refuses to construct a LAN-bound
    configuration without the secret, so the unsafe combination cannot be reached by forgetting
    something.

    THE COST CEILING IS CUMULATIVE AND HAS NO DEFAULT ABOVE ZERO BY ACCIDENT. It is stated here in
    one place, passed to the durable spend journal, and shown in the UI before any run.
    """

    bind_host: str = "127.0.0.1"
    bind_port: int = 8765
    dev_auth_secret: str | None = None
    evaluation_root: str = "./var/evaluation-runs"
    prompt_directory: str = "./prompts/parser"
    capability_snapshot: str = "./docs/llm/bedrock-capability-snapshot.yaml"
    corpus_manifest: str = "./var/research-corpus/meta/filings.json"
    #: The SUPPLIED benchmark-filing contract. Empty means no benchmark catalog is composed,
    #: which is an ABSENT OPTIONAL SOURCE and not a fallback: nothing substitutes a different
    #: filing, the benchmark surface simply answers 404 for a filing nobody supplied.
    benchmark_manifest: str = "./docs/benchmark/benchmark-filings.yaml"
    #: "intact" or "projected". See MultipartSettings.source_input_mode.
    source_input_mode: str = "intact"
    author_label: str = "local-developer"
    cost_ceiling_usd: str = "5.00"
    max_concurrent_invocations: int = 1
    allow_sec_fetch: bool = True
    #: THREE CEILINGS, EACH ANSWERING A DIFFERENT QUESTION. `cost_ceiling_usd` is cumulative and
    #: never resets. `spend_phase` plus `phase_cost_ceiling_usd` bound what the CURRENTLY AUTHORIZED
    #: task may spend against the same durable journal — Phase 2 spent against it too, and a phase
    #: total is what makes "this task's ceiling" a computable fact rather than an arithmetic note.
    #: `multipart_filing_budget_usd` bounds ONE filing's parse across every call it queues, so a
    #: filing that plans ambitiously cannot consume the whole authorization on its own.
    spend_phase: str = ""
    phase_cost_ceiling_usd: str | None = None
    multipart_filing_budget_usd: str = "1.00"
    #: OPERATIONAL SAFETY LIMITS, never statements about what filings contain. A depth limit does
    #: not say a filing has at most four levels; it says this system stops spending on a branch
    #: that keeps asking to go deeper and reports why.
    multipart_max_depth: int = 4
    multipart_reconciliation_cycles: int = 3

    @property
    def loopback_only(self) -> bool:
        return self.bind_host in {"127.0.0.1", "::1", "localhost"}

    def __post_init__(self) -> None:
        if not self.loopback_only and not self.dev_auth_secret:
            raise ValueError(
                f"bind_host {self.bind_host!r} leaves the loopback interface and no development "
                "authentication secret is configured. An unauthenticated review UI on a LAN "
                "exposes preserved filings, run evidence and a control that spends money. Set "
                "REVIEW_DEV_SECRET in ignored environment state, or bind to 127.0.0.1."
            )
        if self.dev_auth_secret is not None and len(self.dev_auth_secret) < 16:
            raise ValueError(
                "the development authentication secret must be at least 16 characters; a short "
                "one is guessable in the time a LAN scan takes"
            )
        if self.max_concurrent_invocations < 1:
            raise ValueError("max_concurrent_invocations must be at least 1")


@dataclass(frozen=True)
class Settings:
    """Top-level application settings."""

    sec: SecAccessSettings
    storage: StorageSettings = field(default_factory=StorageSettings)
    llm: LlmSettings = field(default_factory=LlmSettings)
    review: ReviewSettings = field(default_factory=ReviewSettings)
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
            review=ReviewSettings(
                bind_host=source.get("REVIEW_BIND_HOST", "127.0.0.1"),
                bind_port=int(source.get("REVIEW_BIND_PORT", "8765")),
                # No default and no placeholder. An empty placeholder documents an unsafe design
                # as the expected one; absent means loopback-only, which is the safe state.
                dev_auth_secret=source.get("REVIEW_DEV_SECRET") or None,
                evaluation_root=source.get("EVALUATION_ROOT", "./var/evaluation-runs"),
                prompt_directory=source.get("PROMPT_DIRECTORY", "./prompts/parser"),
                capability_snapshot=source.get(
                    "CAPABILITY_SNAPSHOT", "./docs/llm/bedrock-capability-snapshot.yaml"
                ),
                corpus_manifest=source.get(
                    "CORPUS_MANIFEST", "./var/research-corpus/meta/filings.json"
                ),
                benchmark_manifest=source.get(
                    "BENCHMARK_MANIFEST", "./docs/benchmark/benchmark-filings.yaml"
                ),
                source_input_mode=source.get("SOURCE_INPUT_MODE", "intact"),
                author_label=source.get("REVIEW_AUTHOR", "local-developer"),
                cost_ceiling_usd=source.get("COST_CEILING_USD", "5.00"),
                max_concurrent_invocations=int(source.get("MAX_CONCURRENT_INVOCATIONS", "1")),
                allow_sec_fetch=source.get("ALLOW_SEC_FETCH", "true").lower() != "false",
                spend_phase=source.get("SPEND_PHASE", ""),
                # No default. A phase ceiling with no value configured means no phase ceiling, and
                # the cumulative one still binds; inventing a number here would be a spending limit
                # nobody authorized.
                phase_cost_ceiling_usd=source.get("PHASE_COST_CEILING_USD") or None,
                multipart_filing_budget_usd=source.get("MULTIPART_FILING_BUDGET_USD", "1.00"),
                multipart_max_depth=int(source.get("MULTIPART_MAX_DEPTH", "4")),
                multipart_reconciliation_cycles=int(
                    source.get("MULTIPART_RECONCILIATION_CYCLES", "3")
                ),
            ),
            environment=source.get("ENVIRONMENT", "local"),
        )
