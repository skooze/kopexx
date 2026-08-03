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


class RecordFormatError(EvaluationStoreError):
    """A stored manifest is missing a required field or carries the wrong shape.

    Deliberately fatal rather than defaulted. A manifest that lost its model identity or its
    review state would otherwise produce a record that looks complete and is not.
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
