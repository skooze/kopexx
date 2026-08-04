"""Two independent state machines: what a child job DID, and what a reviewer DECIDED about it.

THEY ARE NEVER COLLAPSED, AND THAT IS THE POINT. An execution state describes machinery: bytes
were assembled, a provider answered, validation ran. A review state describes a human judgement:
this artifact is good enough to reuse, or it is not. Deriving one from the other is how an
unreviewed artifact acquires the authority of an approved one — a job reaching READY_FOR_REVIEW
says only that a person can now look at it.

TRANSITIONS ARE ENUMERATED RATHER THAN CHECKED AD HOC. A table can be read, tested exhaustively
and extended in one place. A scattering of `if state == ...` cannot, and the first thing it loses
is the illegal transition nobody thought to forbid.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final

from .errors import IllegalTransitionError


class ExecutionState(StrEnum):
    """Where a child filing job is in its machinery."""

    CREATED = "CREATED"
    SOURCE_READY = "SOURCE_READY"
    PREFLIGHT = "PREFLIGHT"
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    RESPONSE_RECEIVED = "RESPONSE_RECEIVED"
    VALIDATING = "VALIDATING"
    READY_FOR_REVIEW = "READY_FOR_REVIEW"
    FAILED = "FAILED"
    INCOMPATIBLE = "INCOMPATIBLE"
    INTERRUPTED = "INTERRUPTED"
    CANCELLED = "CANCELLED"


class ReviewState(StrEnum):
    """What a reviewer has decided about the artifact a job produced.

    EVALUATION is the state every artifact starts in and stays in until someone acts. Nothing in
    this project treats an EVALUATION artifact as a reusable result; roadmap.md Phase 4 is where
    APPROVED starts to mean something operational, and that gate is not switched on here.
    """

    EVALUATION = "EVALUATION"
    UNDER_REVIEW = "UNDER_REVIEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    SUPERSEDED = "SUPERSEDED"
    INVALIDATED = "INVALIDATED"


#: States from which no further execution transition is possible.
TERMINAL_EXECUTION_STATES: Final[frozenset[ExecutionState]] = frozenset(
    {
        ExecutionState.READY_FOR_REVIEW,
        ExecutionState.FAILED,
        ExecutionState.INCOMPATIBLE,
        ExecutionState.INTERRUPTED,
        ExecutionState.CANCELLED,
    }
)

#: States a job can be found in after a process died mid-run. On restart every one of these
#: becomes INTERRUPTED, and NOTHING reruns automatically: a rerun spends money, and money is
#: never spent by a process that merely came back up.
RESUMABLE_EXECUTION_STATES: Final[frozenset[ExecutionState]] = frozenset(
    {
        ExecutionState.CREATED,
        ExecutionState.SOURCE_READY,
        ExecutionState.PREFLIGHT,
        ExecutionState.QUEUED,
        ExecutionState.RUNNING,
        ExecutionState.RESPONSE_RECEIVED,
        ExecutionState.VALIDATING,
    }
)

_EXECUTION_TRANSITIONS: Final[dict[ExecutionState, frozenset[ExecutionState]]] = {
    ExecutionState.CREATED: frozenset(
        {
            ExecutionState.SOURCE_READY,
            ExecutionState.FAILED,
            ExecutionState.INCOMPATIBLE,
            ExecutionState.INTERRUPTED,
            ExecutionState.CANCELLED,
        }
    ),
    ExecutionState.SOURCE_READY: frozenset(
        {
            ExecutionState.PREFLIGHT,
            ExecutionState.FAILED,
            ExecutionState.INCOMPATIBLE,
            ExecutionState.INTERRUPTED,
            ExecutionState.CANCELLED,
        }
    ),
    ExecutionState.PREFLIGHT: frozenset(
        {
            ExecutionState.QUEUED,
            ExecutionState.FAILED,
            ExecutionState.INCOMPATIBLE,
            ExecutionState.INTERRUPTED,
            ExecutionState.CANCELLED,
        }
    ),
    ExecutionState.QUEUED: frozenset(
        {
            ExecutionState.RUNNING,
            ExecutionState.FAILED,
            ExecutionState.INTERRUPTED,
            ExecutionState.CANCELLED,
        }
    ),
    # RUNNING may not go to CANCELLED. A provider call that has already been issued is billable
    # whatever the browser does next, and marking it cancelled would hide a charge the ledger
    # has to settle. It becomes INTERRUPTED or it completes.
    ExecutionState.RUNNING: frozenset(
        {
            ExecutionState.RESPONSE_RECEIVED,
            ExecutionState.FAILED,
            ExecutionState.INTERRUPTED,
        }
    ),
    ExecutionState.RESPONSE_RECEIVED: frozenset(
        {
            ExecutionState.VALIDATING,
            ExecutionState.FAILED,
            ExecutionState.INTERRUPTED,
        }
    ),
    # VALIDATING never goes to FAILED for a validation VERDICT. A parse that fails coverage or
    # returns unparseable YAML still reaches READY_FOR_REVIEW carrying that verdict, because the
    # response was bought and a human has to see it. FAILED here means validation itself broke.
    ExecutionState.VALIDATING: frozenset(
        {
            ExecutionState.READY_FOR_REVIEW,
            ExecutionState.FAILED,
            ExecutionState.INTERRUPTED,
        }
    ),
    ExecutionState.READY_FOR_REVIEW: frozenset(),
    ExecutionState.FAILED: frozenset(),
    ExecutionState.INCOMPATIBLE: frozenset(),
    # INTERRUPTED REOPENS, AND ONLY THROUGH AN EXPLICIT USER ACTION. Added in Phase 2.1, because a
    # multipart parse can be interrupted with half its parts already bought and then legitimately
    # resumed — and under the old table the child job stayed INTERRUPTED for ever while every task
    # beneath it succeeded, so a finished parse could never reach review. That is the same shape as
    # `TaskState.INTERRUPTED -> READY` one level down, and it is reached the same way: a person
    # asks. Nothing automatic uses this edge; `mark_interrupted_jobs` still only ever moves work
    # INTO this state, and a restart still re-invokes nothing.
    ExecutionState.INTERRUPTED: frozenset({ExecutionState.RUNNING}),
    ExecutionState.CANCELLED: frozenset(),
}

_REVIEW_TRANSITIONS: Final[dict[ReviewState, frozenset[ReviewState]]] = {
    ReviewState.EVALUATION: frozenset(
        {
            ReviewState.UNDER_REVIEW,
            ReviewState.APPROVED,
            ReviewState.REJECTED,
            ReviewState.INVALIDATED,
        }
    ),
    ReviewState.UNDER_REVIEW: frozenset(
        {
            ReviewState.APPROVED,
            ReviewState.REJECTED,
            ReviewState.EVALUATION,
            ReviewState.INVALIDATED,
        }
    ),
    # An approved artifact is never edited back to unapproved. It is SUPERSEDED by a newer one or
    # INVALIDATED, both of which leave the original readable — rules.md invariant 7.
    ReviewState.APPROVED: frozenset({ReviewState.SUPERSEDED, ReviewState.INVALIDATED}),
    ReviewState.REJECTED: frozenset({ReviewState.UNDER_REVIEW, ReviewState.INVALIDATED}),
    ReviewState.SUPERSEDED: frozenset({ReviewState.INVALIDATED}),
    ReviewState.INVALIDATED: frozenset(),
}


def permitted_execution_transitions(state: ExecutionState) -> frozenset[ExecutionState]:
    """Every execution state reachable in one step from ``state``."""
    return _EXECUTION_TRANSITIONS[state]


def permitted_review_transitions(state: ReviewState) -> frozenset[ReviewState]:
    """Every review state reachable in one step from ``state``."""
    return _REVIEW_TRANSITIONS[state]


def assert_execution_transition(current: ExecutionState, requested: ExecutionState) -> None:
    """Permit the transition or refuse it, naming what was allowed."""
    allowed = _EXECUTION_TRANSITIONS[current]
    if requested not in allowed:
        permitted = ", ".join(sorted(s.value for s in allowed)) or "nothing; it is terminal"
        raise IllegalTransitionError(
            f"a child job in {current.value} cannot move to {requested.value}; "
            f"permitted from here: {permitted}",
            current=current.value,
            requested=requested.value,
        )


def assert_review_transition(current: ReviewState, requested: ReviewState) -> None:
    """Permit the review transition or refuse it, naming what was allowed."""
    allowed = _REVIEW_TRANSITIONS[current]
    if requested not in allowed:
        permitted = ", ".join(sorted(s.value for s in allowed)) or "nothing; it is terminal"
        raise IllegalTransitionError(
            f"an artifact in {current.value} cannot move to {requested.value}; "
            f"permitted from here: {permitted}",
            current=current.value,
            requested=requested.value,
        )
