"""Correlation identifiers carried across ingestion, model calls, and API requests."""

from __future__ import annotations

import contextvars
import uuid

_CORRELATION_ID: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "fintek_correlation_id", default=None
)


def new_correlation_id() -> str:
    """Return a fresh correlation identifier."""
    return str(uuid.uuid4())


def set_correlation_id(value: str) -> contextvars.Token[str | None]:
    """Bind a correlation identifier to the current context."""
    return _CORRELATION_ID.set(value)


def get_correlation_id() -> str | None:
    """Return the correlation identifier bound to the current context."""
    return _CORRELATION_ID.get()


def reset_correlation_id(token: contextvars.Token[str | None]) -> None:
    """Restore the previous correlation identifier."""
    _CORRELATION_ID.reset(token)


class correlation_scope:
    """Context manager binding a correlation identifier for a block of work."""

    def __init__(self, value: str | None = None) -> None:
        self._value = value or new_correlation_id()
        self._token: contextvars.Token[str | None] | None = None

    def __enter__(self) -> str:
        self._token = set_correlation_id(self._value)
        return self._value

    def __exit__(self, *exc_info: object) -> None:
        if self._token is not None:
            reset_correlation_id(self._token)
