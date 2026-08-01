"""Classification of SEC responses that look like failures.

SEC returns HTTP 403 for two entirely different conditions that require opposite responses:

    Request Rate Threshold Exceeded ......... wait 600 seconds, then resume
    Undeclared Automated Tool ............... fix configuration, do not retry

They are indistinguishable by status code. Classification is by response body.
"""

from __future__ import annotations

import re
from enum import StrEnum

from .errors import (
    SecClientError,
    SecRateLimitedError,
    SecUndeclaredAutomationError,
)

_RATE_MARKERS = (
    "request rate threshold exceeded",
    "exceeded the sec's traffic limit",
    "your request rate has exceeded",
)
_AUTOMATION_MARKERS = (
    "undeclared automated tool",
    "declare your traffic",
    "please declare your user-agent",
)
_REFERENCE = re.compile(r"reference\s*id\s*[:=]?\s*([0-9a-fA-F.\-]+)", re.IGNORECASE)
_DIRECTORY_MARKERS = (
    "<title>index of",
    "directory listing for",
)


class ThrottleKind(StrEnum):
    """What a 403 body actually means."""

    RATE_LIMITED = "rate_limited"
    UNDECLARED_AUTOMATION = "undeclared_automation"
    UNKNOWN = "unknown"


def extract_reference_id(body: str) -> str | None:
    """Return the SEC reference identifier from a block page, when present.

    SEC asks for this identifier plus the egress address when reporting access problems, so it is
    recorded on every block rather than discarded.
    """
    if not body:
        return None
    match = _REFERENCE.search(body)
    return match.group(1) if match else None


def classify_403(body: str) -> ThrottleKind:
    """Classify a 403 response body."""
    if not body:
        return ThrottleKind.UNKNOWN
    lowered = body.lower()
    for marker in _AUTOMATION_MARKERS:
        if marker in lowered:
            return ThrottleKind.UNDECLARED_AUTOMATION
    for marker in _RATE_MARKERS:
        if marker in lowered:
            return ThrottleKind.RATE_LIMITED
    return ThrottleKind.UNKNOWN


def raise_for_403(body: str, *, egress_ip: str | None = None) -> SecClientError:
    """Return the typed error corresponding to a 403 body.

    Returns rather than raises so the caller controls the traceback origin.
    """
    reference = extract_reference_id(body)
    kind = classify_403(body)
    if kind is ThrottleKind.UNDECLARED_AUTOMATION:
        return SecUndeclaredAutomationError(reference_id=reference)
    if kind is ThrottleKind.RATE_LIMITED:
        return SecRateLimitedError(reference_id=reference, egress_ip=egress_ip)
    # An unrecognized 403 is treated as a rate block: pausing is safe, hammering is not.
    return SecRateLimitedError(reference_id=reference, egress_ip=egress_ip)


def looks_like_directory_listing(body: str, content_type: str = "") -> bool:
    """Return True when a response body is an Archives directory index rather than a document."""
    if not body:
        return False
    lowered = body[:4096].lower()
    if any(marker in lowered for marker in _DIRECTORY_MARKERS):
        return True
    # SEC folder indexes are HTML tables of filenames with a parent-directory link.
    return "text/html" in content_type.lower() and "parent directory" in lowered
