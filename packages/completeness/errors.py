"""Typed errors for the completeness ledger."""

from __future__ import annotations


class CompletenessError(Exception):
    """Base class for every failure in this package."""


class BenchmarkTruthError(CompletenessError):
    """A human judgement names a classification or an item kind that does not exist.

    Raised rather than coerced. A judgement silently downgraded to REQUIRES_REVIEW would look
    exactly like an item nobody has reviewed yet, and the reviewer would have no way to tell that
    their decision had been discarded.
    """


class LedgerInputError(CompletenessError):
    """The ledger was handed an inventory and a truth document describing different filings.

    Raised rather than reconciled. Computing coverage of one filing against another filing's
    denominator produces a number that is confidently, precisely wrong — which is the exact failure
    mode ADR-0016 was written about.
    """
