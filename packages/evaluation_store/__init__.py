"""Durable evaluation storage for parser experiments — NOT the product database.

WHY THIS PACKAGE EXISTS. A parsed artifact cannot be judged without looking at it beside the
filing it came from, and a review session that loses its work on a page reload is not a review
session. This package is the smallest durable thing that makes reviewing possible: parent runs,
child filing jobs, exact request and response evidence, an append-only event log, developer
comments, and two independent state machines.

WHY IT IS NOT THE PRODUCT DATABASE, AND WHY THAT DISTINCTION IS LOAD-BEARING. rules.md invariant
15 and section 21 rule 13: persistence follows measured model output. A 24-table PostgreSQL schema
was once designed before a single model had parsed a filing, it encoded an interpretation no model
had produced, and it was deleted (ADR-0017). Nothing here is a schema. There is no relational
model, no migration, no index, no query language, and no representation of what a filing contains
— a source set, a validation result and an image-coverage report all arrive as opaque mappings
written by the packages that own those concepts.

APPROVAL EXISTS HERE; REUSE DOES NOT. A reviewer can mark an artifact APPROVED, and that records a
judgement and nothing more. No search consults this store, no cache is populated, and no artifact
becomes a trusted result. roadmap.md Phase 4 is where that gate is designed, from artifacts that
by then will actually exist.
"""

from .errors import (
    EvaluationStoreError,
    IllegalTransitionError,
    InvalidIdentifierError,
    JobNotFoundError,
    RecordFormatError,
    RunNotFoundError,
)
from .identity import (
    is_comment_id,
    is_job_id,
    is_run_id,
    new_comment_id,
    new_job_id,
    new_run_id,
    require_comment_id,
    require_job_id,
    require_run_id,
)
from .records import (
    Comment,
    Incompatibility,
    InvocationAttempt,
    JobRecord,
    ModelRouting,
    ParserSettings,
    PromptIdentity,
    ReviewTransition,
    RunEvent,
    RunRecord,
    utc_now,
)
from .states import (
    RESUMABLE_EXECUTION_STATES,
    TERMINAL_EXECUTION_STATES,
    ExecutionState,
    ReviewState,
    assert_execution_transition,
    assert_review_transition,
    permitted_execution_transitions,
    permitted_review_transitions,
)
from .store import EvaluationStore, summarise_run

__all__ = [
    "RESUMABLE_EXECUTION_STATES",
    "TERMINAL_EXECUTION_STATES",
    "Comment",
    "EvaluationStore",
    "EvaluationStoreError",
    "ExecutionState",
    "IllegalTransitionError",
    "Incompatibility",
    "InvalidIdentifierError",
    "InvocationAttempt",
    "JobNotFoundError",
    "JobRecord",
    "ModelRouting",
    "ParserSettings",
    "PromptIdentity",
    "RecordFormatError",
    "ReviewState",
    "ReviewTransition",
    "RunEvent",
    "RunNotFoundError",
    "RunRecord",
    "assert_execution_transition",
    "assert_review_transition",
    "is_comment_id",
    "is_job_id",
    "is_run_id",
    "new_comment_id",
    "new_job_id",
    "new_run_id",
    "permitted_execution_transitions",
    "permitted_review_transitions",
    "require_comment_id",
    "require_job_id",
    "require_run_id",
    "summarise_run",
    "utc_now",
]
