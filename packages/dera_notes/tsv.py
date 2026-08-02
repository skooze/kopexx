"""Parse DERA TSV members.

SEC-INVARIANT: parse with quoting DISABLED. A double quote inside a DERA field is literal data,
not a delimiter. Python's csv module defaults to QUOTE_MINIMAL, which would swallow a quote
character and silently merge the fields on either side of it — corrupting a footnote's text with
no error raised. `csv.QUOTE_NONE` is the only correct setting here.

Values stay as strings through parsing. Numeric conversion happens once, deliberately, in
`normalize`, using Decimal. A filed financial value must never pass through binary floating point:
float("416161000000") is exact today and silently is not for other magnitudes, and there is no
warning when it stops being.
"""

from __future__ import annotations

import csv
import io
import zipfile
from collections.abc import Iterator
from datetime import date
from decimal import Decimal, InvalidOperation

from .errors import DeraError

# DERA rows are wide; the default 128 KB field limit is comfortably enough for num/pre/ren but
# txt.tsv carries whole narrative blocks and needs more.
csv.field_size_limit(64 * 1024 * 1024)

# Values DERA writes to mean "absent". An empty string is by far the most common.
NULL_TOKENS = frozenset({"", "NULL", "null", "\\N", "None"})


class TsvParseError(DeraError):
    """A row could not be parsed or a member could not be read."""


def iter_rows(archive: zipfile.ZipFile, member: str) -> Iterator[dict[str, str]]:
    """Yield each row of a member as a dict, with quoting disabled.

    STREAMS. A monthly `num.tsv` is 261 MB decompressed and `txt.tsv` is 210 MB; reading either
    with `archive.read()` costs the bytes plus a decoded copy of the same size, so a single member
    would spike half a gigabyte for data consumed one row at a time.

    Decodes with `errors="replace"`. DERA is nominally UTF-8, but occasional filings carry bytes
    that are not, and losing a whole member to one bad byte is worse than replacing that byte.
    """
    try:
        handle = archive.open(member)
    except KeyError as error:
        raise TsvParseError(f"member not found in archive: {member}") from error

    with handle:
        stream = io.TextIOWrapper(handle, encoding="utf-8", errors="replace", newline="")
        reader = csv.DictReader(stream, delimiter="\t", quoting=csv.QUOTE_NONE)
        if reader.fieldnames is None:
            raise TsvParseError(f"{member} has no header row")
        yield from reader


def count_rows(archive: zipfile.ZipFile, member: str) -> int:
    """Data rows in a member, excluding the header. Used for source-side reconciliation."""
    return sum(1 for _ in iter_rows(archive, member))


def clean(value: str | None) -> str | None:
    """Normalize a raw field to a value or None."""
    if value is None:
        return None
    stripped = value.strip()
    return None if stripped in NULL_TOKENS else stripped


def as_decimal(value: str | None) -> Decimal | None:
    """Exact numeric conversion, or None.

    FINANCIAL-INVARIANT: Decimal, never float. The filed string is preserved separately in
    `value_as_filed`, so this is the derived numeric view and the original always survives.
    """
    text = clean(value)
    if text is None:
        return None
    try:
        return Decimal(text)
    except (InvalidOperation, ValueError):
        return None


def as_int(value: str | None) -> int | None:
    text = clean(value)
    if text is None:
        return None
    try:
        return int(text)
    except ValueError:
        return None


def as_bool(value: str | None) -> bool | None:
    """DERA writes booleans as 0 or 1."""
    text = clean(value)
    if text is None:
        return None
    return text not in {"0", "false", "False"}


def as_date(value: str | None) -> date | None:
    """DERA dates are YYYYMMDD. An out-of-range value yields None rather than raising."""
    text = clean(value)
    if text is None or len(text) != 8 or not text.isdigit():
        return None
    try:
        return date(int(text[:4]), int(text[4:6]), int(text[6:8]))
    except ValueError:
        return None
