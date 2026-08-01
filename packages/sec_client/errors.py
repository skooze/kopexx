"""Typed SEC client errors with explicit retry classification.

SEC-INVARIANT: SEC signals throttling with HTTP 403 and an HTML body, not 429, and sends no
Retry-After header. Generic middleware that special-cases only 429 treats throttling as a
permanent client error and silently drops filings. Retry behaviour must therefore be decided by
the typed error, never by the status code alone.
"""

from __future__ import annotations


class SecClientError(Exception):
    """Base class for SEC access failures."""

    retryable: bool = False


class SecRateLimitedError(SecClientError):
    """SEC returned a rate-threshold block.

    SEC-INVARIANT: recovery requires the request rate to stay below threshold for a full ten
    minutes. Exponential backoff starting at one second keeps the client above threshold and
    extends the block indefinitely, so the only correct response is a hard cooldown.
    """

    retryable = True

    def __init__(self, reference_id: str | None = None, egress_ip: str | None = None) -> None:
        self.reference_id = reference_id
        self.egress_ip = egress_ip
        super().__init__(
            "SEC rate threshold exceeded" + (f" (reference {reference_id})" if reference_id else "")
        )


class SecUndeclaredAutomationError(SecClientError):
    """SEC rejected the request as an undeclared automated tool.

    This is a configuration defect, not a transient condition. Retrying cannot succeed and only
    generates blocked traffic, so this error is explicitly not retryable.
    """

    retryable = False

    def __init__(self, reference_id: str | None = None) -> None:
        self.reference_id = reference_id
        super().__init__(
            "SEC rejected the request as an undeclared automated tool; "
            "the configured User-Agent is missing or denylisted"
            + (f" (reference {reference_id})" if reference_id else "")
        )


class SecNotFoundError(SecClientError):
    """The requested object does not exist. Permanent."""

    retryable = False


class SecTransientError(SecClientError):
    """A transient server-side or network failure. Retryable with bounded backoff."""

    retryable = True


class DirectoryListingError(SecClientError):
    """A directory listing was returned where a filing document was expected.

    HISTORICAL-FORMAT: requesting a filing folder without a document name returns HTTP 200 and an
    index page. Storing that as filing content is a silent corruption, so it is an error.
    """

    retryable = False
