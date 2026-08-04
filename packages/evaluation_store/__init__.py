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
    BenchmarkTruthVersionExistsError,
    EvaluationStoreError,
    IllegalTransitionError,
    InvalidIdentifierError,
    JobNotFoundError,
    RecordFormatError,
    RunNotFoundError,
    TaskNotFoundError,
)
from .identity import (
    is_comment_id,
    is_job_id,
    is_run_id,
    is_task_id,
    new_attempt_salt,
    new_comment_id,
    new_job_id,
    new_run_id,
    new_task_id,
    require_comment_id,
    require_job_id,
    require_run_id,
    require_task_id,
)
from .queue_states import (
    BILLABLE_TASK_TYPES,
    CANCELLABLE_TASK_STATES,
    RESUMABLE_TASK_STATES,
    TERMINAL_TASK_STATES,
    DependencyPolicy,
    TaskState,
    TaskType,
    assert_task_transition,
    dependencies_satisfied,
    permitted_task_transitions,
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
from .store import EvaluationStore, summarise_run, summarise_tasks
from .tasks import MultipartTask, idempotency_key, new_task

__all__ = [
    "BILLABLE_TASK_TYPES",
    "CANCELLABLE_TASK_STATES",
    "RESUMABLE_EXECUTION_STATES",
    "RESUMABLE_TASK_STATES",
    "TERMINAL_EXECUTION_STATES",
    "TERMINAL_TASK_STATES",
    "BenchmarkTruthVersionExistsError",
    "Comment",
    "DependencyPolicy",
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
    "MultipartTask",
    "ParserSettings",
    "PromptIdentity",
    "RecordFormatError",
    "ReviewState",
    "ReviewTransition",
    "RunEvent",
    "RunNotFoundError",
    "RunRecord",
    "TaskNotFoundError",
    "TaskState",
    "TaskType",
    "assert_execution_transition",
    "assert_review_transition",
    "assert_task_transition",
    "dependencies_satisfied",
    "idempotency_key",
    "is_comment_id",
    "is_job_id",
    "is_run_id",
    "is_task_id",
    "new_attempt_salt",
    "new_comment_id",
    "new_job_id",
    "new_run_id",
    "new_task",
    "new_task_id",
    "permitted_execution_transitions",
    "permitted_review_transitions",
    "permitted_task_transitions",
    "require_comment_id",
    "require_job_id",
    "require_run_id",
    "require_task_id",
    "summarise_run",
    "summarise_tasks",
    "utc_now",
]
