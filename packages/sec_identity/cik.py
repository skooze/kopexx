"""Central Index Key normalization.

SEC-INVARIANT: CIK formatting is inverted between SEC host families.

    data.sec.gov ............ zero-padded to ten digits, e.g. CIK0000320193
    www.sec.gov/Archives .... unpadded integer, e.g. 320193

Using the padded form against the Archives host produces a 301 redirect and a wasted
round trip against a rate limit measured in single-digit requests per second. Using the
unpadded form against data.sec.gov produces a 404.

This module is the only place in the repository permitted to implement these transforms.
"""

from __future__ import annotations

import re

from .errors import InvalidCikError

_DIGITS = re.compile(r"^\d+$")

CIK_PADDED_WIDTH = 10


def parse_cik(value: str | int) -> int:
    """Return the CIK as an integer, accepting padded, unpadded, or prefixed input.

    Accepts ``320193``, ``"320193"``, ``"0000320193"``, ``"CIK0000320193"``.
    """
    if isinstance(value, bool):  # bool is an int subclass; reject explicitly
        raise InvalidCikError(f"CIK must not be a boolean: {value!r}")
    if isinstance(value, int):
        candidate = str(value)
    else:
        candidate = value.strip()
        if candidate.upper().startswith("CIK"):
            candidate = candidate[3:]
    if not candidate or not _DIGITS.match(candidate):
        raise InvalidCikError(f"not a valid CIK: {value!r}")
    parsed = int(candidate)
    if parsed <= 0:
        raise InvalidCikError(f"CIK must be positive: {value!r}")
    if len(candidate.lstrip("0")) > CIK_PADDED_WIDTH:
        raise InvalidCikError(f"CIK exceeds {CIK_PADDED_WIDTH} significant digits: {value!r}")
    return parsed


def cik_padded(value: str | int) -> str:
    """Return the ten-digit zero-padded form used by data.sec.gov paths."""
    return f"{parse_cik(value):0{CIK_PADDED_WIDTH}d}"


def cik_archive(value: str | int) -> str:
    """Return the unpadded integer form used by www.sec.gov/Archives paths."""
    return str(parse_cik(value))


def cik_submissions_stem(value: str | int) -> str:
    """Return the submissions-API filename stem, e.g. ``CIK0000320193``."""
    return f"CIK{cik_padded(value)}"
