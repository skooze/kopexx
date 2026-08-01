"""Structured logging.

Log records are emitted as key-value lines rather than prose so they can be queried. The
correlation identifier is attached automatically.

SECURITY-INVARIANT: filing text and model-visible payload bodies are never logged. They may be
very large and may carry content that a prompt-injection attempt placed inside a filing. Payloads
are written to object storage and referenced by URI and hash.
"""

from __future__ import annotations

import logging
import sys
from typing import Any

from .correlation import get_correlation_id

_CONFIGURED = False

# Field names that must never appear in a log record.
REDACTED_FIELDS = frozenset(
    {
        "content",
        "payload",
        "request_body",
        "response_body",
        "text",
        "prompt",
        "api_key",
        "secret",
        "authorization_token",
        "access_token",
        "password",
    }
)


class StructuredFormatter(logging.Formatter):
    """Format records as ordered key-value pairs."""

    def format(self, record: logging.LogRecord) -> str:
        parts = [
            f"ts={self.formatTime(record, '%Y-%m-%dT%H:%M:%S%z')}",
            f"level={record.levelname}",
            f"logger={record.name}",
        ]
        correlation = get_correlation_id()
        if correlation:
            parts.append(f"correlation_id={correlation}")
        parts.append(f"msg={record.getMessage()!r}")
        extra = getattr(record, "fields", None)
        if isinstance(extra, dict):
            for key, value in extra.items():
                if key in REDACTED_FIELDS:
                    parts.append(f"{key}=<redacted>")
                else:
                    parts.append(f"{key}={value!r}")
        if record.exc_info:
            parts.append(f"exc={self.formatException(record.exc_info)!r}")
        return " ".join(parts)


def configure_logging(level: int = logging.INFO) -> None:
    """Install the structured formatter on the root logger, once."""
    global _CONFIGURED
    if _CONFIGURED:
        return
    handler = logging.StreamHandler(stream=sys.stderr)
    handler.setFormatter(StructuredFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)
    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    """Return a logger, configuring logging on first use."""
    configure_logging()
    return logging.getLogger(name)


def log_event(logger: logging.Logger, level: int, message: str, **fields: Any) -> None:
    """Emit a structured event with arbitrary fields."""
    logger.log(level, message, extra={"fields": fields})
