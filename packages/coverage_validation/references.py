"""Resolve a model's source references against the PRESERVED BYTES. Nothing else counts.

WHAT A RESOLUTION IS AND IS NOT. It is a search for a verbatim quote inside the bytes SEC
published. It is not a judgement about whether the node the quote supports is correct, whether the
quote was well chosen, or what the surrounding passage means. Interpretation is the model's; proof
is the backend's, and this is the proof half.

WHY QUOTES AND NOT OFFSETS. A model handed an artifact as text cannot count bytes in it, and a
fabricated offset resolves to the wrong place while looking exactly like a real one. A quote either
occurs in the preserved bytes or it does not.

THREE SEARCHES, EACH RECORDED SEPARATELY, EACH OVER THE SAME PRESERVED BYTES.

    EXACT                 the quote appears character for character
    WHITESPACE_NORMALISED it appears once runs of whitespace are collapsed on both sides. Filings
                          wrap prose across lines with arbitrary indentation, and a model that
                          reflows a sentence it copied correctly should not be recorded as having
                          invented it
    TEXT_ONLY             it appears in the same bytes with markup tags removed. An inline-XBRL
                          filing interleaves span and ix elements inside a sentence, so a quote a
                          human would call verbatim is not contiguous in the source

    This is a SEARCH STRATEGY over preserved bytes, not a projection of the input. Nothing here
    changes what is sent to a model; roadmap.md's visible-content projection remains an unapproved
    research option and is untouched by it.

EVERY OFFSET IS AN OFFSET INTO THE ORIGINAL TEXT, IN ONE COORDINATE SYSTEM.

    This is a correction, and the defect it fixes was invisible. Two of the three searches run over
    a TRANSFORMED copy of the artifact — whitespace collapsed, or markup removed — and returning
    the position found in that copy meant the review UI highlighted a range in the original text
    using coordinates measured in a different string. The highlight landed somewhere plausible and
    wrong, and it got further wrong the more markup a filing carried, which is exactly the filings
    where a reviewer most needs it.

    Each transform therefore carries an index map built in the same pass: `map[i]` is the offset in
    the ORIGINAL text of the character that produced position `i` of the transform. A resolution
    reports the original offset and the original LENGTH of the matched span, so the caller
    highlights the bytes that actually matched rather than the length of the quote it asked about.

AMBIGUOUS IS ITS OWN OUTCOME. A quote occurring many times locates nothing in particular. Counting
it as resolved would inflate the citation rate with references that point everywhere at once.
"""

from __future__ import annotations

import re
from array import array
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

#: Beyond this many occurrences a quote locates nothing in particular. Short quotes such as a bare
#: year or a single word hit this immediately, which is the correct answer for them.
AMBIGUITY_THRESHOLD: int = 8

_TAG = re.compile(r"<[^>]{0,4096}>")
_WHITESPACE_CHARS = frozenset(" \t\r\n\f\v")


class Resolution(StrEnum):
    """How a source reference resolved against the preserved bytes."""

    EXACT = "EXACT"
    WHITESPACE_NORMALISED = "WHITESPACE_NORMALISED"
    TEXT_ONLY = "TEXT_ONLY"
    AMBIGUOUS = "AMBIGUOUS"
    UNRESOLVED = "UNRESOLVED"
    NO_SUCH_ARTIFACT = "NO_SUCH_ARTIFACT"
    EMPTY_QUOTE = "EMPTY_QUOTE"


#: Outcomes that count as the reference having been located.
RESOLVED = frozenset({Resolution.EXACT, Resolution.WHITESPACE_NORMALISED, Resolution.TEXT_ONLY})


@dataclass(frozen=True)
class ReferenceOutcome:
    """One reference, its verdict, and where in the ORIGINAL text it landed."""

    filename: str
    quote: str
    resolution: Resolution
    occurrences: int
    offset: int | None
    node_id: str
    match_length: int = 0

    @property
    def resolved(self) -> bool:
        return self.resolution in RESOLVED

    def to_mapping(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "filename": self.filename,
            # Truncated for the manifest only. The full quote is in the exact response, which is
            # preserved beside this record and is authoritative.
            "quote": self.quote[:200],
            "resolution": self.resolution.value,
            "occurrences": self.occurrences,
            "offset": self.offset,
            "match_length": self.match_length,
            "offset_coordinate_system": "characters into the preserved artifact as sent",
        }


def _normalise_whitespace(text: str) -> tuple[str, array[int]]:
    """Collapse whitespace runs to one space, keeping an index back into the original.

    Written as an explicit pass rather than a regex substitution because the index map has to be
    built alongside the output. A regex gives the transformed string and throws away the only thing
    that could locate a match in the source it came from.
    """
    out: list[str] = []
    index: array[int] = array("i")
    in_run = False
    for position, char in enumerate(text):
        if char in _WHITESPACE_CHARS:
            if not in_run:
                out.append(" ")
                index.append(position)
                in_run = True
            continue
        in_run = False
        out.append(char)
        index.append(position)
    return "".join(out), index


def _strip_markup(text: str) -> tuple[str, array[int]]:
    """Replace every markup tag with one space, keeping an index back into the original."""
    out: list[str] = []
    index: array[int] = array("i")
    cursor = 0
    for match in _TAG.finditer(text):
        for position in range(cursor, match.start()):
            out.append(text[position])
            index.append(position)
        out.append(" ")
        index.append(match.start())
        cursor = match.end()
    for position in range(cursor, len(text)):
        out.append(text[position])
        index.append(position)
    collapsed, collapsed_index = _normalise_whitespace("".join(out))
    # Compose the two maps so the result still points into the ORIGINAL text.
    composed: array[int] = array("i", (index[i] for i in collapsed_index))
    return collapsed, composed


@dataclass(frozen=True)
class _Searchable:
    """One search space: the text to look in, and how to map a hit back to the original."""

    resolution: Resolution
    text: str
    index: array[int] | None

    def original_span(self, start: int, length: int) -> tuple[int, int]:
        """Translate a hit in this search space into an offset and length in the original."""
        if self.index is None:
            return start, length
        if start >= len(self.index):
            return self.index[-1] if len(self.index) else 0, 0
        origin = self.index[start]
        last = min(start + length - 1, len(self.index) - 1)
        return origin, max(1, self.index[last] - origin + 1)


class ArtifactIndex:
    """The preserved text of each submitted artifact, prepared once for repeated searching.

    Built once per validation rather than per reference: a filing with 300 references would
    otherwise strip tags from a 4 MB document 300 times.
    """

    def __init__(self, texts: dict[str, str]) -> None:
        self._raw = texts
        self._spaces: dict[str, tuple[_Searchable, _Searchable, _Searchable]] = {}
        for name, text in texts.items():
            normalised, normalised_index = _normalise_whitespace(text)
            stripped, stripped_index = _strip_markup(text)
            self._spaces[name] = (
                _Searchable(Resolution.EXACT, text, None),
                _Searchable(Resolution.WHITESPACE_NORMALISED, normalised, normalised_index),
                _Searchable(Resolution.TEXT_ONLY, stripped, stripped_index),
            )

    @property
    def filenames(self) -> tuple[str, ...]:
        return tuple(self._raw)

    def _candidates(self, filename: str) -> list[str]:
        """Which artifacts to search, in order.

        A named artifact is searched first. A reference naming NO artifact, or naming one that was
        never submitted, still gets searched across everything — a model that cited the right
        sentence and the wrong filename made a labelling error, not a fabrication, and the two
        deserve different verdicts.
        """
        ordered = []
        if filename in self._raw:
            ordered.append(filename)
        ordered.extend(name for name in self._raw if name != filename)
        return ordered

    def resolve(self, filename: str, quote: str, *, node_id: str) -> ReferenceOutcome:
        """Locate one quote, recording which search found it and where in the ORIGINAL it sits."""
        cleaned = quote.strip()
        if not cleaned:
            return ReferenceOutcome(filename, quote, Resolution.EMPTY_QUOTE, 0, None, node_id)
        if not self._raw:
            return ReferenceOutcome(filename, quote, Resolution.NO_SUCH_ARTIFACT, 0, None, node_id)

        normalised_quote, _ = _normalise_whitespace(cleaned)
        normalised_quote = normalised_quote.strip()
        for name in self._candidates(filename):
            exact, normalised, stripped = self._spaces[name]
            for space, needle in (
                (exact, cleaned),
                (normalised, normalised_quote),
                (stripped, normalised_quote),
            ):
                if not needle:
                    continue
                count = space.text.count(needle)
                if count == 0:
                    continue
                if count > AMBIGUITY_THRESHOLD:
                    return ReferenceOutcome(name, quote, Resolution.AMBIGUOUS, count, None, node_id)
                offset, length = space.original_span(space.text.find(needle), len(needle))
                return ReferenceOutcome(
                    name, quote, space.resolution, count, offset, node_id, match_length=length
                )
        return ReferenceOutcome(filename, quote, Resolution.UNRESOLVED, 0, None, node_id)
