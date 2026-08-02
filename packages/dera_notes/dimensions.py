"""Resolve DERA dimension hashes to the axis and member pairs they stand for.

num.tsv carries `dimh`, an opaque hash, not the dimensions themselves. dim.tsv is the lookup, and
without it every dimensional fact would be stored as if it were a consolidated one — the exact
error that makes `companyfacts` unusable for this project, reproduced locally.

The hash `0x00000000` means no dimensions. That is the consolidated series the dashboard charts,
and the partial index `ix_xbrl_fact_consolidated_series` selects on `dimensions = '{}'::jsonb`, so
mapping this hash to an empty object rather than to a placeholder is load-bearing.
"""

from __future__ import annotations

import zipfile

from .tsv import clean, iter_rows

NO_DIMENSIONS = "0x00000000"
DIM_MEMBER = "dim.tsv"


def parse_segments(segments: str | None) -> dict[str, str]:
    """Turn `Axis=Member;Axis2=Member2;` into a mapping.

    A segment without `=` is kept under its own name with an empty value rather than dropped: an
    unparseable segment is still evidence that the fact is dimensional, and silently discarding it
    would promote the fact into the consolidated series.
    """
    text = clean(segments)
    if not text:
        return {}

    parsed: dict[str, str] = {}
    for part in text.split(";"):
        piece = part.strip()
        if not piece:
            continue
        if "=" in piece:
            axis, member = piece.split("=", 1)
            parsed[axis.strip()] = member.strip()
        else:
            parsed[piece] = ""
    return parsed


class DimensionIndex:
    """dimh to segments, loaded once per package.

    dim.tsv for a monthly package holds on the order of 120,000 rows. Reading it once and holding
    the mapping costs a few tens of megabytes; querying it per fact would re-read a 16 MB member
    for every row.
    """

    def __init__(
        self,
        mapping: dict[str, dict[str, str]],
        truncated: frozenset[str],
        raw: dict[str, str] | None = None,
    ) -> None:
        self._mapping = mapping
        self._truncated = truncated
        self._raw = raw or {}

    @classmethod
    def from_archive(cls, archive: zipfile.ZipFile) -> DimensionIndex:
        mapping: dict[str, dict[str, str]] = {}
        raw: dict[str, str] = {}
        truncated: set[str] = set()
        for row in iter_rows(archive, DIM_MEMBER):
            digest = clean(row.get("dimhash"))
            if not digest:
                continue
            mapping[digest] = parse_segments(row.get("segments"))
            segments = clean(row.get("segments"))
            if segments:
                raw[digest] = segments
            # `segt` is DERA's own flag that it truncated the segment string. A truncated value is
            # still recorded, and the flag is what stops it being read as complete.
            if clean(row.get("segt")) == "1":
                truncated.add(digest)
        return cls(mapping, frozenset(truncated), raw)

    @classmethod
    def empty(cls) -> DimensionIndex:
        """For packages with no dim.tsv. Every fact then resolves to no dimensions, which is a
        loss of fidelity, so callers should prefer failing to using this silently."""
        return cls({}, frozenset())

    def resolve(self, digest: str | None) -> dict[str, str]:
        value = clean(digest)
        if not value or value == NO_DIMENSIONS:
            return {}
        return dict(self._mapping.get(value, {}))

    def raw_segments(self, digest: str | None) -> str | None:
        """DERA's own segment expression, verbatim.

        Stored beside the parsed mapping because the parse is lossy in one direction: an axis and
        member both containing `=` or `;` cannot be reconstructed from the dict, and a reviewer
        checking a surprising fact wants the string DERA actually wrote.
        """
        value = clean(digest)
        if not value or value == NO_DIMENSIONS:
            return None
        return self._raw.get(value)

    def is_truncated(self, digest: str | None) -> bool:
        value = clean(digest)
        return bool(value) and value in self._truncated

    def is_known(self, digest: str | None) -> bool:
        """False when a fact references a hash dim.tsv does not define — a package defect."""
        value = clean(digest)
        if not value or value == NO_DIMENSIONS:
            return True
        return value in self._mapping

    def __len__(self) -> int:
        return len(self._mapping)
