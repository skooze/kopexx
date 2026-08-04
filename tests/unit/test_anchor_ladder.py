"""The six-level anchor ladder, and the line between a PROOF and a CANDIDATE.

WHAT IS ACTUALLY UNDER TEST. Not that a search finds a string. The subject is which near-misses
this repository is allowed to call `resolved` and which it must hand to a person instead. Levels 1
through 4 fold away a defect of TRANSCRIPTION — a full-width digit, a reflowed line, a retyped en
dash — and every one of them still demands the same characters in the same order. Levels 5 and 6
fold away a defect of JUDGEMENT, so they produce a candidate. A count that treated either as proof
would be a citation rate flattering the model that produced it, which is the one failure the whole
ladder exists to prevent, so it is asserted explicitly rather than implied by an enum membership.

THE DEFECT THAT MOTIVATED THE LADDER IS THE ENTITY ONE, AND IT HAS ITS OWN TEST. The package
records that Apple's 10-Q primary document for accession 0000320193-25-000008 carries 970 character
references and not one literal non-ASCII character, 116 of them `&#8217;`. A model reading those
bytes and quoting a sentence back writes the apostrophe, not the escape — so without the decode
transform a transcription-perfect citation fails in a way indistinguishable from a fabricated one.

OFFSETS ARE THE OTHER HALF, AND A VERDICT-ONLY TEST WOULD NOT SEE THEM. Every level searches a
TRANSFORMED text and must report a position in the ORIGINAL. A ladder whose index maps were wrong
would still return the right resolution while highlighting bytes that are merely nearby, and it
would get further wrong the more markup a filing carries — which is exactly the filings where a
reviewer most needs the highlight. Every offset assertion below slices the original and reads it.
"""

from __future__ import annotations

import pytest

from packages.coverage_validation import (
    AMBIGUITY_THRESHOLD,
    RESOLVED,
    ArtifactIndex,
    ReferenceOutcome,
    Resolution,
)
from packages.coverage_validation.references import APPROXIMATE_EDGE, HUMAN_REVIEW_CANDIDATE

#: The sentence the APPROXIMATE tests work over. Forty characters of each end must survive the
#: insertion with a middle left over, so nothing shorter can exercise that level at all.
LONG_SENTENCE = (
    "The Company designs, manufactures and markets smartphones, personal computers, "
    "tablets, wearables and accessories, and sells a variety of related services."
)

#: Pure ASCII, no markup, no escapes, already NFKC, no typographic punctuation: every transform in
#: the chain is a no-op over it and returns no index map at all.
ASCII_SOURCE = "Total net sales increased 2 percent in the 2024-2025 period to 124,300."


def resolve(source: str, quote: str, *, filename: str = "filing.htm") -> ReferenceOutcome:
    """One anchor against one artifact, which is the shape almost every question below takes."""
    return ArtifactIndex({filename: source}).resolve(filename, quote, node_id="n1")


# --- levels 1 to 4, the rungs that count as resolved ---------------------------------------------


def test_a_verbatim_quote_resolves_at_level_one_in_the_bytes_as_filed() -> None:
    """Level 1 is the only rung that folds nothing, and the record has to be able to say so.

    `resolution` alone cannot say it: TEXT_ONLY is one value covering four levels, so a report that
    could not tell an exact hit in the filed bytes from a hyphen-folded hit in rendered prose would
    have thrown away the measurement the ladder was added to make.
    """
    outcome = resolve("Total net sales increased 2 percent.", "Total net sales increased")
    assert outcome.resolution is Resolution.EXACT
    assert outcome.level == 1
    assert outcome.markup_stripped is False
    assert outcome.resolved is True
    assert outcome.review_candidate is False


@pytest.mark.parametrize(
    ("source", "quote"),
    [
        pytest.param("net sales of 124,300 in 2024", "net sales of １２４,３００", id="full-width"),
        pytest.param("a significant portion of revenue", "a signiﬁcant portion", id="fi-ligature"),
    ],
)
def test_a_compatibility_character_folds_at_level_two(source: str, quote: str) -> None:
    """NFKC is applied PER CHARACTER so one output character maps back to one input position.

    A full-width digit and an `fi` ligature are the two shapes that reach a filing: one from a
    model retyping a figure, one from a PDF-derived source. Neither is a different number or a
    different word, and recording either as a fabrication would make the unresolved count a
    measure of typesetting.
    """
    assert quote not in source, "the folded quote must not be present verbatim"
    outcome = resolve(source, quote)
    assert outcome.resolution is Resolution.UNICODE_NORMALISED
    assert outcome.level == 2
    assert outcome.resolved is True


def test_a_reflowed_quote_resolves_at_level_three_and_carries_the_source_line_break() -> None:
    """Filings wrap prose at a fixed column with arbitrary indentation; a model does not.

    The match is found in a text where the wrap has been collapsed, and the offset must still point
    at the wrapped original — so the reported span here contains the newline and the indentation
    that the searched text no longer had.
    """
    source = "Total net sales\n        increased 2 percent during the quarter."
    quote = "Total net sales increased 2 percent"
    assert quote not in source, "the reflowed quote must not be present verbatim"
    outcome = resolve(source, quote)
    assert outcome.resolution is Resolution.WHITESPACE_NORMALISED
    assert outcome.level == 3
    assert outcome.offset is not None
    assert source[outcome.offset : outcome.offset + outcome.match_length] == (
        "Total net sales\n        increased 2 percent"
    )


@pytest.mark.parametrize(
    ("source", "quote"),
    [
        pytest.param(
            "the 2024–2025 transition period", "the 2024-2025 transition period", id="en-dash"
        ),
        pytest.param(
            "net sales — excluding services — rose",
            "net sales - excluding services - rose",
            id="em-dash",
        ),
        pytest.param(
            "the Company’s fiscal year", "the Company's fiscal year", id="curly-apostrophe"
        ),
    ],
)
def test_a_dash_or_a_quote_mark_retyped_as_ascii_folds_at_level_four(
    source: str, quote: str
) -> None:
    """Dashes and quote marks share one rung because a model retypes them in the same breath.

    Splitting them into two levels would add a rung that changes no verdict and one more number for
    a reviewer to interpret. The curly apostrophe is in this test rather than its own because it is
    the same defect class, not because it is rare — it is the commonest of the three.
    """
    assert quote not in source, "the folded quote must not be present verbatim"
    outcome = resolve(source, quote)
    assert outcome.resolution is Resolution.HYPHEN_NORMALISED
    assert outcome.level == 4
    assert outcome.resolved is True


# --- the rendered-text space: markup and escapes --------------------------------------------------


def test_a_quote_spanning_markup_resolves_text_only_and_says_the_markup_was_stripped() -> None:
    """A figure and its row label are not contiguous in any real filing that carries a table.

    `markup_stripped` is what tells a reviewer which of the two spaces the hit came from, and the
    level records that the tag-to-space substitution left two spaces where two tags met — so the
    whitespace rung, not the exact one, is what closes a quote written with one space in it.
    """
    source = "<td>Total net sales</td><td>124,300</td>"
    quote = "Total net sales 124,300"
    assert quote not in source, "the quote must not be contiguous in the preserved markup"
    outcome = resolve(source, quote)
    assert outcome.resolution is Resolution.TEXT_ONLY
    assert outcome.markup_stripped is True
    assert outcome.level == 3
    assert outcome.resolved is True


def test_a_quote_carrying_an_apostrophe_resolves_against_the_filings_escaped_one() -> None:
    """THE DEFECT THE WHOLE DECODE TRANSFORM EXISTS FOR, and it is not a detail.

    A modern filing writes every apostrophe as `&#8217;` — 116 of them in the Apple 10-Q the package
    measured, alongside 655 `&#160;` and not one literal non-ASCII character. A model quoting a
    sentence back writes the character. Without the decode step every such citation is UNRESOLVED,
    and an unresolved citation is the loudest fabrication signal this repository has, so the whole
    class of them would have been read as the model inventing text it had copied exactly.

    The reported span covers the ESCAPE in the original bytes, which is the only useful answer: it
    is what a reviewer needs highlighted, and it is longer than the quote that was asked about.
    """
    source = "<p>the Company&#8217;s fiscal year</p>"
    outcome = resolve(source, "the Company’s fiscal year")
    assert outcome.resolution is Resolution.TEXT_ONLY
    assert outcome.level == 1, "an escape decoded is an EXACT hit in the rendered space"
    assert outcome.markup_stripped is True
    assert outcome.resolved is True
    assert outcome.offset is not None
    assert source[outcome.offset : outcome.offset + outcome.match_length] == (
        "the Company&#8217;s fiscal year"
    )


def test_a_straight_apostrophe_still_reaches_the_filings_escaped_curly_one() -> None:
    """The two folds compose, and a reader should not have to take that on trust.

    `&#8217;` decodes to a CURLY apostrophe, and a model that retypes rather than copies writes a
    straight one. Only the typographic rung applied on top of the decoded rendered text closes that
    gap, so this is the case that proves the entity transform did not replace level 4 for it.
    """
    outcome = resolve("<p>the Company&#8217;s fiscal year</p>", "the Company's fiscal year")
    assert outcome.resolution is Resolution.TEXT_ONLY
    assert outcome.level == 4
    assert outcome.resolved is True


@pytest.mark.parametrize(
    ("source", "quote", "expected_level"),
    [
        pytest.param("<p>Total&#160;net&#160;sales</p>", "Total net sales", 2, id="nbsp"),
        pytest.param("<p>Smith &amp; Wesson filed</p>", "Smith & Wesson filed", 1, id="ampersand"),
    ],
)
def test_a_numeric_and_a_named_escape_both_decode_in_the_rendered_space(
    source: str, quote: str, expected_level: int
) -> None:
    """Both reference syntaxes decode, and the rung each lands on is recorded rather than assumed.

    `&#160;` becomes a non-breaking space, which is not an ASCII space, so it takes the Unicode
    rung on top of the decode — two transforms for what a reader sees as one word gap. `&amp;` is
    an exact hit the moment it is decoded. Pinning both keeps a future change to either transform
    from silently moving where the commonest escapes in the corpus resolve.
    """
    outcome = resolve(source, quote)
    assert outcome.resolution is Resolution.TEXT_ONLY
    assert outcome.markup_stripped is True
    assert outcome.level == expected_level
    assert outcome.resolved is True


# --- levels 5 and 6, which locate something and prove nothing -------------------------------------


def test_a_case_folded_near_match_is_a_candidate_and_is_never_counted_as_resolved() -> None:
    """THE RULE THE LADDER EXISTS TO KEEP. A rung that locates is not a rung that proves.

    A filing writing a heading in capitals and a model writing it in title case are probably the
    same passage, and "probably" is a person's call. The assertion that matters here is the
    negative one: `resolved` is False and CASE_INSENSITIVE is absent from RESOLVED, so no count
    anywhere can pick this up as evidence. Everything else in this test is decoration.
    """
    outcome = resolve(
        "ITEM 1A. RISK FACTORS AND OTHER MATTERS\n", "Item 1A. Risk Factors and Other Matters"
    )
    assert outcome.resolution is Resolution.CASE_INSENSITIVE
    assert outcome.level == 5
    assert outcome.resolved is False
    assert outcome.review_candidate is True
    assert outcome.located is True, "a candidate still tells a reviewer where to look"
    assert Resolution.CASE_INSENSITIVE not in RESOLVED
    assert Resolution.CASE_INSENSITIVE in HUMAN_REVIEW_CANDIDATE


def test_a_word_inserted_into_the_middle_locates_an_approximate_candidate() -> None:
    """The fourth of Phase 2.1's four transcription defects, and the only one no exact rung reaches.

    Head and tail both occur, in order, close enough together to be one passage. That locates
    something a reviewer can look at and establishes nothing at all about it, so the verdict is a
    candidate — the located region is the SOURCE sentence, which is shorter than the quote asked
    about, and calling that a resolution would mean counting text the filing does not contain.
    """
    quote = LONG_SENTENCE.replace("tablets,", "certain tablets,")
    assert quote != LONG_SENTENCE and len(quote) >= APPROXIMATE_EDGE * 2
    outcome = resolve(LONG_SENTENCE, quote)
    assert outcome.resolution is Resolution.APPROXIMATE
    assert outcome.level == 6
    assert outcome.resolved is False
    assert outcome.review_candidate is True
    assert Resolution.APPROXIMATE not in RESOLVED
    assert outcome.offset is not None
    assert LONG_SENTENCE[outcome.offset : outcome.offset + outcome.match_length] == LONG_SENTENCE


def test_a_quote_too_short_for_the_edge_match_is_unresolved_rather_than_approximate() -> None:
    """The edge length is a floor, not a preference, and below it the answer is silence.

    Forty characters of each end is what stops two unrelated passages from both qualifying. A
    quote shorter than both edges together has no middle to insert a word into, so an approximate
    match over it would be a match on the whole quote — which is a claim the exact rungs already
    refused. UNRESOLVED is the honest answer and it is what a reviewer must be shown.
    """
    quote = "Net sales increased sharply during the quarter."
    assert len(quote) < APPROXIMATE_EDGE * 2
    outcome = resolve("Net sales increased during the quarter.", quote)
    assert outcome.resolution is Resolution.UNRESOLVED
    assert outcome.level == 0
    assert outcome.located is False
    assert outcome.resolved is False


# --- the outcomes that are not a rung at all ------------------------------------------------------


def test_a_quote_occurring_past_the_threshold_is_ambiguous_and_carries_no_offset() -> None:
    """A reference pointing everywhere locates nothing in particular and must not be counted.

    Reporting the first of many occurrences would hand the review UI an arbitrary highlight and
    inflate the citation rate with references that support no particular passage. The ambiguity
    verdict survives the deeper rungs: a phrase repeated nine times is repeated nine times at every
    level, and the ladder must not fold its way past the guard into a candidate instead.
    """
    quote = "the segment operating margin"
    outcome = resolve(" and ".join([quote] * (AMBIGUITY_THRESHOLD + 1)), quote)
    assert outcome.resolution is Resolution.AMBIGUOUS
    assert outcome.occurrences == AMBIGUITY_THRESHOLD + 1
    assert outcome.offset is None
    assert outcome.resolved is False
    assert outcome.review_candidate is False


def test_an_empty_quote_and_an_unsubmitted_source_set_are_named_separately() -> None:
    """Two failures that both mean `not located`, kept distinguishable in the preserved record.

    A model that emitted a reference with no quote and a run that submitted no text at all are
    different problems with different fixes, and one UNRESOLVED bucket would hide both behind a
    number that looks like a model defect.
    """
    populated = ArtifactIndex({"filing.htm": "Total net sales increased 2 percent."})
    empty_quote = populated.resolve("filing.htm", "   ", node_id="n1")
    assert empty_quote.resolution is Resolution.EMPTY_QUOTE
    assert empty_quote.level == 0
    assert empty_quote.resolved is False

    nothing_submitted = ArtifactIndex({}).resolve("filing.htm", "Total net sales", node_id="n1")
    assert nothing_submitted.resolution is Resolution.NO_SUCH_ARTIFACT
    assert nothing_submitted.offset is None
    assert nothing_submitted.resolved is False


# --- one coordinate system, whichever space the hit came from -------------------------------------


def test_an_offset_from_the_markup_stripped_space_indexes_the_original_bytes() -> None:
    """THE DEFECT THE INDEX MAPS EXIST TO PREVENT, asserted against the original text.

    The hit is found in a text where four tags have each become one space, so both ends of the
    match sit somewhere else there than here — three characters out at the start, eleven at the
    end. A ladder reporting the searched position would send the review UI into the middle of a
    `td` element, and the error grows with every tag a filing carries. The reported span is the
    ORIGINAL region, markup included, and it is read back below rather than trusted.
    """
    source = "<td>Total net sales</td><td>124,300</td>"
    outcome = resolve(source, "Total net sales 124,300")
    assert outcome.offset is not None
    assert outcome.offset == source.index("Total"), "the span starts at the first quoted character"
    matched = source[outcome.offset : outcome.offset + outcome.match_length]
    assert "Total net sales" in matched
    assert "124,300" in matched
    assert outcome.match_length > len("Total net sales 124,300"), (
        "the original span is longer than the quote because the markup between is included"
    )


def test_an_offset_from_the_whitespace_collapsed_space_indexes_the_original_bytes() -> None:
    """The same rule for the other transform, where the searched text is SHORTER than the original.

    Two runs collapse before this match ends — a blank line and a wrap with eight spaces of
    indentation — so the searched text is nine characters shorter than the bytes by the time the
    quote finishes. The span reported here has to cover the wrapped original including the newline
    and the indentation, or a highlight over a pre-2001 filing, which wraps every line it has,
    starts drifting on the first paragraph and never recovers.
    """
    source = "Item 1.\n\nTotal net sales\n        increased 2 percent during the quarter."
    outcome = resolve(source, "Total net sales increased 2 percent")
    assert outcome.offset is not None
    assert outcome.offset == source.index("Total")
    matched = source[outcome.offset : outcome.offset + outcome.match_length]
    assert matched.startswith("Total net sales")
    assert matched.endswith("2 percent")
    assert "\n        " in matched, "the collapsed run is inside the reported original span"


@pytest.mark.parametrize(
    ("quote", "expected", "expected_level", "matched"),
    [
        pytest.param(
            "Total net sales increased",
            Resolution.EXACT,
            1,
            "Total net sales increased",
            id="level-1-exact",
        ),
        pytest.param(
            "１２４,３００",
            Resolution.UNICODE_NORMALISED,
            2,
            "124,300",
            id="level-2-unicode",
        ),
        pytest.param(
            "Total net  sales increased",
            Resolution.WHITESPACE_NORMALISED,
            3,
            "Total net sales increased",
            id="level-3-whitespace",
        ),
        pytest.param(
            "the 2024–2025 period",
            Resolution.HYPHEN_NORMALISED,
            4,
            "the 2024-2025 period",
            id="level-4-typographic",
        ),
    ],
)
def test_a_transform_that_changed_nothing_still_reports_a_true_offset(
    quote: str, expected: Resolution, expected_level: int, matched: str
) -> None:
    """THE IDENTITY SHORTCUT, which is a performance decision with a correctness consequence.

    Every transform returns no index map when it changed nothing, because building one Python
    integer per character for four levels over both spaces of a 732 KB document is roughly ten
    million iterations per artifact — and SEC markup is overwhelmingly ASCII, so most of those
    transforms are no-ops. The consequence is that a hit at every rung of a source the chain never
    touched has to fall through to the identity mapping, and a fold applied to the QUOTE alone must
    still land on the right bytes. Nothing here is exercised by a source that needs the maps.
    """
    outcome = resolve(ASCII_SOURCE, quote)
    assert outcome.resolution is expected
    assert outcome.level == expected_level
    assert outcome.markup_stripped is False
    assert outcome.offset is not None
    assert ASCII_SOURCE[outcome.offset : outcome.offset + outcome.match_length] == matched


# --- which hit wins ------------------------------------------------------------------------------


def test_an_exact_hit_in_the_wrong_named_artifact_beats_a_folded_hit_in_the_right_one() -> None:
    """LEVEL ORDER BEATS ARTIFACT ORDER, and it has to be proved on a case where they disagree.

    Searching every rung of the named artifact before touching the next one would report the weaker
    of two available hits, and the level number is the measurement this phase was added to produce.
    The second half of the test is the control: the named artifact really does hold a hyphen-folded
    match, so the exact hit was chosen over an available alternative rather than by default.
    """
    index = ArtifactIndex(
        {
            "primary.htm": "the 2024–2025 transition period was reported",
            "exhibit-99.htm": "the 2024-2025 transition period was reported",
        }
    )
    outcome = index.resolve("primary.htm", "the 2024-2025 transition period", node_id="n1")
    assert outcome.resolution is Resolution.EXACT
    assert outcome.level == 1
    assert outcome.filename == "exhibit-99.htm"

    alone = resolve(
        "the 2024–2025 transition period was reported",
        "the 2024-2025 transition period",
        filename="primary.htm",
    )
    assert alone.resolution is Resolution.HYPHEN_NORMALISED
    assert alone.level == 4
