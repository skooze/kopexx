"""Resolve a model's anchors against the PRESERVED BYTES. Nothing else counts.

WHAT A RESOLUTION IS AND IS NOT. It is a search for a verbatim quote inside the bytes SEC
published. It is not a judgement about whether the node the quote supports is correct, whether the
quote was well chosen, or what the surrounding passage means. Interpretation is the model's; proof
is the backend's, and this is the proof half.

WHY QUOTES AND NOT OFFSETS. A model handed an artifact as text cannot count bytes in it, and a
fabricated offset resolves to the wrong place while looking exactly like a real one. A quote either
occurs in the preserved bytes or it does not.

SIX LEVELS, IN ORDER, EACH RECORDED SEPARATELY. Phase 2.1 ran three. The four extra levels exist
because that phase's twelve unresolved GPT OSS references were all, on inspection, small
transcription defects over content demonstrably present in the parse: a capitalised first letter, a
non-breaking hyphen, a dropped space, an inserted word. Three of those four classes now have a
level, and the fourth is a candidate rather than a verdict.

    1  EXACT                  character for character
    2  UNICODE_NORMALISED     NFKC per character. Folds a non-breaking space to a space, a
                              full-width digit to an ASCII digit, and a `fi` ligature to two
                              letters. It is applied PER CHARACTER so that every output character
                              maps back to exactly one input position; whole-string NFKC would
                              compose a base letter and a following combining accent into one
                              character and lose that correspondence. SEC filings do not use
                              decomposed accents, and the limitation is recorded rather than
                              papered over.
    3  WHITESPACE_NORMALISED  runs of whitespace collapsed to one space. Filings wrap prose across
                              lines with arbitrary indentation, and a model that reflows a sentence
                              it copied correctly should not be recorded as having invented it.
    4  HYPHEN_NORMALISED      every Unicode dash and minus sign to ASCII hyphen-minus, soft hyphens
                              removed, and — in the same pass and for the same reason — curly
                              quotes folded to straight ones. A model that retypes an en dash
                              retypes a curly apostrophe in the same breath, and splitting the two
                              into separate levels would add a level that changes no verdict.
    5  CASE_INSENSITIVE       a HUMAN-REVIEW CANDIDATE, not a resolution. A filing that writes a
                              heading in capitals and a model that writes it in title case are
                              probably talking about the same passage, and "probably" is a person's
                              call.
    6  APPROXIMATE            a HUMAN-REVIEW CANDIDATE. The head and tail of the quote both occur,
                              in order, close enough together to be the same passage. It locates
                              something a reviewer can look at; it proves nothing.

    LEVELS 1 THROUGH 4 COUNT AS MECHANICALLY RESOLVED. LEVELS 5 AND 6 DO NOT, EVER, BY DEFAULT.
    Counting a case-folded near-match as proof is how a citation rate starts flattering the model
    that produced it.

TWO SEARCH SPACES, ONE COORDINATE SYSTEM. Every level is tried over the preserved text as sent and
over the same bytes with markup tags replaced by a space. The second is not a projection of the
INPUT — nothing here changes what a model receives, and visible-content projection remains an
unapproved research option under rules.md section 21 rule 7. It exists because an inline-XBRL filing
interleaves `span` and `ix` elements inside a single sentence, so a quote a human would call
verbatim is not contiguous in the source. A hit found only in that space is reported as `TEXT_ONLY`,
which is what Phase 2 already called it.

EVERY OFFSET IS AN OFFSET INTO THE ORIGINAL TEXT. Each transform carries an index map built in the
same pass: `map[i]` is the offset in the ORIGINAL text of the character that produced position `i`
of the transform. A resolution reports the original offset and the original LENGTH of the matched
span, so the caller highlights the bytes that actually matched rather than the length of the quote
it asked about. Without that, a highlight lands somewhere plausible and wrong, and it gets further
wrong the more markup a filing carries — which is exactly the filings where a reviewer most needs it.

AMBIGUOUS IS ITS OWN OUTCOME. A quote occurring many times locates nothing in particular. Counting
it as resolved would inflate the citation rate with references that point everywhere at once.
"""

from __future__ import annotations

import re
import unicodedata
from array import array
from dataclasses import dataclass
from enum import StrEnum
from html import unescape
from typing import Any, Final

#: Beyond this many occurrences a quote locates nothing in particular. Short quotes such as a bare
#: year or a single word hit this immediately, which is the correct answer for them.
AMBIGUITY_THRESHOLD: int = 8

#: How many characters of each end an APPROXIMATE candidate matches on. Short enough that a retyped
#: middle does not defeat it, long enough that two unrelated passages do not both qualify.
APPROXIMATE_EDGE: Final[int] = 40

#: How much longer than the quote the located region may be before it stops being the same passage.
APPROXIMATE_SLACK: Final[float] = 3.0

_TAG = re.compile(r"<[^>]{0,4096}>")
_ENTITY = re.compile(r"&(?:#\d{1,7}|#[xX][0-9a-fA-F]{1,6}|[a-zA-Z][a-zA-Z0-9]{1,31});")
_WHITESPACE_CHARS = frozenset(" \t\r\n\f\v   ")

#: Dashes, minus signs and quotes a filing renders typographically and a model retypes as ASCII.
_TYPOGRAPHIC: Final[dict[str, str]] = {
    "‐": "-", "‑": "-", "‒": "-", "–": "-", "—": "-", "―": "-",
    "−": "-", "﹘": "-", "﹣": "-", "－": "-",
    "‘": "'", "’": "'", "‚": "'", "‛": "'", "′": "'",
    "“": '"', "”": '"', "„": '"', "‟": '"', "″": '"',
}  # fmt: skip

#: Removed entirely rather than folded: a soft hyphen is an invisible line-break opportunity, and a
#: zero-width joiner is not a character anybody retypes.
_DISCARDED: Final[frozenset[str]] = frozenset("­​‌‍﻿")


class Resolution(StrEnum):
    """How an anchor resolved against the preserved bytes.

    THE FOUR ADDED IN PHASE 2.2 ARE ADDITIONS, NOT REPLACEMENTS. Every value Phase 2 and Phase 2.1
    recorded still means exactly what it meant, so preserved evidence stays readable and a
    re-derivation of an old run cannot silently change its counts.
    """

    EXACT = "EXACT"
    UNICODE_NORMALISED = "UNICODE_NORMALISED"
    WHITESPACE_NORMALISED = "WHITESPACE_NORMALISED"
    HYPHEN_NORMALISED = "HYPHEN_NORMALISED"
    TEXT_ONLY = "TEXT_ONLY"
    CASE_INSENSITIVE = "CASE_INSENSITIVE"
    APPROXIMATE = "APPROXIMATE"
    AMBIGUOUS = "AMBIGUOUS"
    UNRESOLVED = "UNRESOLVED"
    NO_SUCH_ARTIFACT = "NO_SUCH_ARTIFACT"
    EMPTY_QUOTE = "EMPTY_QUOTE"


#: Outcomes that count as the anchor having been LOCATED in the preserved bytes.
RESOLVED = frozenset(
    {
        Resolution.EXACT,
        Resolution.UNICODE_NORMALISED,
        Resolution.WHITESPACE_NORMALISED,
        Resolution.HYPHEN_NORMALISED,
        Resolution.TEXT_ONLY,
    }
)

#: Outcomes that locate something a PERSON should look at and that no count may treat as proof.
HUMAN_REVIEW_CANDIDATE = frozenset({Resolution.CASE_INSENSITIVE, Resolution.APPROXIMATE})


@dataclass(frozen=True)
class ReferenceOutcome:
    """One anchor, its verdict, and where in the ORIGINAL text it landed."""

    filename: str
    quote: str
    resolution: Resolution
    occurrences: int
    offset: int | None
    node_id: str
    match_length: int = 0
    #: Which rung of the ladder found it, 1 through 6, or 0 when nothing did. Reported ALONGSIDE
    #: `resolution` rather than instead of it: `TEXT_ONLY` is one value covering four levels, and a
    #: report that cannot distinguish an exact hit in rendered prose from a hyphen-folded one has
    #: thrown away the measurement this phase exists to make.
    level: int = 0
    #: Whether the hit came from the rendered-text space rather than the bytes as filed.
    markup_stripped: bool = False

    @property
    def resolved(self) -> bool:
        return self.resolution in RESOLVED

    @property
    def review_candidate(self) -> bool:
        return self.resolution in HUMAN_REVIEW_CANDIDATE

    @property
    def located(self) -> bool:
        """Whether an offset exists at all — true for a candidate as well as a resolution."""
        return self.offset is not None

    def to_mapping(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "filename": self.filename,
            # Truncated for the manifest only. The full quote is in the exact response, which is
            # preserved beside this record and is authoritative.
            "quote": self.quote[:200],
            "resolution": self.resolution.value,
            "resolved": self.resolved,
            "human_review_candidate": self.review_candidate,
            "level": self.level,
            "markup_stripped": self.markup_stripped,
            "occurrences": self.occurrences,
            "offset": self.offset,
            "match_length": self.match_length,
            "offset_coordinate_system": "characters into the preserved artifact as sent",
        }


# --- transforms, each carrying an index map back into the ORIGINAL text -------------------------
#
# EVERY TRANSFORM RETURNS `None` FOR ITS INDEX WHEN IT CHANGED NOTHING, and that is a performance
# decision with a correctness consequence, so it is stated rather than left to be discovered.
#
#     An index map is one Python integer per output character. Building all four levels over both
#     search spaces of a 732 KB inline-XBRL document eagerly is roughly ten million interpreter
#     iterations per artifact, six artifacts to a filing, on every validation. Most of those
#     transforms are no-ops: SEC markup is overwhelmingly ASCII, so the Unicode fold and the
#     typographic fold usually change not one character.
#
#     `None` therefore means "this level's text IS the previous level's text", the composition
#     skips it, and `_Space.original_span` falls through to the identity it already handled. The
#     correctness consequence is that a caller may never assume an index exists.


def _unicode_fold(text: str) -> tuple[str, array[int] | None]:
    # `is_normalized` is a fast C-level check that answers "would this do anything at all".
    if unicodedata.is_normalized("NFKC", text):
        return text, None
    out: list[str] = []
    index: array[int] = array("i")
    for position, char in enumerate(text):
        for produced in unicodedata.normalize("NFKC", char):
            out.append(produced)
            index.append(position)
    return "".join(out), index


def _collapse_whitespace(text: str) -> tuple[str, array[int] | None]:
    out: list[str] = []
    index: array[int] = array("i")
    in_run = False
    changed = False
    for position, char in enumerate(text):
        if char in _WHITESPACE_CHARS:
            if in_run:
                changed = True
                continue
            if char != " ":
                changed = True
            out.append(" ")
            index.append(position)
            in_run = True
            continue
        in_run = False
        out.append(char)
        index.append(position)
    return (text, None) if not changed else ("".join(out), index)


def _fold_typographic(text: str) -> tuple[str, array[int] | None]:
    if not any(char in _TYPOGRAPHIC or char in _DISCARDED for char in text):
        return text, None
    out: list[str] = []
    index: array[int] = array("i")
    for position, char in enumerate(text):
        if char in _DISCARDED:
            continue
        out.append(_TYPOGRAPHIC.get(char, char))
        index.append(position)
    return "".join(out), index


def _casefold(text: str) -> tuple[str, array[int] | None]:
    if text == text.casefold():
        return text, None
    out: list[str] = []
    index: array[int] = array("i")
    for position, char in enumerate(text):
        for produced in char.casefold():
            out.append(produced)
            index.append(position)
    return "".join(out), index


def _strip_markup(text: str) -> tuple[str, array[int] | None]:
    """Replace every markup tag with one space, keeping an index back into the original."""
    if "<" not in text:
        return text, None
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
    return "".join(out), index


def _decode_entities(text: str) -> tuple[str, array[int] | None]:
    """Resolve character and entity references to the characters they stand for.

    MEASURED, AND IT IS NOT A DETAIL. Apple's 10-Q primary document for accession
    0000320193-25-000008 contains 970 character references and NOT ONE literal non-ASCII character:
    655 `&#160;`, 116 `&#8217;`, 53 `&#8212;`, 51 each of `&#8220;` and `&#8221;`. Every
    non-breaking space, apostrophe, em dash and quotation mark in the filing is an escape.

    A model reading those bytes and quoting a sentence back writes the CHARACTER, not the escape.
    Without this transform, every quote containing an apostrophe fails to resolve, and the failure
    looks exactly like a fabricated citation. Phase 2.1 saw the same class of defect as "a
    non-breaking hyphen" among GPT OSS's twelve unresolved references.

    IT LIVES ONLY IN THE MARKUP-STRIPPED SPACE, ON PURPOSE. That space means "these bytes as
    rendered", and rendering resolves an escape. The raw space stays byte-faithful so that `EXACT`
    keeps meaning exact.
    """
    if "&" not in text:
        return text, None
    out: list[str] = []
    index: array[int] = array("i")
    cursor = 0
    for match in _ENTITY.finditer(text):
        for position in range(cursor, match.start()):
            out.append(text[position])
            index.append(position)
        for produced in unescape(match.group(0)):
            out.append(produced)
            index.append(match.start())
        cursor = match.end()
    for position in range(cursor, len(text)):
        out.append(text[position])
        index.append(position)
    return "".join(out), index


def _compose(first: array[int] | None, second: array[int] | None) -> array[int] | None:
    """Chain two index maps so the result still points into the ORIGINAL text."""
    if second is None:
        return first
    if first is None:
        return second
    return array("i", (first[i] for i in second))


@dataclass(frozen=True)
class _Space:
    """One search space: text to look in, how to map a hit back, and what to call a hit."""

    resolution: Resolution
    text: str
    index: array[int] | None

    def original_span(self, start: int, length: int) -> tuple[int, int]:
        if self.index is None:
            return start, length
        if start >= len(self.index):
            return (self.index[-1] if len(self.index) else 0), 0
        origin = self.index[start]
        last = min(start + length - 1, len(self.index) - 1)
        return origin, max(1, self.index[last] - origin + 1)


#: The four mechanically-resolving levels, deepest last. Level 5 and level 6 are handled separately
#: because they produce a candidate rather than a resolution, and mixing them into this list is how
#: a candidate ends up counted as proof.
_LEVELS: Final[tuple[Resolution, ...]] = (
    Resolution.EXACT,
    Resolution.UNICODE_NORMALISED,
    Resolution.WHITESPACE_NORMALISED,
    Resolution.HYPHEN_NORMALISED,
)


class _Ladder:
    """The cumulative transform chain over one base text, built ONE LEVEL AT A TIME.

    Levels are built on demand and cached. Most anchors resolve at level 1 to 3, so the deeper
    levels of most artifacts are never built at all — which is the difference between a validation
    that takes a second and one that takes a minute on a filing this size.

    A hit in the markup-stripped base is reported as TEXT_ONLY at every level, because that is the
    fact a reviewer needs: the quote is in the rendered prose and not in the source as written.
    """

    def __init__(self, text: str, *, markup_stripped: bool) -> None:
        self._markup_stripped = markup_stripped
        if markup_stripped:
            # Two transforms make the base, because "as rendered" means both: tags become spacing
            # and escapes become the characters they stand for.
            stripped, stripped_index = _strip_markup(text)
            decoded, decoded_index = _decode_entities(stripped)
            base, index = decoded, _compose(stripped_index, decoded_index)
        else:
            base, index = text, None
        self._built: list[_Space] = [
            _Space(Resolution.TEXT_ONLY if markup_stripped else Resolution.EXACT, base, index)
        ]
        self._casefolded: _Space | None = None

    def space(self, level: int) -> _Space:
        """Level `level` of the ladder, zero-indexed, building whatever is not built yet."""
        while len(self._built) <= level:
            previous = self._built[-1]
            transform = (_unicode_fold, _collapse_whitespace, _fold_typographic)[
                len(self._built) - 1
            ]
            text, index = transform(previous.text)
            self._built.append(
                _Space(
                    Resolution.TEXT_ONLY if self._markup_stripped else _LEVELS[len(self._built)],
                    text,
                    _compose(previous.index, index),
                )
            )
        return self._built[level]

    def casefolded(self) -> _Space:
        """The deepest level, case-folded. Level 5, and the base level 6 searches."""
        if self._casefolded is None:
            deepest = self.space(len(_LEVELS) - 1)
            text, index = _casefold(deepest.text)
            self._casefolded = _Space(
                Resolution.CASE_INSENSITIVE, text, _compose(deepest.index, index)
            )
        return self._casefolded


def _needles(quote: str) -> tuple[str, str, str, str]:
    """The quote at each level of the ladder, so a search compares like with like."""
    folded, _ = _unicode_fold(quote)
    collapsed, _ = _collapse_whitespace(folded)
    typographic, _ = _fold_typographic(collapsed)
    return quote, folded.strip(), collapsed.strip(), typographic.strip()


class ArtifactIndex:
    """The preserved text of each submitted artifact, prepared for repeated searching.

    Prepared once per validation rather than once per anchor: a filing with 300 anchors would
    otherwise strip tags from a 732 KB document 300 times, at every level of the ladder.
    """

    def __init__(self, texts: dict[str, str]) -> None:
        self._raw = texts
        self._ladders: dict[str, tuple[_Ladder, _Ladder]] = {
            name: (_Ladder(text, markup_stripped=False), _Ladder(text, markup_stripped=True))
            for name, text in texts.items()
        }

    @property
    def filenames(self) -> tuple[str, ...]:
        return tuple(self._raw)

    def text_for(self, filename: str) -> str:
        return self._raw.get(filename, "")

    def _candidate_order(self, filename: str) -> list[str]:
        """Which artifacts to search, in order.

        A named artifact is searched first. An anchor naming NO artifact, or naming one that was
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
        """Locate one anchor, recording which level found it and where in the ORIGINAL it sits."""
        cleaned = quote.strip()
        if not cleaned:
            return ReferenceOutcome(filename, quote, Resolution.EMPTY_QUOTE, 0, None, node_id)
        if not self._raw:
            return ReferenceOutcome(filename, quote, Resolution.NO_SUCH_ARTIFACT, 0, None, node_id)

        needles = _needles(cleaned)
        ambiguous: ReferenceOutcome | None = None

        # LEVEL ORDER BEATS ARTIFACT ORDER, DELIBERATELY. An exact hit in the wrong-named artifact
        # is better evidence than a hyphen-folded hit in the right-named one, and searching every
        # level of one artifact before touching the next would report the weaker of the two.
        for level in range(len(_LEVELS)):
            needle = needles[level]
            if not needle:
                continue
            for name in self._candidate_order(filename):
                for stripped, ladder in enumerate(self._ladders[name]):
                    space = ladder.space(level)
                    found = space.text.find(needle)
                    if found < 0:
                        continue
                    count = space.text.count(needle)
                    if count > AMBIGUITY_THRESHOLD:
                        if ambiguous is None:
                            ambiguous = ReferenceOutcome(
                                name, quote, Resolution.AMBIGUOUS, count, None, node_id
                            )
                        continue
                    offset, length = space.original_span(found, len(needle))
                    return ReferenceOutcome(
                        name,
                        quote,
                        space.resolution,
                        count,
                        offset,
                        node_id,
                        match_length=length,
                        level=level + 1,
                        markup_stripped=bool(stripped),
                    )

        if ambiguous is not None:
            return ambiguous

        # Level 5, then level 6. Both produce a CANDIDATE, never a resolution.
        lowered = needles[3].casefold()
        if not lowered:
            return ReferenceOutcome(filename, quote, Resolution.UNRESOLVED, 0, None, node_id)

        for name in self._candidate_order(filename):
            for stripped, ladder in enumerate(self._ladders[name]):
                space = ladder.casefolded()
                found = space.text.find(lowered)
                if found < 0:
                    continue
                offset, length = space.original_span(found, len(lowered))
                return ReferenceOutcome(
                    name,
                    quote,
                    Resolution.CASE_INSENSITIVE,
                    space.text.count(lowered),
                    offset,
                    node_id,
                    match_length=length,
                    level=5,
                    markup_stripped=bool(stripped),
                )

        for name in self._candidate_order(filename):
            for stripped, ladder in enumerate(self._ladders[name]):
                approximate = _approximate(ladder.casefolded(), lowered)
                if approximate is not None:
                    offset, length = approximate
                    return ReferenceOutcome(
                        name,
                        quote,
                        Resolution.APPROXIMATE,
                        1,
                        offset,
                        node_id,
                        match_length=length,
                        level=6,
                        markup_stripped=bool(stripped),
                    )

        return ReferenceOutcome(filename, quote, Resolution.UNRESOLVED, 0, None, node_id)


def _approximate(space: _Space, needle: str) -> tuple[int, int] | None:
    """Locate a passage whose head and tail match, in order, close enough to be the same passage.

    This is what catches "an inserted word" — the fourth of the four transcription defects Phase 2.1
    found and the only one no exact level can reach. It is a CANDIDATE. A reviewer decides.
    """
    if len(needle) < APPROXIMATE_EDGE * 2:
        return None
    head, tail = needle[:APPROXIMATE_EDGE], needle[-APPROXIMATE_EDGE:]
    start = space.text.find(head)
    if start < 0:
        return None
    end = space.text.find(tail, start + APPROXIMATE_EDGE)
    if end < 0:
        return None
    length = end + APPROXIMATE_EDGE - start
    if length > len(needle) * APPROXIMATE_SLACK:
        return None
    return space.original_span(start, length)
