"""Which artifact CURRENTLY holds a part's content, when more than one exists for it.

THE PROBLEM, STATED AS THE DEFECT IT WAS. A part whose response would not parse is preserved with
`readable: False` and an empty envelope. A FORMAT_REPAIR of it may succeed and carry the same
model-created identifier, real nodes and real references. Two preserved artifacts, one part. Commit
f70c9f3 taught the ASSEMBLY INDEX to read the second — and left every other consumer reading the
first, so the reconciliation brief was shown `node_count 0` for a part that had two nodes, four of
the five mechanical findings could not fire for it, and the review UI offered no way to reach the
repair from the original or the original from the repair.

    A FALSE EMPTY IS THE INVERSE OF A FALSE COMPLETE AND IT IS EXACTLY AS UNTRUE. This repository
    spends considerable effort making sure uncertainty produces PARTIAL or REVIEW_REQUIRED rather
    than a false complete. Content that exists, reported as absent, had no guard at all.

WHY THIS IS A PACKAGE-LEVEL FUNCTION AND NOT A PRIVATE METHOD. It was 44 lines inside a 2,000-line
service with one call site, and the reason six other consumers disagreed with it is that they could
not reach it. A resolver every consumer shares is the only shape in which "the effective artifact"
means one thing.

THREE FACTS ARE KEPT SEPARATE AND MUST NEVER BE COLLAPSED, because collapsing them is how a model
gets credit for something it did not do:

    RAW PARSEABILITY      did the model's own response parse
    REPAIR PARSEABILITY   did a repair of it parse
    EFFECTIVE USABILITY   is there, now, a readable artifact for this part

A parse that needed a repair is usable AND its model did not serialise correctly. Reporting only the
first hides working evidence; reporting only the second credits a model with a document it did not
produce.

NOTHING IS EVER REPLACED OR REWRITTEN. The malformed original stays exactly as the provider returned
it, keeps its own task record, and stays one click away in the review UI. `rules.md` invariant 7:
supersede, never overwrite.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


class ArtifactTask(Protocol):
    """The shape this module needs from a durable task record.

    A PROTOCOL RATHER THAN AN IMPORT, DELIBERATELY. `packages/evaluation_store` owns the task
    record and `packages/multipart` owns the envelopes; making this module import the store would
    put a dependency edge between two packages that have managed without one, for the sake of five
    attribute reads. It also means the resolver is testable against a five-line stub.
    """

    @property
    def task_id(self) -> str: ...
    @property
    def parent_task_id(self) -> str | None: ...
    @property
    def order(self) -> int: ...
    @property
    def envelope(self) -> dict[str, Any] | None: ...
    @property
    def task_type(self) -> Any: ...
    @property
    def state(self) -> Any: ...


@dataclass(frozen=True)
class Supersession:
    """One part task and the repair that now carries its content."""

    original_task_id: str
    effective_task_id: str

    def to_mapping(self) -> dict[str, Any]:
        return {
            "original_task_id": self.original_task_id,
            "effective_task_id": self.effective_task_id,
            "note": (
                "the original is preserved exactly as the provider returned it and is never "
                "replaced; this records which artifact currently holds the part's content"
            ),
        }


class EffectiveArtifacts[TaskT: ArtifactTask]:
    """A resolver from a part task to whichever artifact currently holds its content.

    GENERIC OVER THE CALLER'S OWN TASK TYPE, so `effective(task)` hands back the caller's record
    rather than the narrow protocol view. A resolver that returned the protocol would force every
    consumer to cast, and a cast is where the type check stops being a check.

    Built once per read of a job's tasks and shared by every consumer: the assembly index, the
    reconciliation inventory, the mechanical findings, the task list, the API and the UI. One
    resolver is what makes "effective" a fact about the job rather than an opinion of whichever
    function happened to ask.
    """

    def __init__(self, mapping: dict[str, TaskT]) -> None:
        self._by_original = mapping
        self._by_effective = {task.task_id: original for original, task in mapping.items()}

    def effective(self, task: TaskT) -> TaskT:
        """The artifact holding this task's content — itself when nothing superseded it."""
        return self._by_original.get(task.task_id, task)

    def superseded(self, task_id: str) -> bool:
        """Whether a later artifact carries this task's content."""
        return task_id in self._by_original

    def superseded_by(self, task_id: str) -> str | None:
        """The task id of the artifact that carries this one's content, if any."""
        replacement = self._by_original.get(task_id)
        return replacement.task_id if replacement is not None else None

    def supersedes(self, task_id: str) -> str | None:
        """The task id whose content this artifact carries, if it carries another's."""
        return self._by_effective.get(task_id)

    def __len__(self) -> int:
        return len(self._by_original)

    def supersessions(self) -> tuple[Supersession, ...]:
        return tuple(
            Supersession(original, task.task_id)
            for original, task in sorted(self._by_original.items())
        )


def resolve_effective[TaskT: ArtifactTask](
    tasks: list[TaskT],
    *,
    part_types: frozenset[Any],
    repair_type: Any,
    succeeded_state: Any,
) -> EffectiveArtifacts[TaskT]:
    """Map every part task to the successful format repair that carries its content, if any.

    A REPAIR IS ONLY SUBSTITUTED WHEN IT ACTUALLY PRODUCED A PART. Two ways it may not have. A
    repair whose own response would not parse is recorded with `readable: False` and is no
    improvement on the original; substituting it would swap one unreadable artifact for another and
    lose the first one's place in the index. A repair of something that is not a part carries a
    bookkeeping envelope with no `node_count` at all. Requiring the key the part interpreter writes
    admits only the case that means anything here. Measured on a real Phase 2.1 run: eight repairs
    were attempted and exactly ONE returned a readable part envelope.

    CHAINS ARE STILL FOLLOWED, BECAUSE PRESERVED RUNS CONTAIN THEM. A repair of a repair can no
    longer be created — the allowance is counted per ARTIFACT rather than per link, which is the
    defect commit f70c9f3 closed — but a run recorded before that must still resolve to the artifact
    holding its content rather than to the middle of a chain, and the walk costs nothing.

    THE TYPES ARE PARAMETERS RATHER THAN IMPORTS for the reason in `ArtifactTask`: this package does
    not import the store's enums, and a caller that has them passes them in.
    """
    by_id = {task.task_id: task for task in tasks}
    resolved: dict[str, TaskT] = {}
    for repair in tasks:
        if repair.task_type is not repair_type or repair.state is not succeeded_state:
            continue
        envelope = repair.envelope or {}
        if envelope.get("readable") is False or "node_count" not in envelope:
            continue
        origin = by_id.get(repair.parent_task_id or "")
        seen = {repair.task_id}
        while origin is not None and origin.task_type is repair_type:
            if origin.task_id in seen:  # a cycle cannot happen; refusing to loop is free
                origin = None
                break
            seen.add(origin.task_id)
            origin = by_id.get(origin.parent_task_id or "")
        if origin is None or origin.task_type not in part_types:
            continue
        existing = resolved.get(origin.task_id)
        if existing is None or repair.order >= existing.order:
            resolved[origin.task_id] = repair
    return EffectiveArtifacts(resolved)
