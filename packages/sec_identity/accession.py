"""Accession number normalization.

SEC-INVARIANT: the same accession appears in two forms inside one URL family.

    folder segment ..... dashes removed ... 000032019325000079
    filename ........... dashes kept ...... 0000320193-25-000079.txt

SEC-INVARIANT: the accession prefix is NOT the issuer CIK. The first ten digits identify the
filer agent that transmitted the submission. Apple's filing list contains accessions beginning
0001140361 (a filing agent). Building an Archives path from the accession prefix 404s on every
agent-transmitted document. Always take the CIK from the filing record, never from the accession.

This module is the only place in the repository permitted to implement these transforms.
"""

from __future__ import annotations

import re

from .errors import InvalidAccessionError

_DASHED = re.compile(r"^(\d{10})-(\d{2})-(\d{6})$")
_UNDASHED = re.compile(r"^(\d{10})(\d{2})(\d{6})$")

ACCESSION_DIGITS = 18


def parse_accession(value: str) -> tuple[str, str, str]:
    """Return the three accession components, accepting either dashed or undashed input."""
    if not isinstance(value, str):
        raise InvalidAccessionError(f"accession must be a string: {value!r}")
    candidate = value.strip()
    match = _DASHED.match(candidate) or _UNDASHED.match(candidate)
    if not match:
        raise InvalidAccessionError(f"not a valid accession number: {value!r}")
    return match.group(1), match.group(2), match.group(3)


def accession_dashed(value: str) -> str:
    """Return the canonical dashed form, e.g. ``0000320193-25-000079``.

    This is the identifier used by the submissions API, DERA datasets, and our own storage.
    """
    prefix, year, sequence = parse_accession(value)
    return f"{prefix}-{year}-{sequence}"


def accession_undashed(value: str) -> str:
    """Return the undashed form used only as an Archives folder segment."""
    prefix, year, sequence = parse_accession(value)
    return f"{prefix}{year}{sequence}"


def accession_filer_prefix(value: str) -> str:
    """Return the ten-digit transmitting-filer prefix.

    Exposed for provenance and reconciliation only. Never use this as the issuer CIK when
    constructing a URL; see the module docstring.
    """
    prefix, _, _ = parse_accession(value)
    return prefix


def is_valid_accession(value: str) -> bool:
    """Return True when the value parses as an accession number."""
    try:
        parse_accession(value)
    except InvalidAccessionError:
        return False
    return True
