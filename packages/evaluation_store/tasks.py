"""One durable unit of queued multipart work, and the session record that groups them.

WHAT A TASK RECORD HAS TO SURVIVE. A process restart, a browser reload, a partial branch retry and
a reviewer opening it three days later. Everything the scheduler needs to decide whether a task may
run, everything the ledger needs to settle it, and everything the review UI needs to show it, is
written here — not held in the worker, which holds nothing.

WHY THE MODEL-CREATED IDENTIFIERS ARE CARRIED VERBATIM AND SEPARATELY FROM THE STORAGE TOKEN. The
selected parsing model chooses `part_id`. That string is opaque to this repository: it is never
interpreted, never normalised into a vocabulary, and never rewritten. It is also, unavoidably,
about to become part of a filesystem path — so a mechanically derived `storage_token` travels
beside it, and the EXACT value the model returned is what is displayed, compared and reported.
Losing the exact one to make the path safe would be the backend quietly renaming the model's work.

WHY `depends_on` IS A DURABLE LIST AND NOT A POLL. Two tasks writing files in the same directory
and a third watching for them is a race dressed as a scheduler. A task names the tasks it waits
for, records the policy under which they count as satisfied, and becomes READY when a pass over
those records says so.

IDEMPOTENCY IS AN IDENTITY, NOT A LOCK. `idempotency_key` is derived from everything that changes
what comes back — the source set, the model, the region, the prompt bytes, the task type, the plan
and part identity, the parent artifact and the request settings. Before a billable attempt the
scheduler looks for an already SUCCEEDED task carrying the same key and skips rather than paying
twice. It claims nothing about the provider: an explicit rerun mints a new `attempt_salt`, which
makes a new identity, which is exactly what a rerun should be.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from .errors import RecordFormatError
from .queue_states import DependencyPolicy, TaskState, TaskType
from .records import (
    InvocationAttempt,
    ModelRouting,
    ParserSettings,
    PromptIdentity,
    utc_now,
)


def _text(mapping: dict[str, Any], key: str, where: str) -> str:
    if key not in mapping:
        raise RecordFormatError(f"{where} is missing required field {key!r}")
    value = mapping[key]
    if not isinstance(value, str):
        raise RecordFormatError(
            f"{where}.{key} must be a quoted string, got {type(value).__name__} ({value!r})"
        )
    return value


def _optional_text(mapping: dict[str, Any], key: str) -> str | None:
    value = mapping.get(key)
    return None if value is None else str(value)


def _optional_decimal(mapping: dict[str, Any], key: str) -> Decimal | None:
    value = mapping.get(key)
    return None if value is None else Decimal(str(value))


def idempotency_key(
    *,
    source_set_id: str,
    model_label: str,
    invocation_id: str,
    region: str,
    prompt_identity: str,
    prompt_sha256: str,
    task_type: str,
    plan_id: str,
    part_id: str,
    parent_artifact_sha256: str,
    max_output_tokens: int,
    temperature: float,
    attempt_salt: str,
) -> str:
    """A stable identity for one billable attempt's inputs.

    Every argument is something that changes what the provider would return. Nothing that does not
    is included — not the task identifier, not the timestamp, not the run — because two tasks with
    identical inputs SHOULD collide, and that collision is the whole protection.
    """
    joined = "\n".join(
        (
            source_set_id,
            model_label,
            invocation_id,
            region,
            prompt_identity,
            prompt_sha256,
            task_type,
            plan_id,
            part_id,
            parent_artifact_sha256,
            str(max_output_tokens),
            f"{temperature:.6f}",
            attempt_salt,
        )
    )
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


@dataclass
class MultipartTask:
    """One queued unit of work inside one filing's multipart parse."""

    task_id: str
    run_id: str
    root_job_id: str
    parent_task_id: str | None
    task_type: TaskType
    created_at: str
    updated_at: str
    routing: ModelRouting
    prompt: PromptIdentity
    settings: ParserSettings
    state: TaskState = TaskState.CREATED
    depth: int = 0
    order: int = 0
    #: The model's own identifiers, carried verbatim. Empty for a task that predates a plan.
    plan_id: str = ""
    part_id: str = ""
    parent_part_id: str | None = None
    storage_token: str = ""
    #: The model-created part specification this task was asked to produce, as an opaque mapping.
    part_spec: dict[str, Any] | None = None
    source_set_id: str = ""
    depends_on: list[str] = field(default_factory=list)
    dependency_policy: DependencyPolicy = DependencyPolicy.ALL_SUCCEEDED
    idempotency: str = ""
    attempt_salt: str = ""
    input_artifact_ids: list[str] = field(default_factory=list)
    output_artifact_ids: list[str] = field(default_factory=list)
    attempts: list[InvocationAttempt] = field(default_factory=list)
    reserved_cost_usd: Decimal | None = None
    actual_cost_usd: Decimal | None = None
    estimated_input_tokens: int | None = None
    output_target_tokens: int | None = None
    started_at: str | None = None
    finished_at: str | None = None
    error: str | None = None
    blocked_reason: str | None = None
    truncation: dict[str, Any] | None = None
    validation: dict[str, Any] | None = None
    envelope: dict[str, Any] | None = None
    note: str = ""

    @property
    def attempt_count(self) -> int:
        return len(self.attempts)

    @property
    def label(self) -> str:
        """A short human label for the hierarchy view. Model words where the model supplied them."""
        title = str((self.part_spec or {}).get("title") or "")
        if title:
            return title
        return self.task_type.value.replace("_", " ").lower()

    def to_mapping(self) -> dict[str, Any]:
        return {
            "schema_version": "multipart-task-v1",
            "task_id": self.task_id,
            "run_id": self.run_id,
            "root_job_id": self.root_job_id,
            "parent_task_id": self.parent_task_id,
            "task_type": self.task_type.value,
            "state": self.state.value,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "depth": self.depth,
            "order": self.order,
            "model_routing": self.routing.to_mapping(),
            "prompt": self.prompt.to_mapping(),
            "settings": self.settings.to_mapping(),
            "model_created": {
                "plan_id": self.plan_id,
                "part_id": self.part_id,
                "parent_part_id": self.parent_part_id,
                "storage_token": self.storage_token,
                "part_spec": self.part_spec,
            },
            "source_set_id": self.source_set_id,
            "depends_on": list(self.depends_on),
            "dependency_policy": self.dependency_policy.value,
            "idempotency": self.idempotency,
            "attempt_salt": self.attempt_salt,
            "input_artifact_ids": list(self.input_artifact_ids),
            "output_artifact_ids": list(self.output_artifact_ids),
            "attempts": [a.to_mapping() for a in self.attempts],
            "attempt_count": self.attempt_count,
            "reserved_cost_usd": (
                None if self.reserved_cost_usd is None else str(self.reserved_cost_usd)
            ),
            "actual_cost_usd": (
                None if self.actual_cost_usd is None else str(self.actual_cost_usd)
            ),
            "estimated_input_tokens": self.estimated_input_tokens,
            "output_target_tokens": self.output_target_tokens,
            "error": self.error,
            "blocked_reason": self.blocked_reason,
            "truncation": self.truncation,
            "validation": self.validation,
            "envelope": self.envelope,
            "note": self.note,
        }

    @classmethod
    def from_mapping(cls, raw: dict[str, Any]) -> MultipartTask:
        where = "multipart task"
        routing_raw = raw.get("model_routing")
        if not isinstance(routing_raw, dict):
            raise RecordFormatError("multipart task.model_routing must be a mapping")
        prompt_raw = raw.get("prompt")
        if not isinstance(prompt_raw, dict):
            raise RecordFormatError("multipart task.prompt must be a mapping")
        settings_raw = raw.get("settings")
        if not isinstance(settings_raw, dict):
            raise RecordFormatError("multipart task.settings must be a mapping")
        created = raw.get("model_created")
        created = created if isinstance(created, dict) else {}
        return cls(
            task_id=_text(raw, "task_id", where),
            run_id=_text(raw, "run_id", where),
            root_job_id=_text(raw, "root_job_id", where),
            parent_task_id=_optional_text(raw, "parent_task_id"),
            task_type=TaskType(_text(raw, "task_type", where)),
            created_at=_text(raw, "created_at", where),
            updated_at=_text(raw, "updated_at", where),
            routing=ModelRouting.from_mapping(routing_raw),
            prompt=PromptIdentity.from_mapping(prompt_raw),
            settings=ParserSettings.from_mapping(settings_raw),
            state=TaskState(_text(raw, "state", where)),
            depth=int(raw.get("depth") or 0),
            order=int(raw.get("order") or 0),
            plan_id=str(created.get("plan_id") or ""),
            part_id=str(created.get("part_id") or ""),
            parent_part_id=_optional_text(created, "parent_part_id"),
            storage_token=str(created.get("storage_token") or ""),
            part_spec=created.get("part_spec"),
            source_set_id=str(raw.get("source_set_id") or ""),
            depends_on=[str(d) for d in (raw.get("depends_on") or ())],
            dependency_policy=DependencyPolicy(
                str(raw.get("dependency_policy") or DependencyPolicy.ALL_SUCCEEDED.value)
            ),
            idempotency=str(raw.get("idempotency") or ""),
            attempt_salt=str(raw.get("attempt_salt") or ""),
            input_artifact_ids=[str(a) for a in (raw.get("input_artifact_ids") or ())],
            output_artifact_ids=[str(a) for a in (raw.get("output_artifact_ids") or ())],
            attempts=[InvocationAttempt.from_mapping(a) for a in (raw.get("attempts") or ())],
            reserved_cost_usd=_optional_decimal(raw, "reserved_cost_usd"),
            actual_cost_usd=_optional_decimal(raw, "actual_cost_usd"),
            estimated_input_tokens=raw.get("estimated_input_tokens"),
            output_target_tokens=raw.get("output_target_tokens"),
            started_at=_optional_text(raw, "started_at"),
            finished_at=_optional_text(raw, "finished_at"),
            error=_optional_text(raw, "error"),
            blocked_reason=_optional_text(raw, "blocked_reason"),
            truncation=raw.get("truncation"),
            validation=raw.get("validation"),
            envelope=raw.get("envelope"),
            note=str(raw.get("note") or ""),
        )


def new_task(
    *,
    task_id: str,
    run_id: str,
    root_job_id: str,
    task_type: TaskType,
    routing: ModelRouting,
    prompt: PromptIdentity,
    settings: ParserSettings,
    parent_task_id: str | None = None,
    **rest: Any,
) -> MultipartTask:
    """A task in CREATED, timestamped once so both timestamps agree on creation."""
    now = utc_now()
    return MultipartTask(
        task_id=task_id,
        run_id=run_id,
        root_job_id=root_job_id,
        parent_task_id=parent_task_id,
        task_type=task_type,
        created_at=now,
        updated_at=now,
        routing=routing,
        prompt=prompt,
        settings=settings,
        **rest,
    )
