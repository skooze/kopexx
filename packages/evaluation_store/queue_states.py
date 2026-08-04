"""The THIRD state machine: where one unit of queued multipart work is.

WHY A THIRD ONE, AND WHY IT IS NOT ALLOWED TO BORROW EITHER OF THE OTHER TWO. `states.py` already
holds two machines that are never collapsed — what a child filing job DID, and what a reviewer
DECIDED about it. A multipart parse adds a level below the child job: a plan call, N part calls,
subpart calls, a replanning call, reconciliation and gap repair, each independently queued,
independently billable, independently rerunnable and independently reviewable.

Overloading `ExecutionState` to carry that would make a job's state mean two different things
depending on which level you were looking at, and would give `READY_FOR_REVIEW` two meanings: "the
whole filing can be reviewed" and "this one part can be". The Phase 2.1 brief says plainly: do not
overload review states. This machine is separate, and the two existing ones are untouched.

TWO STATES ARE DELIBERATELY NOT TERMINAL, AND EVERY OTHER ENDING IS.

    TRUNCATED    is terminal. A truncated attempt is EVIDENCE. It is preserved exactly, it is never
                 marked complete, its partial text is never concatenated onto a later response, and
                 the work it did not finish is picked up by a NEW replanning task. Reopening it
                 would be the blind-continuation protocol this phase exists to refuse.

    INTERRUPTED  is a PAUSE, not an ending. A process that died mid-flight leaves work that a
                 person may legitimately resume, and resuming it must not mean rerunning the parts
                 that already succeeded. It reopens to READY through an explicit user action only —
                 `EvaluationStore.resume_task` — never because a server came back up.

    FAILED       reopens to READY the same way, and only that way. A retry is a second billable
                 call; it gets its own reservation and its own attempt record.

BILLABILITY IS WHAT MAKES `RUNNING -> CANCELLED` ILLEGAL. Once a provider call has been issued it is
charged whatever the browser does next, so a cancelled label would hide a charge the journal still
has to settle. A running task becomes INTERRUPTED or it completes — the same rule `states.py`
applies one level up, for the same reason.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final

from .errors import IllegalTransitionError


class TaskType(StrEnum):
    """What one queued unit of multipart work is for.

    Every value except SOURCE_PREFLIGHT, VALIDATE_ASSEMBLY and READY_FOR_REVIEW invokes the
    SELECTED PARSING MODEL exactly once per attempt and is therefore billable. The three that do
    not are mechanical and are queued anyway, so the hierarchy a reviewer sees is the hierarchy
    that actually ran rather than a rendering of it.
    """

    SOURCE_PREFLIGHT = "SOURCE_PREFLIGHT"
    PLAN_PARSE = "PLAN_PARSE"
    PARSE_PART = "PARSE_PART"
    PLAN_SUBPARTS = "PLAN_SUBPARTS"
    PARSE_SUBPART = "PARSE_SUBPART"
    REPLAN_TRUNCATED_PART = "REPLAN_TRUNCATED_PART"
    RECONCILE_PARSE = "RECONCILE_PARSE"
    GAP_REPAIR = "GAP_REPAIR"
    FORMAT_REPAIR = "FORMAT_REPAIR"
    VALIDATE_ASSEMBLY = "VALIDATE_ASSEMBLY"
    READY_FOR_REVIEW = "READY_FOR_REVIEW"


#: Task types that invoke a model and therefore cost money. Everything scheduling-related consults
#: this rather than testing a type by name, so a new mechanical task type cannot accidentally
#: acquire a cost reservation and a new billable one cannot accidentally skip it.
BILLABLE_TASK_TYPES: Final[frozenset[TaskType]] = frozenset(
    {
        TaskType.PLAN_PARSE,
        TaskType.PARSE_PART,
        TaskType.PLAN_SUBPARTS,
        TaskType.PARSE_SUBPART,
        TaskType.REPLAN_TRUNCATED_PART,
        TaskType.RECONCILE_PARSE,
        TaskType.GAP_REPAIR,
        TaskType.FORMAT_REPAIR,
    }
)


class TaskState(StrEnum):
    """Where one queued unit of multipart work is."""

    CREATED = "CREATED"
    BLOCKED = "BLOCKED"
    READY = "READY"
    RESERVED = "RESERVED"
    RUNNING = "RUNNING"
    RESPONSE_RECEIVED = "RESPONSE_RECEIVED"
    VALIDATING = "VALIDATING"
    SUCCEEDED = "SUCCEEDED"
    TRUNCATED = "TRUNCATED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    INTERRUPTED = "INTERRUPTED"
    WAITING_FOR_RECONCILIATION = "WAITING_FOR_RECONCILIATION"
    READY_FOR_REVIEW = "READY_FOR_REVIEW"


class DependencyPolicy(StrEnum):
    """When a task's dependencies are considered satisfied.

    RECORDED ON THE TASK RATHER THAN INFERRED FROM ITS TYPE. Reconciliation waits for every part to
    reach a terminal state — including TRUNCATED and FAILED, because a truncated part is exactly
    what reconciliation exists to notice. A subpart waits for its plan to SUCCEED, because there is
    nothing to parse without one. Writing that into the durable record makes it inspectable in the
    UI and testable in isolation; deriving it from the type would bury it in a scheduler branch.
    """

    ALL_SUCCEEDED = "ALL_SUCCEEDED"
    ALL_TERMINAL = "ALL_TERMINAL"


#: States from which the scheduler will never run a task again on its own.
TERMINAL_TASK_STATES: Final[frozenset[TaskState]] = frozenset(
    {
        TaskState.SUCCEEDED,
        TaskState.TRUNCATED,
        TaskState.FAILED,
        TaskState.CANCELLED,
        TaskState.READY_FOR_REVIEW,
        TaskState.INTERRUPTED,
    }
)

#: States a task can be found in after a process died mid-flight. On restart every one becomes
#: INTERRUPTED and NOTHING is re-invoked: a rerun spends money, and money is never spent by a
#: process that merely came back up.
RESUMABLE_TASK_STATES: Final[frozenset[TaskState]] = frozenset(
    {
        TaskState.CREATED,
        TaskState.BLOCKED,
        TaskState.READY,
        TaskState.RESERVED,
        TaskState.RUNNING,
        TaskState.RESPONSE_RECEIVED,
        TaskState.VALIDATING,
        TaskState.WAITING_FOR_RECONCILIATION,
    }
)

#: States a queued-but-not-yet-issued task can be cancelled from. A RESERVED or RUNNING task is not
#: among them: the call is about to be, or has been, issued and charged.
CANCELLABLE_TASK_STATES: Final[frozenset[TaskState]] = frozenset(
    {TaskState.CREATED, TaskState.BLOCKED, TaskState.READY}
)

_TASK_TRANSITIONS: Final[dict[TaskState, frozenset[TaskState]]] = {
    TaskState.CREATED: frozenset(
        {
            TaskState.BLOCKED,
            TaskState.READY,
            TaskState.CANCELLED,
            TaskState.INTERRUPTED,
            TaskState.FAILED,
        }
    ),
    TaskState.BLOCKED: frozenset(
        {
            TaskState.READY,
            TaskState.CANCELLED,
            TaskState.INTERRUPTED,
            TaskState.FAILED,
        }
    ),
    # READY -> BLOCKED is the budget pause. A task that was runnable becomes unrunnable when the
    # remaining run budget can no longer cover its conservative reservation, and it says so rather
    # than being dropped or shrunk to fit.
    TaskState.READY: frozenset(
        {
            TaskState.RESERVED,
            TaskState.BLOCKED,
            TaskState.CANCELLED,
            TaskState.INTERRUPTED,
            TaskState.FAILED,
        }
    ),
    TaskState.RESERVED: frozenset(
        {TaskState.RUNNING, TaskState.FAILED, TaskState.INTERRUPTED},
    ),
    TaskState.RUNNING: frozenset(
        {TaskState.RESPONSE_RECEIVED, TaskState.FAILED, TaskState.INTERRUPTED},
    ),
    TaskState.RESPONSE_RECEIVED: frozenset(
        {
            TaskState.VALIDATING,
            TaskState.TRUNCATED,
            TaskState.FAILED,
            TaskState.INTERRUPTED,
        }
    ),
    # VALIDATING never becomes FAILED for a validation VERDICT. A part whose YAML will not parse
    # still reaches a terminal state carrying that verdict, because the response was bought and a
    # person has to see it. FAILED here means validation itself broke.
    TaskState.VALIDATING: frozenset(
        {
            TaskState.SUCCEEDED,
            TaskState.WAITING_FOR_RECONCILIATION,
            TaskState.FAILED,
            TaskState.INTERRUPTED,
        }
    ),
    TaskState.SUCCEEDED: frozenset(
        {TaskState.WAITING_FOR_RECONCILIATION, TaskState.READY_FOR_REVIEW},
    ),
    TaskState.WAITING_FOR_RECONCILIATION: frozenset(
        {
            TaskState.READY_FOR_REVIEW,
            TaskState.FAILED,
            TaskState.INTERRUPTED,
            TaskState.CANCELLED,
        }
    ),
    # TRUNCATED is terminal. The unfinished work becomes a NEW replanning task; this record stays
    # exactly as it is, as evidence.
    TaskState.TRUNCATED: frozenset(),
    TaskState.READY_FOR_REVIEW: frozenset(),
    TaskState.CANCELLED: frozenset(),
    # Both of these reopen, and ONLY through an explicit user action that takes a new reservation.
    TaskState.FAILED: frozenset({TaskState.READY}),
    TaskState.INTERRUPTED: frozenset({TaskState.READY}),
}


def permitted_task_transitions(state: TaskState) -> frozenset[TaskState]:
    """Every task state reachable in one step from ``state``."""
    return _TASK_TRANSITIONS[state]


def assert_task_transition(current: TaskState, requested: TaskState) -> None:
    """Permit the transition or refuse it, naming what was allowed."""
    allowed = _TASK_TRANSITIONS[current]
    if requested not in allowed:
        permitted = ", ".join(sorted(s.value for s in allowed)) or "nothing; it is terminal"
        raise IllegalTransitionError(
            f"a multipart task in {current.value} cannot move to {requested.value}; "
            f"permitted from here: {permitted}",
            current=current.value,
            requested=requested.value,
        )


def dependencies_satisfied(
    states: list[TaskState], policy: DependencyPolicy = DependencyPolicy.ALL_SUCCEEDED
) -> bool:
    """Whether a task whose dependencies are in ``states`` may become READY.

    An empty dependency list is satisfied. That is not a special case being smuggled in: the first
    task of a parse — the plan — genuinely depends on nothing, and a scheduler that treated "no
    dependencies" as "not satisfied" would never start.
    """
    if policy is DependencyPolicy.ALL_SUCCEEDED:
        return all(state is TaskState.SUCCEEDED for state in states)
    return all(state in TERMINAL_TASK_STATES for state in states)
