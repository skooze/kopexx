"""Opaque, copyable identifiers for parent runs, child jobs, comments and events.

WHAT AN IDENTIFIER MUST NOT CARRY. No account id, no CIK, no ticker, no model id, no email, no
username, no timestamp and no counter that leaks how many runs exist. A run id is quoted in a bug
report and pasted into a chat window; anything encoded in it is disclosed with it.

WHY THE STANDARD LIBRARY. `secrets.token_bytes` is a cryptographically secure source and
`base64.b32encode` is in the same standard library. Adding a dependency for identifier generation
would be a supply-chain surface bought for nothing.

WHY BASE32 AND NOT HEX OR UUID. The identifier appears in a filesystem path and in a URL, so it
must be case-insensitively safe and free of separators. Lowercase base32 of 16 random bytes is 26
characters carrying 128 bits — the same entropy as a UUID4 has in total, in a shorter string with
no hyphens to lose when a user copies it out of a terminal.
"""

from __future__ import annotations

import base64
import re
import secrets
from typing import Final

from .errors import InvalidIdentifierError

RUN_PREFIX: Final[str] = "run_"
JOB_PREFIX: Final[str] = "job_"
COMMENT_PREFIX: Final[str] = "cmt_"

# 16 random bytes encode to exactly 26 base32 characters plus padding, which is stripped.
_RANDOM_BYTES: Final[int] = 16
_BODY = r"[a-z2-7]{26}"

_RUN_ID = re.compile(rf"^{RUN_PREFIX}{_BODY}$")
_JOB_ID = re.compile(rf"^{JOB_PREFIX}{_BODY}$")
_COMMENT_ID = re.compile(rf"^{COMMENT_PREFIX}{_BODY}$")


def _mint(prefix: str) -> str:
    body = base64.b32encode(secrets.token_bytes(_RANDOM_BYTES)).decode("ascii").rstrip("=")
    return f"{prefix}{body.lower()}"


def new_run_id() -> str:
    """A fresh parent run identifier."""
    return _mint(RUN_PREFIX)


def new_job_id() -> str:
    """A fresh child filing-job identifier."""
    return _mint(JOB_PREFIX)


def new_comment_id() -> str:
    """A fresh comment identifier."""
    return _mint(COMMENT_PREFIX)


def is_run_id(value: str) -> bool:
    return bool(_RUN_ID.match(value))


def is_job_id(value: str) -> bool:
    return bool(_JOB_ID.match(value))


def is_comment_id(value: str) -> bool:
    return bool(_COMMENT_ID.match(value))


def require_run_id(value: str) -> str:
    """Return the identifier, or refuse it.

    SECURITY-INVARIANT: this runs before any identifier reaches a storage key. `..` and `/` are
    not in the permitted alphabet, so a path-traversal attempt fails here rather than relying on
    the object store's traversal guard as the only line of defence.
    """
    if not is_run_id(value):
        raise InvalidIdentifierError(
            f"{value!r} is not a run identifier issued by this store; "
            f"expected {RUN_PREFIX} followed by 26 lowercase base32 characters"
        )
    return value


def require_job_id(value: str) -> str:
    if not is_job_id(value):
        raise InvalidIdentifierError(
            f"{value!r} is not a child job identifier issued by this store; "
            f"expected {JOB_PREFIX} followed by 26 lowercase base32 characters"
        )
    return value


def require_comment_id(value: str) -> str:
    if not is_comment_id(value):
        raise InvalidIdentifierError(
            f"{value!r} is not a comment identifier issued by this store; "
            f"expected {COMMENT_PREFIX} followed by 26 lowercase base32 characters"
        )
    return value
