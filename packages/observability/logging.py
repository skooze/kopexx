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

# Field names whose VALUE is never emitted. Redaction is centralized so a new logger cannot
# forget it, and so adding a credential-bearing name protects every call site at once.
#
# The AWS group is present before any AWS integration exists, deliberately: a credential that
# reaches a log has already been disclosed, and the log is the one place nobody thinks to check.
# rules.md section 3, AWS-IDENTITY-AND-SECRETS-INVARIANT.
REDACTED_FIELDS = frozenset(
    {
        # model and request content
        "content",
        "payload",
        "request_body",
        "response_body",
        "text",
        "prompt",
        # generic secret material
        "api_key",
        "secret",
        "secret_value",
        "credentials",
        "authorization",
        "authorization_token",
        "access_token",
        "password",
        # AWS identity. Kopexx holds none of these; if one ever appears in a log record, the
        # value is suppressed and the field name itself is the signal that something is wrong.
        "aws_access_key_id",
        "aws_secret_access_key",
        "aws_session_token",
        "access_key_id",
        "secret_access_key",
        "session_token",
        "x_amz_security_token",
        "x_amz_credential",
        "security_token",
        # signed URLs and cookies carry the credential in the signature
        "signature",
        "x_amz_signature",
        "signed_cookie",
        "presigned_url",
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
