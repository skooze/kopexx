"""Cost-ceiling enforcement before a billable invocation, and a bounded retry budget.

rules.md section 21 rule 11: NO BILLABLE INVOCATION WITHOUT EXPLICIT AUTHORIZATION AND A COST
CEILING — cost is previewed and authorized before the call, never reconciled after it.

THE BOUND IS AN UPPER BOUND, NOT AN ESTIMATE. `authorize` is given the largest input and output
the request can possibly consume and refuses if that worst case would breach the ceiling. A mean
estimate that is right on average is wrong exactly when it matters, which is the call that goes
over.

DECIMAL THROUGHOUT. Token counts reach the millions and prices reach the sixth decimal place;
binary floating point is the wrong representation for a number that becomes a bill.
"""

from __future__ import annotations

from decimal import Decimal

from .capabilities import PriceInputs
from .errors import CostCeilingExceededError, RetryBudgetExceededError


class SpendLedger:
    """A running conservative total against a hard ceiling.

    One ledger per authorized run. Two runs never share one, because a ceiling that resets
    silently is not a ceiling.
    """

    def __init__(self, ceiling_usd: Decimal | str | int) -> None:
        ceiling = Decimal(str(ceiling_usd))
        if ceiling <= 0:
            raise ValueError("a cost ceiling must be positive; use zero invocations instead")
        self._ceiling = ceiling
        self._spent = Decimal(0)

    @property
    def ceiling_usd(self) -> Decimal:
        return self._ceiling

    @property
    def spent_usd(self) -> Decimal:
        return self._spent

    @property
    def remaining_usd(self) -> Decimal:
        return self._ceiling - self._spent

    def bound(
        self, price: PriceInputs, *, max_input_tokens: int, max_output_tokens: int
    ) -> Decimal:
        """The worst-case cost of one invocation. No side effect; safe to show a user."""
        return price.cost(max_input_tokens, max_output_tokens)

    def authorize(
        self, price: PriceInputs, *, max_input_tokens: int, max_output_tokens: int
    ) -> Decimal:
        """Reserve the worst case, or refuse.

        The reservation is charged immediately and reconciled by `settle`. Charging on success
        only would let a run of rejected-but-billable requests walk past the ceiling.
        """
        estimate = self.bound(
            price, max_input_tokens=max_input_tokens, max_output_tokens=max_output_tokens
        )
        if self._spent + estimate > self._ceiling:
            raise CostCeilingExceededError(
                "invocation refused: the conservative bound would exceed the authorized ceiling",
                ceiling_usd=str(self._ceiling),
                spent_usd=str(self._spent),
                estimate_usd=str(estimate),
            )
        self._spent += estimate
        return estimate

    def settle(
        self, price: PriceInputs, *, reserved: Decimal, input_tokens: int, output_tokens: int
    ) -> Decimal:
        """Replace a reservation with the measured cost. Returns the actual.

        A settlement may only ever reduce the total below the reservation or raise it to the
        measured value; it cannot be used to release a reservation without a measurement.
        """
        actual = price.cost(input_tokens, output_tokens)
        self._spent = self._spent - reserved + actual
        return actual


class RetryBudget:
    """A bounded number of retries, and only for reasons that justify one.

    The Phase 1 instruction allows exactly one automatic retry, and only for a clear transient
    service error, throttling, a first-use provisioning delay or a retryable network failure. A
    response whose WORDING is disliked is never a retryable reason: retrying until a model says
    what you wanted is prompt tuning with the measurement removed.
    """

    def __init__(self, max_retries: int = 1) -> None:
        if max_retries < 0:
            raise ValueError("max_retries cannot be negative")
        self._max = max_retries
        self._used = 0

    @property
    def used(self) -> int:
        return self._used

    @property
    def remaining(self) -> int:
        return self._max - self._used

    def consume(self, *, retryable: bool) -> None:
        """Record one retry, or refuse the retry with the reason it is refused."""
        if not retryable:
            raise RetryBudgetExceededError(
                "refusing to retry: the failure was not a transient service error, throttling, a "
                "provisioning delay or a retryable network failure"
            )
        if self._used >= self._max:
            raise RetryBudgetExceededError(
                f"retry budget of {self._max} exhausted; the failure is reported rather than "
                "retried again"
            )
        self._used += 1
