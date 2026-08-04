"""Typed errors for the evaluation store.

Every one of these is raised INSTEAD of returning something plausible. The store holds the only
copy of a model response that cost real money and cannot be regenerated for free, so a
half-written manifest, an unrecognised identifier or an illegal state transition is a failure,
never something to paper over.
"""

from __future__ import annotations


class EvaluationStoreError(Exception):
    """Base class for every evaluation-store failure."""


class InvalidIdentifierError(EvaluationStoreError):
    """An identifier is not one this store issued.

    SECURITY-INVARIANT. Identifiers arrive from HTTP paths. They are validated against their
    exact issued shape before they are ever used to build a storage key, so a caller cannot
    reach a directory by naming it.
    """


class RunNotFoundError(EvaluationStoreError):
    """No run exists under that identifier."""


class JobNotFoundError(EvaluationStoreError):
    """No child job exists under that identifier."""


class TaskNotFoundError(EvaluationStoreError):
    """No multipart task exists under that identifier, inside that child job."""


class RecordFormatError(EvaluationStoreError):
    """A stored manifest is missing a required field or carries the wrong shape.

    Deliberately fatal rather than defaulted. A manifest that lost its model identity or its
    review state would otherwise produce a record that looks complete and is not.
    """


class BenchmarkTruthVersionExistsError(EvaluationStoreError):
    """A benchmark-truth version is already on disk under that filing.

    The truth document is SUPERSEDED, NEVER OVERWRITTEN — `rules.md` invariant 7 — so writing
    version 4 over a stored version 4 is refused rather than accepted. The defect it prevents is
    concrete: a completeness figure computed against version 3 means nothing if version 3 can be
    edited under its own name, and two reviewers classifying the same filing in two browser tabs
    both read version 3 and both write version 4.

    THIS IS A CHECK BEFORE A WRITE AND NOT A LOCK. The object store offers no compare-and-swap, so
    the window between the check and the rename is narrowed rather than closed. What it does
    guarantee is that the losing write is REPORTED — the reviewer is told to reload and re-record —
    instead of a judgement disappearing in silence.
    """


class IllegalTransitionError(EvaluationStoreError):
    """A state change is not permitted from the current state.

    Execution state and review state have separate machines and neither is ever inferred from the
    other. A job that FAILED is not REJECTED, and an APPROVED artifact did not become approved
    because its execution reached READY_FOR_REVIEW.
    """

    def __init__(self, message: str, *, current: str, requested: str) -> None:
        self.current = current
        self.requested = requested
        super().__init__(message)
