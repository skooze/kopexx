"""The durable records an evaluation run is made of.

WHAT LIVES HERE AND WHAT DELIBERATELY DOES NOT. These records carry identity, model routing,
prompt identity, execution and review state, cost and attempt history — everything the store
itself has to understand in order to be a store. They do NOT carry a source-set model, a
validation model or a filing model. Those belong to `packages/source_transport` and
`packages/coverage_validation`, and each arrives here as an opaque mapping its owner produced.

That keeps the dependency direction one-way and keeps this package free of any opinion about what
a filing contains — which is rules.md invariant 14 applied to storage. A store that understood
source sets would eventually start deciding which members mattered.

MONEY IS A DECIMAL CARRIED AS A STRING. Every amount is serialised as its exact decimal text and
read back through `Decimal`. A float round-trip through YAML is how 0.00015 becomes
0.000149999999999999993145.

EVERY IDENTIFIER IS QUOTED ON THE WAY OUT. YAML 1.2 parses an unquoted 0000320193 as the integer
320193 and destroys a CIK. `packages/llm_gateway.to_yaml` is the single home for that rule and is
what serialises these records.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from .errors import RecordFormatError
from .states import ExecutionState, ReviewState


def utc_now() -> str:
    """An ISO-8601 UTC timestamp. One home, so every record is comparable as text."""
    return datetime.now(UTC).isoformat()


def _require(mapping: dict[str, Any], key: str, where: str) -> Any:
    if key not in mapping:
        raise RecordFormatError(f"{where} is missing required field {key!r}")
    return mapping[key]


def _text(mapping: dict[str, Any], key: str, where: str) -> str:
    value = _require(mapping, key, where)
    if not isinstance(value, str):
        raise RecordFormatError(
            f"{where}.{key} must be a quoted string, got {type(value).__name__} ({value!r})"
        )
    return value


def _optional_text(mapping: dict[str, Any], key: str) -> str | None:
    value = mapping.get(key)
    return None if value is None else str(value)


def _integer(mapping: dict[str, Any], key: str, where: str) -> int:
    value = _require(mapping, key, where)
    if isinstance(value, bool) or not isinstance(value, int):
        raise RecordFormatError(f"{where}.{key} must be an integer, got {type(value).__name__}")
    return value


def _decimal(mapping: dict[str, Any], key: str, where: str) -> Decimal:
    value = _require(mapping, key, where)
    try:
        return Decimal(str(value))
    except ArithmeticError as error:
        raise RecordFormatError(f"{where}.{key} is not a decimal amount: {value!r}") from error


def _optional_decimal(mapping: dict[str, Any], key: str) -> Decimal | None:
    value = mapping.get(key)
    return None if value is None else Decimal(str(value))


@dataclass(frozen=True)
class ModelRouting:
    """Exactly which model was invoked, where, and whether that was the preferred region.

    `in_preferred_region` and `cross_region_reason` exist so a cross-region route is a DISCLOSED
    fact rather than an invisible one. The product is explicitly allowed to run different models
    in different regions; it is not allowed to do so quietly. Section 5 of the Phase 2 brief
    requires the region to appear in the run plan, the child job, the request, the response, the
    cost record and the artifact lineage, and this record is what carries it into all six.
    """

    label: str
    role: str
    model_id: str
    invocation_id: str
    region: str
    preferred_region: str
    in_preferred_region: bool
    inference_profile_id: str | None
    cross_region_reason: str | None
    multimodal: bool

    def to_mapping(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "role": self.role,
            "model_id": self.model_id,
            "invocation_id": self.invocation_id,
            "region": self.region,
            "preferred_region": self.preferred_region,
            "in_preferred_region": self.in_preferred_region,
            "inference_profile_id": self.inference_profile_id,
            "cross_region_reason": self.cross_region_reason,
            "multimodal": self.multimodal,
        }

    @classmethod
    def from_mapping(cls, raw: dict[str, Any]) -> ModelRouting:
        where = "model_routing"
        return cls(
            label=_text(raw, "label", where),
            role=_text(raw, "role", where),
            model_id=_text(raw, "model_id", where),
            invocation_id=_text(raw, "invocation_id", where),
            region=_text(raw, "region", where),
            preferred_region=_text(raw, "preferred_region", where),
            in_preferred_region=bool(_require(raw, "in_preferred_region", where)),
            inference_profile_id=_optional_text(raw, "inference_profile_id"),
            cross_region_reason=_optional_text(raw, "cross_region_reason"),
            multimodal=bool(_require(raw, "multimodal", where)),
        )


@dataclass(frozen=True)
class PromptIdentity:
    """Which exact prompt bytes produced this response.

    The SHA-256 is recorded rather than the text, because the text is also written beside the
    request evidence and a second copy would be the one that drifts. A prompt version is never
    edited after use; the hash is what proves it.
    """

    prompt_id: str
    version: str
    sha256: str

    def to_mapping(self) -> dict[str, Any]:
        return {"prompt_id": self.prompt_id, "version": self.version, "sha256": self.sha256}

    @classmethod
    def from_mapping(cls, raw: dict[str, Any]) -> PromptIdentity:
        where = "prompt"
        return cls(
            prompt_id=_text(raw, "prompt_id", where),
            version=_text(raw, "version", where),
            sha256=_text(raw, "sha256", where),
        )


@dataclass(frozen=True)
class ParserSettings:
    """The request settings that change what comes back, and therefore change reuse identity."""

    max_output_tokens: int
    temperature: float

    def to_mapping(self) -> dict[str, Any]:
        return {"max_output_tokens": self.max_output_tokens, "temperature": self.temperature}

    @classmethod
    def from_mapping(cls, raw: dict[str, Any]) -> ParserSettings:
        where = "settings"
        return cls(
            max_output_tokens=_integer(raw, "max_output_tokens", where),
            temperature=float(_require(raw, "temperature", where)),
        )


@dataclass(frozen=True)
class InvocationAttempt:
    """One billable attempt against one model, whatever its outcome.

    A FAILED attempt is recorded exactly as carefully as a successful one. It was billable, it
    consumed the retry budget, and a benchmark that quietly dropped failures would report a
    success rate it never measured.

    `reasoning_characters` is separate from `visible_characters` because one candidate emits
    reasoning content before its answer through the Converse path. An output budget sized for the
    answer alone returns a well-formed response with no text in it, and recording only the visible
    length would make that look like an empty answer rather than an exhausted budget.
    """

    attempt: int
    started_at: str
    finished_at: str
    latency_ms: int
    stop_reason: str
    input_tokens: int
    output_tokens: int
    visible_characters: int
    reasoning_characters: int
    provider_request_id: str | None = None
    error: str | None = None
    retryable: bool | None = None

    def to_mapping(self) -> dict[str, Any]:
        return {
            "attempt": self.attempt,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "latency_ms": self.latency_ms,
            "stop_reason": self.stop_reason,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "visible_characters": self.visible_characters,
            "reasoning_characters": self.reasoning_characters,
            "provider_request_id": self.provider_request_id,
            "error": self.error,
            "retryable": self.retryable,
        }

    @classmethod
    def from_mapping(cls, raw: dict[str, Any]) -> InvocationAttempt:
        where = "attempt"
        return cls(
            attempt=_integer(raw, "attempt", where),
            started_at=_text(raw, "started_at", where),
            finished_at=_text(raw, "finished_at", where),
            latency_ms=_integer(raw, "latency_ms", where),
            stop_reason=_text(raw, "stop_reason", where),
            input_tokens=_integer(raw, "input_tokens", where),
            output_tokens=_integer(raw, "output_tokens", where),
            visible_characters=_integer(raw, "visible_characters", where),
            reasoning_characters=_integer(raw, "reasoning_characters", where),
            provider_request_id=_optional_text(raw, "provider_request_id"),
            error=_optional_text(raw, "error"),
            retryable=raw.get("retryable"),
        )


@dataclass(frozen=True)
class Incompatibility:
    """Why a filing and a model cannot be paired, in numbers a person can check.

    "Incompatible" on its own sends a user to a support channel. Every field here exists so the
    UI can say which limit was exceeded and by how much, and so the user — never the backend —
    can choose a different model.
    """

    reason: str
    detail: str
    source_set_bytes: int | None = None
    estimated_input_tokens: int | None = None
    model_context_tokens: int | None = None

    def to_mapping(self) -> dict[str, Any]:
        return {
            "reason": self.reason,
            "detail": self.detail,
            "source_set_bytes": self.source_set_bytes,
            "estimated_input_tokens": self.estimated_input_tokens,
            "model_context_tokens": self.model_context_tokens,
        }

    @classmethod
    def from_mapping(cls, raw: dict[str, Any]) -> Incompatibility:
        where = "incompatibility"
        return cls(
            reason=_text(raw, "reason", where),
            detail=_text(raw, "detail", where),
            source_set_bytes=raw.get("source_set_bytes"),
            estimated_input_tokens=raw.get("estimated_input_tokens"),
            model_context_tokens=raw.get("model_context_tokens"),
        )


@dataclass(frozen=True)
class ReviewTransition:
    """One entry in a job's review history. Appended, never rewritten."""

    at: str
    author: str
    from_state: str
    to_state: str
    note: str | None = None

    def to_mapping(self) -> dict[str, Any]:
        return {
            "at": self.at,
            "author": self.author,
            "from_state": self.from_state,
            "to_state": self.to_state,
            "note": self.note,
        }

    @classmethod
    def from_mapping(cls, raw: dict[str, Any]) -> ReviewTransition:
        where = "review_history entry"
        return cls(
            at=_text(raw, "at", where),
            author=_text(raw, "author", where),
            from_state=_text(raw, "from_state", where),
            to_state=_text(raw, "to_state", where),
            note=_optional_text(raw, "note"),
        )


@dataclass(frozen=True)
class Comment:
    """One developer evaluation comment, bound to the artifact VERSION it targeted.

    `target_version` matters: a comment written against attempt 1 does not silently become a
    comment about attempt 2. Comments are DATA. They are rendered as text and are never placed
    into any model-visible content — a filing, and anything a reviewer writes beside it, is
    untrusted input to a model.
    """

    comment_id: str
    parent_run_id: str
    child_job_id: str | None
    target_type: str
    target_id: str
    target_version: str
    author: str
    created_at: str
    text: str
    status: str = "OPEN"
    tags: tuple[str, ...] = ()

    def to_mapping(self) -> dict[str, Any]:
        return {
            "comment_id": self.comment_id,
            "parent_run_id": self.parent_run_id,
            "child_job_id": self.child_job_id,
            "target_type": self.target_type,
            "target_id": self.target_id,
            "target_version": self.target_version,
            "author": self.author,
            "created_at": self.created_at,
            "text": self.text,
            "status": self.status,
            "tags": list(self.tags),
        }

    @classmethod
    def from_mapping(cls, raw: dict[str, Any]) -> Comment:
        where = "comment"
        return cls(
            comment_id=_text(raw, "comment_id", where),
            parent_run_id=_text(raw, "parent_run_id", where),
            child_job_id=_optional_text(raw, "child_job_id"),
            target_type=_text(raw, "target_type", where),
            target_id=_text(raw, "target_id", where),
            target_version=_text(raw, "target_version", where),
            author=_text(raw, "author", where),
            created_at=_text(raw, "created_at", where),
            text=_text(raw, "text", where),
            status=str(raw.get("status") or "OPEN"),
            tags=tuple(str(t) for t in (raw.get("tags") or ())),
        )


@dataclass(frozen=True)
class RunEvent:
    """One progress event on the parent run's append-only log.

    NO PROVIDER DATA AND NO FILING TEXT. An event carries a kind, an optional child job and a
    short human message. Filing text may be very large and may carry an instruction a prompt
    injection placed inside a filing; provider payloads may carry request identifiers a browser
    has no business seeing. Both go to the evaluation store and are referenced, never streamed.
    """

    sequence: int
    at: str
    kind: str
    job_id: str | None
    message: str
    #: The multipart task this event is about, when it is about one. Added in Phase 2.1: a
    #: multipart run emits many events per child job, and a stream that could only say WHICH FILING
    #: something happened to would leave a reviewer unable to tell which part truncated.
    task_id: str | None = None

    @property
    def event_id(self) -> str:
        """A monotonic, resumable identifier. `Last-Event-ID` replays from the one after it."""
        return f"{self.sequence:08d}"


@dataclass
class RunRecord:
    """The parent run: one user request, one visible identifier, N child filing jobs.

    `selections` holds all four roles with None for a blank one. A blank role is a legitimate,
    complete configuration and is recorded as such — writing the parsing model into an empty
    summary slot is exactly the silent substitution rules.md section 21 rule 8 forbids, and it
    would be invisible afterwards if the record could not represent "the user chose nothing".
    """

    run_id: str
    created_at: str
    author: str
    cik: str
    entity_label: str
    parsing_label: str
    image_label: str | None = None
    summary_label: str | None = None
    analysis_label: str | None = None
    from_date: str | None = None
    to_date: str | None = None
    preferred_region: str = ""
    cost_ceiling_usd: Decimal = Decimal(0)
    job_ids: list[str] = field(default_factory=list)
    closed_at: str | None = None
    note: str | None = None

    @property
    def selected_roles(self) -> tuple[str, ...]:
        """The roles this run will actually execute, in order. Parsing is always among them."""
        roles = ["parsing"]
        if self.image_label:
            roles.append("image")
        if self.summary_label:
            roles.append("summary")
        if self.analysis_label:
            roles.append("analysis")
        return tuple(roles)

    def to_mapping(self) -> dict[str, Any]:
        return {
            "schema_version": "evaluation-run-v1",
            "run_id": self.run_id,
            "created_at": self.created_at,
            "author": self.author,
            "cik": self.cik,
            "entity_label": self.entity_label,
            "selections": {
                "parsing": self.parsing_label,
                "image": self.image_label,
                "summary": self.summary_label,
                "analysis": self.analysis_label,
            },
            "timeframe": {"from": self.from_date, "to": self.to_date},
            "preferred_region": self.preferred_region,
            "cost_ceiling_usd": str(self.cost_ceiling_usd),
            "job_ids": list(self.job_ids),
            "closed_at": self.closed_at,
            "note": self.note,
        }

    @classmethod
    def from_mapping(cls, raw: dict[str, Any]) -> RunRecord:
        where = "run"
        selections = raw.get("selections") or {}
        timeframe = raw.get("timeframe") or {}
        if not isinstance(selections, dict) or "parsing" not in selections:
            raise RecordFormatError("run.selections must carry at least a parsing model")
        return cls(
            run_id=_text(raw, "run_id", where),
            created_at=_text(raw, "created_at", where),
            author=_text(raw, "author", where),
            cik=_text(raw, "cik", where),
            entity_label=_text(raw, "entity_label", where),
            parsing_label=str(selections["parsing"]),
            image_label=_optional_text(selections, "image"),
            summary_label=_optional_text(selections, "summary"),
            analysis_label=_optional_text(selections, "analysis"),
            from_date=_optional_text(timeframe, "from"),
            to_date=_optional_text(timeframe, "to"),
            preferred_region=str(raw.get("preferred_region") or ""),
            cost_ceiling_usd=_decimal(raw, "cost_ceiling_usd", where),
            job_ids=[str(j) for j in (raw.get("job_ids") or ())],
            closed_at=_optional_text(raw, "closed_at"),
            note=_optional_text(raw, "note"),
        )


@dataclass
class JobRecord:
    """One filing, one parsing model, one independent unit of billable work.

    A multi-year request never becomes one invocation. Each filing gets one of these, with its own
    identifier, its own source set, its own preflight, its own cost and its own review state.

    `source_set`, `validation` and `image_coverage` are opaque mappings written by the packages
    that own those concepts. This record stores and returns them; it does not read inside them.
    """

    job_id: str
    parent_run_id: str
    created_at: str
    updated_at: str
    cik: str
    accession: str
    form_as_filed: str
    filing_date: str
    issuer_label: str
    transport_era: str
    routing: ModelRouting
    prompt: PromptIdentity
    settings: ParserSettings
    report_period: str | None = None
    execution_state: ExecutionState = ExecutionState.CREATED
    review_state: ReviewState = ReviewState.EVALUATION
    #: Which protocol produced this job's artifact. `single_response` is the Phase 2 protocol and
    #: is what every stored historical job is; `multipart` is the model-directed protocol Phase 2.1
    #: added. It is RECORDED rather than inferred from the presence of tasks, because a multipart
    #: job that failed before its plan returned has no tasks and is still a multipart job.
    strategy: str = "single_response"
    #: The multipart session summary — plan identity, depth, cycles, budget, assembly status — as
    #: an opaque mapping written by `packages/orchestrator`. Same discipline as `source_set` and
    #: `validation`: this record stores and returns it and never reads inside it.
    multipart: dict[str, Any] | None = None
    #: The maximum this ONE filing's parse may spend, across every task it queues. Distinct from
    #: the cumulative ceiling in the durable journal: a run must not be able to exhaust the whole
    #: authorized budget on one filing merely because it planned a lot of parts.
    budget_ceiling_usd: Decimal | None = None
    source_set_id: str | None = None
    source_set: dict[str, Any] | None = None
    validation: dict[str, Any] | None = None
    image_coverage: dict[str, Any] | None = None
    incompatibility: Incompatibility | None = None
    attempts: list[InvocationAttempt] = field(default_factory=list)
    review_history: list[ReviewTransition] = field(default_factory=list)
    reserved_cost_usd: Decimal | None = None
    actual_cost_usd: Decimal | None = None
    estimated_input_tokens: int | None = None
    failure: str | None = None

    def to_mapping(self) -> dict[str, Any]:
        # v2 ADDS FIELDS AND REMOVES NONE. A v1 document reads back through `from_mapping`
        # unchanged, because every field Phase 2.1 introduced is optional with a default that
        # describes what a Phase 2 job actually was: the single-response protocol, no multipart
        # session, no per-filing budget.
        return {
            "schema_version": "evaluation-job-v2",
            "job_id": self.job_id,
            "parent_run_id": self.parent_run_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "filing": {
                "cik": self.cik,
                "accession": self.accession,
                "form_as_filed": self.form_as_filed,
                "filing_date": self.filing_date,
                "report_period": self.report_period,
                "issuer_label": self.issuer_label,
                "transport_era": self.transport_era,
            },
            "model_routing": self.routing.to_mapping(),
            "prompt": self.prompt.to_mapping(),
            "settings": self.settings.to_mapping(),
            "execution_state": self.execution_state.value,
            "review_state": self.review_state.value,
            "strategy": self.strategy,
            "multipart": self.multipart,
            "budget_ceiling_usd": (
                None if self.budget_ceiling_usd is None else str(self.budget_ceiling_usd)
            ),
            "source_set_id": self.source_set_id,
            "source_set": self.source_set,
            "validation": self.validation,
            "image_coverage": self.image_coverage,
            "incompatibility": (
                self.incompatibility.to_mapping() if self.incompatibility else None
            ),
            "attempts": [a.to_mapping() for a in self.attempts],
            "review_history": [t.to_mapping() for t in self.review_history],
            "reserved_cost_usd": (
                None if self.reserved_cost_usd is None else str(self.reserved_cost_usd)
            ),
            "actual_cost_usd": (
                None if self.actual_cost_usd is None else str(self.actual_cost_usd)
            ),
            "estimated_input_tokens": self.estimated_input_tokens,
            "failure": self.failure,
        }

    @classmethod
    def from_mapping(cls, raw: dict[str, Any]) -> JobRecord:
        where = "job"
        filing = raw.get("filing")
        if not isinstance(filing, dict):
            raise RecordFormatError("job.filing must be a mapping")
        routing_raw = raw.get("model_routing")
        if not isinstance(routing_raw, dict):
            raise RecordFormatError("job.model_routing must be a mapping")
        prompt_raw = raw.get("prompt")
        if not isinstance(prompt_raw, dict):
            raise RecordFormatError("job.prompt must be a mapping")
        settings_raw = raw.get("settings")
        if not isinstance(settings_raw, dict):
            raise RecordFormatError("job.settings must be a mapping")
        incompatible_raw = raw.get("incompatibility")
        return cls(
            job_id=_text(raw, "job_id", where),
            parent_run_id=_text(raw, "parent_run_id", where),
            created_at=_text(raw, "created_at", where),
            updated_at=_text(raw, "updated_at", where),
            cik=_text(filing, "cik", "job.filing"),
            accession=_text(filing, "accession", "job.filing"),
            form_as_filed=_text(filing, "form_as_filed", "job.filing"),
            filing_date=_text(filing, "filing_date", "job.filing"),
            issuer_label=_text(filing, "issuer_label", "job.filing"),
            transport_era=_text(filing, "transport_era", "job.filing"),
            report_period=_optional_text(filing, "report_period"),
            routing=ModelRouting.from_mapping(routing_raw),
            prompt=PromptIdentity.from_mapping(prompt_raw),
            settings=ParserSettings.from_mapping(settings_raw),
            execution_state=ExecutionState(_text(raw, "execution_state", where)),
            review_state=ReviewState(_text(raw, "review_state", where)),
            strategy=str(raw.get("strategy") or "single_response"),
            multipart=raw.get("multipart"),
            budget_ceiling_usd=_optional_decimal(raw, "budget_ceiling_usd"),
            source_set_id=_optional_text(raw, "source_set_id"),
            source_set=raw.get("source_set"),
            validation=raw.get("validation"),
            image_coverage=raw.get("image_coverage"),
            incompatibility=(
                Incompatibility.from_mapping(incompatible_raw)
                if isinstance(incompatible_raw, dict)
                else None
            ),
            attempts=[InvocationAttempt.from_mapping(a) for a in (raw.get("attempts") or ())],
            review_history=[
                ReviewTransition.from_mapping(t) for t in (raw.get("review_history") or ())
            ],
            reserved_cost_usd=_optional_decimal(raw, "reserved_cost_usd"),
            actual_cost_usd=_optional_decimal(raw, "actual_cost_usd"),
            estimated_input_tokens=raw.get("estimated_input_tokens"),
            failure=_optional_text(raw, "failure"),
        )
