"""SEC User-Agent validation.

SEC's access policy requires a declared identity with a contact address on every request.
Requests carrying a library default User-Agent are refused with HTTP 403.
"""

from __future__ import annotations

import re
from typing import Final

from .errors import InvalidUserAgentError

_EMAIL = re.compile(r"[^@\s]+@[^@\s]+\.[A-Za-z]{2,}")

# Substrings that identify a library default or an obviously undeclared client. Matching is
# case-insensitive against the whole User-Agent string.
DENYLIST_FRAGMENTS: Final[tuple[str, ...]] = (
    "python-requests",
    "python-urllib",
    "urllib3",
    "httpx/",
    "aiohttp",
    "curl/",
    "wget/",
    "go-http-client",
    "java/",
    "okhttp",
    "scrapy",
    "libwww-perl",
    "postman",
    "insomnia",
    "node-fetch",
    "axios/",
)

MIN_LENGTH: Final[int] = 10


def validate_user_agent(user_agent: str | None) -> str:
    """Return the User-Agent when it satisfies SEC policy, otherwise raise.

    A valid User-Agent identifies the application and carries a contact email address, for
    example: ``FinTek Research contact@example.com``.
    """
    if user_agent is None or not user_agent.strip():
        raise InvalidUserAgentError(
            "SEC_USER_AGENT is not set. SEC requires a declared identity with a contact "
            "address on every request, for example: 'FinTek Research you@example.com'"
        )
    candidate = user_agent.strip()
    if len(candidate) < MIN_LENGTH:
        raise InvalidUserAgentError(
            f"SEC_USER_AGENT is too short to identify this application: {candidate!r}"
        )
    lowered = candidate.lower()
    for fragment in DENYLIST_FRAGMENTS:
        if fragment in lowered:
            raise InvalidUserAgentError(
                f"SEC_USER_AGENT {candidate!r} contains the library-default fragment "
                f"{fragment!r}. SEC denylists these and answers with HTTP 403."
            )
    if not _EMAIL.search(candidate):
        raise InvalidUserAgentError(
            f"SEC_USER_AGENT {candidate!r} does not contain a contact email address, "
            "which SEC access policy requires."
        )
    return candidate


def is_valid_user_agent(user_agent: str | None) -> bool:
    """Return True when the User-Agent satisfies SEC policy."""
    try:
        validate_user_agent(user_agent)
    except InvalidUserAgentError:
        return False
    return True
