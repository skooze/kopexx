"""Typed errors for the model catalog.

Every one of these is raised INSTEAD of quietly returning something usable. That is the whole
point of the package: rules.md section 21 rules 9 and 10 forbid silent model substitution, silent
fallback and silent truncation, and the only way code can obey that is by failing loudly when the
thing the user selected cannot be used.
"""

from __future__ import annotations


class ModelCatalogError(Exception):
    """Base class for every capability-catalog failure."""


class SnapshotFormatError(ModelCatalogError):
    """The capability snapshot is missing a required field or carries the wrong shape.

    Deliberately fatal rather than defaulted. A snapshot with a missing price or a missing region
    list would otherwise produce a catalog that looks complete and understates cost or overstates
    availability.
    """


class CapabilityContradictionError(ModelCatalogError):
    """The snapshot claims a capability its own evidence does not support.

    The case this exists for: `multimodal: true` on a record whose image invocation was never
    verified. The instruction is explicit that a model is not labelled Multimodal in the selector
    until an actual image invocation works, and a flag copied from a marketing page is exactly how
    that would happen.
    """


class UnknownModelLabelError(ModelCatalogError):
    """No candidate in the snapshot carries this user-facing label."""


class AmbiguousModelLabelError(ModelCatalogError):
    """The label does not resolve to exactly one provider model.

    A product decision, not a code decision. The catalog refuses to pick.
    """


class ModelUnavailableError(ModelCatalogError):
    """The selected model cannot be used, and the reason is carried on the exception.

    `reason` is what the UI shows in the disabled state. It is required rather than optional
    because a disabled control with no explanation is indistinguishable from a broken one.
    """

    def __init__(self, message: str, *, label: str, reason: str) -> None:
        self.label = label
        self.reason = reason
        super().__init__(message)


class CostCeilingExceededError(ModelCatalogError):
    """A billable invocation would push conservative spend past the authorized ceiling.

    rules.md section 21 rule 11: cost is previewed and authorized BEFORE the call, never
    reconciled after it.
    """

    def __init__(
        self, message: str, *, ceiling_usd: str, spent_usd: str, estimate_usd: str
    ) -> None:
        self.ceiling_usd = ceiling_usd
        self.spent_usd = spent_usd
        self.estimate_usd = estimate_usd
        super().__init__(message)


class RetryBudgetExceededError(ModelCatalogError):
    """A retryable failure recurred after the authorized number of retries."""
