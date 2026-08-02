"""Parsing DERA TSV members.

The load-bearing test here is the quoting one. Everything else in this module guards a conversion;
that one guards against silently corrupting a footnote and never finding out.
"""

from __future__ import annotations

import io
import zipfile
from datetime import date
from decimal import Decimal

import pytest

from packages.dera_notes.tsv import (
    TsvParseError,
    as_bool,
    as_date,
    as_decimal,
    as_int,
    clean,
    count_rows,
    iter_rows,
)


def _archive(members: dict[str, str]) -> zipfile.ZipFile:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as writer:
        for name, body in members.items():
            writer.writestr(name, body)
    buffer.seek(0)
    return zipfile.ZipFile(buffer)


def test_a_quote_character_is_data_not_a_delimiter() -> None:
    """SEC-INVARIANT: DERA TSVs are parsed with quoting DISABLED.

    Python's csv default is QUOTE_MINIMAL. Under it, the leading double quote below opens a quoted
    field, the tab inside it stops being a delimiter, and the two columns silently merge into one.
    No exception is raised and the row count is unchanged, so the corruption is invisible.

    This test asserts the correct shape AND names the failure it prevents.
    """
    body = 'adsh\ttag\tvalue\n0000320193-25-000079\tSegment\t"Americas" segment\n'
    with _archive({"num.tsv": body}) as archive:
        rows = list(iter_rows(archive, "num.tsv"))

    assert len(rows) == 1
    assert rows[0]["tag"] == "Segment"
    assert rows[0]["value"] == '"Americas" segment'
    # The quote survives verbatim. Under QUOTE_MINIMAL it would have been stripped.
    assert rows[0]["value"].startswith('"')


def test_an_embedded_quote_does_not_swallow_the_next_column() -> None:
    """The concrete corruption: a field ending mid-quote must not absorb the following column."""
    body = 'adsh\tplabel\tnegating\nx\t5" pipe\t1\n'
    with _archive({"pre.tsv": body}) as archive:
        rows = list(iter_rows(archive, "pre.tsv"))

    assert rows[0]["plabel"] == '5" pipe'
    assert rows[0]["negating"] == "1", "the column after an embedded quote was absorbed"


def test_missing_member_raises_rather_than_yielding_nothing() -> None:
    """An empty iterator would look like an empty table, which is a silent short load."""
    with (
        _archive({"num.tsv": "adsh\n"}) as archive,
        pytest.raises(TsvParseError, match="not found"),
    ):
        list(iter_rows(archive, "txt.tsv"))


def test_member_without_a_header_raises() -> None:
    with _archive({"num.tsv": ""}) as archive, pytest.raises(TsvParseError, match="header"):
        list(iter_rows(archive, "num.tsv"))


def test_undecodable_bytes_replace_rather_than_lose_the_member() -> None:
    """DERA is nominally UTF-8 and occasionally is not. One bad byte must not cost the table."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as writer:
        writer.writestr("num.tsv", b"adsh\tvalue\nx\t\xff\xfe\n")
    buffer.seek(0)
    with zipfile.ZipFile(buffer) as archive:
        rows = list(iter_rows(archive, "num.tsv"))
    assert len(rows) == 1
    assert rows[0]["adsh"] == "x"


def test_count_rows_excludes_the_header() -> None:
    body = "adsh\tvalue\na\t1\nb\t2\nc\t3\n"
    with _archive({"num.tsv": body}) as archive:
        assert count_rows(archive, "num.tsv") == 3


@pytest.mark.parametrize("token", ["", "  ", "NULL", "null", "\\N", "None"])
def test_null_tokens_become_none(token: str) -> None:
    assert clean(token) is None


def test_clean_strips_but_preserves_content() -> None:
    assert clean("  us-gaap/2025  ") == "us-gaap/2025"


def test_decimal_conversion_is_exact() -> None:
    """FINANCIAL-INVARIANT: never float.

    float("416161000000.05") is not 416161000000.05, and nothing warns when that matters.
    """
    assert as_decimal("416161000000.0000") == Decimal("416161000000.0000")
    assert as_decimal("0.000000000000001") == Decimal("0.000000000000001")
    assert as_decimal("not a number") is None
    assert as_decimal("") is None


def test_integer_and_boolean_conversion() -> None:
    assert as_int("4") == 4
    assert as_int("-1") == -1
    assert as_int("4.5") is None
    assert as_bool("1") is True
    assert as_bool("0") is False
    assert as_bool("") is None


def test_dera_dates_are_yyyymmdd() -> None:
    assert as_date("20250930") == date(2025, 9, 30)
    assert as_date("2025-09-30") is None, "a dashed date is not DERA's format and must not parse"
    assert as_date("20250231") is None, "an impossible date yields None rather than raising"
    assert as_date("") is None
