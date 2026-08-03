"""Generic numeric signals over model output. Arithmetic only — never meaning.

WHAT IS PERMITTED HERE, AND WHY THE LIST IS SHORT. The Phase 2 brief allows only generic, clearly
justified numeric checks: does a number the model reported appear in the source; is a table
internally coherent; is currency and percentage formatting preserved. Everything beyond that runs
into rules.md invariant 14 — backend code deciding what a number MEANS — and into D-26, where
local numeric cross-checking was deliberately deferred until a measured need appears. The DERA fact
lake that would have made a richer check possible was deleted (ADR-0017) and is not coming back
through this module.

WHAT `internally coherent` MEANS AND DOES NOT MEAN. For a column of numbers, one value equalling
the sum of the others is an ARITHMETIC OBSERVATION. This module does not conclude that the row is
a total, does not look at row labels, and does not report an incoherent table as wrong — plenty of
legitimate tables have no total row at all. The count is a comparison signal between models on the
same filing, nothing more.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

#: A number as a filing writes one: optional sign or parentheses, digits with thousands
#: separators, an optional decimal part, an optional trailing percent.
_NUMBER = re.compile(r"\(?-?\$?\d{1,3}(?:,\d{3})+(?:\.\d+)?\)?%?|\(?-?\$?\d+(?:\.\d+)?\)?%?")

#: Numbers this small are years, note numbers, item numbers and page numbers. Including them makes
#: the verbatim rate meaningless, because a bare `3` occurs in every filing ever written.
_MINIMUM_DIGITS = 4


@dataclass(frozen=True)
class NumericSignals:
    """Counts only. Every one of them is a comparison signal, not a correctness verdict."""

    numbers_checked: int
    numbers_verbatim_in_source: int
    formatted_numbers_checked: int
    formatted_numbers_preserved: int
    tables_checked: int
    tables_with_a_coherent_column: int

    @property
    def verbatim_rate(self) -> float:
        return (
            self.numbers_verbatim_in_source / self.numbers_checked if self.numbers_checked else 0.0
        )

    def to_mapping(self) -> dict[str, Any]:
        return {
            "numbers_checked": self.numbers_checked,
            "numbers_verbatim_in_source": self.numbers_verbatim_in_source,
            "verbatim_rate": round(self.verbatim_rate, 4),
            "formatted_numbers_checked": self.formatted_numbers_checked,
            "formatted_numbers_preserved": self.formatted_numbers_preserved,
            "tables_checked": self.tables_checked,
            "tables_with_a_coherent_column": self.tables_with_a_coherent_column,
            "note": (
                "arithmetic observations only. A coherent column means one value equals the sum "
                "of the others; it does not mean the table is correct, and an incoherent table is "
                "not reported as wrong."
            ),
        }


def extract_numbers(text: str) -> list[str]:
    """Numeric literals a filing would recognise, above the noise floor."""
    found = []
    for match in _NUMBER.finditer(text):
        token = match.group(0)
        digits = sum(1 for c in token if c.isdigit())
        if digits >= _MINIMUM_DIGITS:
            found.append(token)
    return found


def _bare(token: str) -> str:
    return token.strip("()%$").replace(",", "").lstrip("-")


def _numeric_cells(rows: list[Any]) -> list[list[float]]:
    """Rows reduced to their parseable numbers, keeping only rows of equal width."""
    parsed: list[list[float]] = []
    for row in rows:
        cells = row if isinstance(row, list) else [row]
        values: list[float] = []
        for cell in cells:
            tokens = extract_numbers(str(cell))
            if len(tokens) == 1:
                try:
                    values.append(float(_bare(tokens[0])))
                except ValueError:
                    continue
        if values:
            parsed.append(values)
    width = max((len(v) for v in parsed), default=0)
    return [v for v in parsed if len(v) == width and width > 0]


def _has_coherent_column(rows: list[Any]) -> bool:
    """Whether some column contains a value equal to the sum of the others in that column."""
    grid = _numeric_cells(rows)
    if len(grid) < 3:
        return False
    for column in range(len(grid[0])):
        values = [row[column] for row in grid]
        total = sum(values)
        for value in values:
            # A value equals the sum of the rest when twice it equals the whole column total.
            # Tolerance is relative: filings round to thousands and to millions.
            if value and abs(2 * value - total) <= max(abs(total) * 1e-6, 0.5):
                return True
    return False


def assess(
    *,
    reported_text: str,
    tables: list[Any],
    source_text: str,
) -> NumericSignals:
    """Numeric signals for one parsed artifact against the concatenated preserved source."""
    reported = extract_numbers(reported_text)
    # Bare-number comparison, so 1,234 in the response matches 1234 in the source and vice versa.
    # A filing and a model may legitimately write the same figure two ways, and counting that as a
    # fabrication would make the signal measure formatting rather than fidelity.
    source_bare = {_bare(token) for token in extract_numbers(source_text)}
    verbatim = sum(1 for token in reported if _bare(token) in source_bare)

    formatted = [token for token in reported if token[0] in "($" or token.endswith("%")]
    preserved = sum(1 for token in formatted if token in source_text)

    checked = 0
    coherent = 0
    for table in tables:
        rows = table.get("rows") if isinstance(table, dict) else None
        if not isinstance(rows, list) or not rows:
            continue
        checked += 1
        if _has_coherent_column(rows):
            coherent += 1

    return NumericSignals(
        numbers_checked=len(reported),
        numbers_verbatim_in_source=verbatim,
        formatted_numbers_checked=len(formatted),
        formatted_numbers_preserved=preserved,
        tables_checked=checked,
        tables_with_a_coherent_column=coherent,
    )
