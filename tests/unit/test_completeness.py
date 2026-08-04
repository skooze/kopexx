"""Every accounting `packages/completeness` makes, proved against a filing small enough to count.

WHY THE FIXTURE IS FOUR LINES OF SYNTHETIC PROSE AND NOT A REAL FILING. The subject of this package
is a DENOMINATOR, and a test whose denominator is the 41 table elements of somebody's 10-Q proves
nothing about the arithmetic — it proves that a number came out. Four spans, one table element and
one image can be counted by hand, so every assertion below states the whole filing it measures.

HERMETIC. No network, no AWS, no provider, no clock, no filesystem. Inventories are built from
`packages.source_inventory` records directly rather than by walking markup: a ledger test that
depended on the markup walker would go red for reasons that have nothing to do with the ledger, and
the walker has its own tests.

WHAT IS BEING PROVED, IN ONE SENTENCE. That SILENCE IS COUNTED. A source range no part of the parse
ever mentioned must come out as SILENTLY_OMITTED and must fail the gate — the omission a reference
rate cannot see, because a region a model never cited never enters a reference rate's denominator.

The single most important test in this file is `test_prose_about_a_table_does_not_discharge_the
_table`. Phase 2.1 measured `table_count` as ZERO across all seven proof runs while its candidates
carried tabular material as narrative and its numeric validator confirmed those numbers occurred in
the preserved bytes. That combination — real numbers, real citations, no table — is exactly what
this package has to refuse to call coverage.
"""

from __future__ import annotations

from typing import Any

import pytest

from packages.completeness import (
    BenchmarkTruth,
    BenchmarkTruthError,
    CompletenessLedger,
    ConvergenceState,
    CoverageClaim,
    Disposition,
    GateResult,
    HumanReadiness,
    ImageClassification,
    ImageState,
    Interval,
    Judgement,
    LedgerInputError,
    SerializationState,
    SourceCoverageState,
    SpanClassification,
    TableClassification,
    TableState,
    TableValidation,
    TransportState,
    build_ledger,
    covered_length,
    evaluate,
    gaps,
    merge,
    overlaps,
    resolve_claims,
    suggest,
    table_source_interval,
    validate_table,
    validate_tables,
)
from packages.coverage_validation import ArtifactIndex, ReferenceOutcome, Resolution
from packages.multipart import StructuredTable, read_table
from packages.source_inventory import (
    FilingInventory,
    HiddenReason,
    ImageRecord,
    MemberRecord,
    TableCell,
    TableElement,
    TextSpan,
)

CIK = "0000320193"
ACCESSION = "0000320193-25-000008"
SOURCE_SHA = "a" * 64
AT = "2026-08-04T00:00:00Z"
MEMBER = "primary.htm"
EXHIBIT = "exhibit.htm"
IMAGE = "chart.gif"

#: The whole filing. One span per line; the fourth line is also the one table element. Every count
#: asserted below is readable straight off this tuple, which is the only reason the counts mean
#: anything: a denominator nobody can verify by eye is how "352 of 364 resolved" came to be read as
#: 96.7 percent of a filing.
LINES: tuple[str, ...] = (
    "Item 1. The Company designs and manufactures widgets in several countries.",
    "Item 2. Properties are held in fee and under lease in many locations.",
    "Item 3. Legal Proceedings are described in Note 11 to the financial statements.",
    "Net sales 391,035 383,285 394,328",
)
SOURCE_TEXT = "".join(line + "\n" for line in LINES)
EXHIBIT_TEXT = "Exhibit 21. Subsidiaries of the registrant are listed in this schedule.\n"

SPAN_IDS: tuple[str, ...] = tuple(f"{MEMBER}#s{index}" for index in range(len(LINES)))
TABLE_ID = f"{MEMBER}#t0"
TABLE_CELLS: tuple[str, ...] = ("Net sales", "391,035", "383,285", "394,328")


# --- fixture builders ----------------------------------------------------------------------------
#
# Records are constructed field by field rather than through `build_inventory`. The point is that
# each test states its own denominator: a helper that quietly added a span would move every number
# in this file at once, and the drift would look like a passing suite.


def _bounds(line: int) -> tuple[int, int]:
    start = SOURCE_TEXT.index(LINES[line])
    return start, start + len(LINES[line])


def _span(
    line: int,
    *,
    hidden: HiddenReason = HiddenReason.VISIBLE,
    duplicate_of: str = "",
) -> TextSpan:
    start, end = _bounds(line)
    return TextSpan(
        span_id=SPAN_IDS[line],
        member=MEMBER,
        start=start,
        end=end,
        original_text=LINES[line],
        normalized_text=LINES[line],
        hidden_reason=hidden,
        element_path=f"/html/body/p[{line}]",
        parent_element="p",
        table_id=TABLE_ID if line == 3 else "",
        duplicate_of=duplicate_of,
    )


def _all_spans() -> tuple[TextSpan, ...]:
    return tuple(_span(line) for line in range(len(LINES)))


def _table_element(
    *,
    table_id: str = TABLE_ID,
    cells: tuple[str, ...] = TABLE_CELLS,
    duplicate_of: str = "",
    sha256: str = "b" * 64,
) -> TableElement:
    start, end = _bounds(3)
    return TableElement(
        table_id=table_id,
        member=MEMBER,
        start=start,
        end=end,
        element_path="/html/body/table",
        parent_table_id="",
        nesting_depth=0,
        row_count=1,
        max_columns=len(cells),
        cell_count=len(cells),
        sha256=sha256,
        cells=tuple(
            TableCell(
                row_index=0,
                column_index=column,
                row_span=1,
                column_span=1,
                is_header=False,
                text=text,
                start=start,
                end=end,
            )
            for column, text in enumerate(cells)
        ),
        duplicate_of=duplicate_of,
    )


def _text_member() -> MemberRecord:
    return MemberRecord(
        filename=MEMBER,
        member=MEMBER,
        declared_type="10-K",
        description="the primary document",
        media_type="text/html",
        byte_count=len(SOURCE_TEXT),
        sha256="c" * 64,
        transport_role="PARSER_INPUT_TEXT",
        human_readable=True,
        image=False,
        character_count=len(SOURCE_TEXT),
        duplicate_of="",
        span_count=len(LINES),
        table_count=1,
    )


def _image_member() -> MemberRecord:
    return MemberRecord(
        filename=IMAGE,
        member=IMAGE,
        declared_type="GRAPHIC",
        description="a filed chart",
        media_type="image/gif",
        byte_count=1024,
        sha256="e" * 64,
        transport_role="PARSER_INPUT_IMAGE",
        human_readable=False,
        image=True,
        character_count=0,
        duplicate_of="",
        span_count=0,
        table_count=0,
    )


def _transport_member() -> MemberRecord:
    """A member whose bytes never reach the parsing model — an XBRL schema, say."""
    return MemberRecord(
        filename="schema.xsd",
        member="schema.xsd",
        declared_type="EX-101.SCH",
        description="the taxonomy extension schema",
        media_type="application/xml",
        byte_count=4096,
        sha256="f" * 64,
        transport_role="TRANSPORT_ONLY",
        human_readable=False,
        image=False,
        character_count=0,
        duplicate_of="",
        span_count=0,
        table_count=0,
    )


def _image_record() -> ImageRecord:
    return ImageRecord(
        filename=IMAGE,
        member=IMAGE,
        media_type="image/gif",
        byte_count=1024,
        sha256="e" * 64,
        width=320,
        height=200,
        referenced_at=((MEMBER, 0),),
    )


def _inventory(
    *,
    spans: tuple[TextSpan, ...] | None = None,
    tables: tuple[TableElement, ...] = (),
    images: tuple[ImageRecord, ...] = (),
    members: tuple[MemberRecord, ...] | None = None,
    source_set_sha256: str = SOURCE_SHA,
) -> FilingInventory:
    return FilingInventory(
        cik=CIK,
        accession=ACCESSION,
        form_as_filed="10-K",
        filing_date="2025-01-31",
        report_period="2024-12-28",
        source_set_sha256=source_set_sha256,
        members=(_text_member(),) + tuple(_image_member() for _ in images)
        if members is None
        else members,
        spans=_all_spans() if spans is None else spans,
        tables=tables,
        images=images,
    )


def _index(extra: dict[str, str] | None = None) -> ArtifactIndex:
    texts = {MEMBER: SOURCE_TEXT}
    texts.update(extra or {})
    return ArtifactIndex(texts)


def _claim(
    first: int, last: int, *, part_id: str = "part-a", unresolved: bool = False
) -> CoverageClaim:
    """One claim bounded by the head of line `first` and the tail of line `last`.

    Both anchors are verbatim slices of the fixture, which is what makes the resulting interval a
    fact about the bytes rather than about this helper.
    """
    return CoverageClaim(
        member=MEMBER,
        start_anchor=LINES[first][:28],
        end_anchor=LINES[last][-28:],
        intermediate_anchors=(),
        part_id=part_id,
        purpose="the model's own words for what it did here",
        unresolved=unresolved,
    )


def _reversed_claim() -> CoverageClaim:
    """A claim whose end anchor sits before its start anchor in the preserved bytes."""
    return CoverageClaim(
        member=MEMBER,
        start_anchor=LINES[3][-28:],
        end_anchor=LINES[0][:28],
        intermediate_anchors=(),
        part_id="part-reversed",
        purpose="a region the model believed it had bounded",
        unresolved=False,
    )


def _truth(
    *judgements: tuple[str, str, str], source_set_sha256: str = SOURCE_SHA
) -> BenchmarkTruth:
    truth = BenchmarkTruth.empty(cik=CIK, accession=ACCESSION, source_set_sha256=source_set_sha256)
    for kind, item_id, classification in judgements:
        truth = truth.with_judgement(
            kind,
            Judgement(item_id=item_id, classification=classification, reviewer="a reviewer", at=AT),
        )
    return truth


def _reviewed_truth(*overrides: tuple[str, str, str]) -> BenchmarkTruth:
    """Every fixture item classified as required content, then whatever a test overrides."""
    return _truth(
        *(
            ("span", span_id, SpanClassification.MATERIAL_FILING_CONTENT.value)
            for span_id in SPAN_IDS
        ),
        ("table", TABLE_ID, TableClassification.DATA_BEARING.value),
        ("image", IMAGE, ImageClassification.DATA_BEARING.value),
        *overrides,
    )


def _structured_table(**overrides: Any) -> StructuredTable:
    raw: dict[str, Any] = {
        "table_id": "the net sales table",
        "source_member": MEMBER,
        "source_table_id": TABLE_ID,
        "rows": [[{"text": text} for text in TABLE_CELLS]],
    }
    raw.update(overrides)
    table = read_table(raw)
    assert table is not None, "the fixture table must name an identifier"
    return table


def _accounted_inputs() -> dict[str, Any]:
    """A parse that accounts for every item of the fixture filing. The baseline every test flips."""
    return {
        "inventory": _inventory(tables=(_table_element(),), images=(_image_record(),)),
        "truth": _reviewed_truth(),
        "index": _index(),
        "claims": (_claim(0, 3),),
        "reference_outcomes": (),
        "structured_tables": (_structured_table(),),
        "declared_unresolved_spans": frozenset(),
        "declared_unresolved_tables": frozenset(),
        "images_submitted": frozenset({IMAGE}),
        "image_references": frozenset({IMAGE}),
        "model_accepts_images": True,
    }


def _build(**overrides: Any) -> CompletenessLedger:
    inputs = _accounted_inputs()
    inputs.update(overrides)
    return build_ledger(**inputs)


def _gate_inputs() -> dict[str, Any]:
    return {
        "transport": TransportState.INVOKED,
        "serialization": SerializationState.RAW_PARSEABLE,
        "convergence": ConvergenceState.CONVERGED,
        "human_readiness": HumanReadiness.READY_FOR_REVIEW,
        "unparseable_effective_artifacts": 0,
        "nonterminal_required_jobs": 0,
        "truncations_without_replacement": 0,
        "reconciliation_created_new_work": False,
        "repeated_gap_fingerprints": 0,
        "unsettled_reservations": 0,
        "held_billing_unknown": 0,
        "structured_tables_failing_validation": 0,
    }


def _gate(ledger: CompletenessLedger, **overrides: Any) -> GateResult:
    inputs = _gate_inputs()
    inputs.update(overrides)
    return evaluate(ledger, **inputs)


def _failed(result: GateResult) -> tuple[int, ...]:
    return tuple(condition.number for condition in result.failed)


# --- intervals ------------------------------------------------------------------------------------


def test_merge_joins_two_ranges_that_meet_end_to_start() -> None:
    assert merge([Interval(0, 10), Interval(10, 20)]) == (Interval(0, 20),)


def test_merge_joins_overlapping_ranges_and_counts_the_shared_region_once() -> None:
    """Summing lengths without merging is how one paragraph claimed three times reads as 300%."""
    merged = merge([Interval(0, 10), Interval(5, 20)])
    assert merged == (Interval(0, 20),)
    assert covered_length(merged) == 20


def test_merge_leaves_disjoint_ranges_apart() -> None:
    """MUTATION PROOF. A merge that joined everything would report total coverage of any filing."""
    assert merge([Interval(0, 10), Interval(30, 40)]) == (Interval(0, 10), Interval(30, 40))


def test_merge_swallows_a_range_wholly_inside_another() -> None:
    assert merge([Interval(0, 100), Interval(40, 50)]) == (Interval(0, 100),)


def test_merge_of_nothing_is_nothing() -> None:
    assert merge([]) == ()


def test_gaps_finds_the_head_the_middle_and_the_tail_of_an_uncovered_window() -> None:
    """The head and the tail are the ones a naive implementation loses, and they are filing content.

    A parse that starts at the first heading and stops at the signature block leaves a cover page
    and an exhibit index uncovered; both sit outside every claimed interval, at the two ends.
    """
    found = gaps((Interval(10, 20), Interval(30, 40)), within=Interval(0, 50))
    assert found == (Interval(0, 10), Interval(20, 30), Interval(40, 50))


def test_gaps_of_a_fully_covered_window_is_empty() -> None:
    assert gaps((Interval(0, 50),), within=Interval(0, 50)) == ()


def test_gaps_ignores_coverage_that_falls_outside_the_window() -> None:
    assert gaps((Interval(100, 200),), within=Interval(0, 50)) == (Interval(0, 50),)


def test_gaps_of_a_window_nobody_claimed_is_the_whole_window() -> None:
    assert gaps((), within=Interval(0, 50)) == (Interval(0, 50),)


def test_overlaps_reports_the_region_two_claims_both_touch() -> None:
    """Reported, never resolved: two parts covering one paragraph may be a defect or a reading."""
    assert overlaps([Interval(0, 10), Interval(5, 20)]) == (Interval(5, 10),)


def test_overlaps_of_disjoint_claims_is_empty() -> None:
    """MUTATION PROOF. An overlap detector that fired on adjacency would flag every plan."""
    assert overlaps([Interval(0, 10), Interval(10, 20)]) == ()


def test_overlaps_merges_a_region_three_claims_share() -> None:
    assert overlaps([Interval(0, 10), Interval(2, 10), Interval(4, 10)]) == (Interval(2, 10),)


def test_covered_length_never_double_counts() -> None:
    assert covered_length((Interval(0, 10), Interval(0, 10), Interval(0, 10))) == 10
    assert covered_length(()) == 0


def test_an_interval_that_ends_before_it_begins_is_refused() -> None:
    with pytest.raises(ValueError, match="ends before it begins"):
        Interval(20, 10)


def test_an_empty_interval_is_permitted_because_a_zero_length_match_is_a_real_outcome() -> None:
    assert Interval(10, 10).length == 0
    assert Interval(10, 10).intersection(Interval(0, 50)) is None


def test_an_interval_reports_the_positions_it_contains() -> None:
    window = Interval(10, 20)
    assert window.contains(10) is True
    assert window.contains(20) is False
    assert window.to_mapping() == {"start": 10, "end": 20, "length": 10}


# --- the benchmark truth --------------------------------------------------------------------------


def test_every_item_is_requires_review_until_a_person_says_otherwise() -> None:
    """A default of MATERIAL would demand every layout table; a default of LAYOUT would excuse a
    financial statement. REQUIRES_REVIEW is honest about the evidence and it blocks the gate."""
    truth = BenchmarkTruth.empty(cik=CIK, accession=ACCESSION, source_set_sha256=SOURCE_SHA)
    assert truth.span(SPAN_IDS[0]) is SpanClassification.REQUIRES_REVIEW
    assert truth.table(TABLE_ID) is TableClassification.REQUIRES_REVIEW
    assert truth.image(IMAGE) is ImageClassification.REQUIRES_REVIEW
    assert truth.reviewed_count == 0
    assert truth.suggestion_count == 0


def test_a_suggested_judgement_does_not_change_the_effective_classification() -> None:
    """THE WHOLE POINT OF THE SUGGESTED FLAG, ASSERTED DIRECTLY.

    A mechanical proposal that took effect on its own would be backend code deciding that a table
    is layout — the judgement rules.md section 21 rule 1 puts outside backend code entirely. The
    proposal is carried, the evidence is carried, and the effective classification does not move
    until a person records the same judgement without the flag.
    """
    proposed = BenchmarkTruth.empty(
        cik=CIK, accession=ACCESSION, source_set_sha256=SOURCE_SHA
    ).with_judgement(
        "table",
        Judgement(
            item_id=TABLE_ID,
            classification=TableClassification.LAYOUT.value,
            reviewer="",
            at=AT,
            suggested=True,
            evidence="its cells carry no non-whitespace character",
        ),
    )
    assert proposed.table(TABLE_ID) is TableClassification.REQUIRES_REVIEW
    assert proposed.tables[TABLE_ID].classification == TableClassification.LAYOUT.value
    assert proposed.suggestion_count == 1
    assert proposed.reviewed_count == 0

    accepted = proposed.with_judgement(
        "table",
        Judgement(
            item_id=TABLE_ID,
            classification=TableClassification.LAYOUT.value,
            reviewer="a reviewer",
            at=AT,
        ),
    )
    assert accepted.table(TABLE_ID) is TableClassification.LAYOUT
    assert accepted.reviewed_count == 1


def test_with_judgement_supersedes_rather_than_edits() -> None:
    """A coverage figure computed against version 3 is meaningless if version 3 can become 4."""
    first = _truth(("span", SPAN_IDS[0], SpanClassification.MATERIAL_FILING_CONTENT.value))
    second = first.with_judgement(
        "span",
        Judgement(
            item_id=SPAN_IDS[1],
            classification=SpanClassification.NAVIGATION.value,
            reviewer="a reviewer",
            at=AT,
        ),
    )
    assert second.version == first.version + 1
    assert set(first.spans) == {SPAN_IDS[0]}, "the earlier document was edited in place"
    assert set(second.spans) == {SPAN_IDS[0], SPAN_IDS[1]}
    assert first.span(SPAN_IDS[1]) is SpanClassification.REQUIRES_REVIEW


def test_a_classification_that_does_not_exist_is_refused_rather_than_coerced() -> None:
    """Coerced to REQUIRES_REVIEW it would look exactly like an item nobody had reviewed."""
    truth = BenchmarkTruth.empty(cik=CIK, accession=ACCESSION, source_set_sha256=SOURCE_SHA)
    with pytest.raises(BenchmarkTruthError, match="is not a span classification"):
        truth.with_judgement(
            "span",
            Judgement(
                item_id=SPAN_IDS[0], classification="PROBABLY_BOILERPLATE", reviewer="r", at=AT
            ),
        )


def test_a_judgement_about_something_that_is_not_an_inventory_item_is_refused() -> None:
    truth = BenchmarkTruth.empty(cik=CIK, accession=ACCESSION, source_set_sha256=SOURCE_SHA)
    with pytest.raises(BenchmarkTruthError, match="span, table or image"):
        truth.with_judgement(
            "footnote",
            Judgement(item_id="n1", classification="DATA_BEARING", reviewer="r", at=AT),
        )


def test_a_classification_a_stored_document_no_longer_recognises_reads_as_requires_review() -> None:
    """A value read back from disk is coerced, unlike one being recorded: refusing at read time
    would make a whole preserved truth document unloadable because one enum member was renamed."""
    restored = BenchmarkTruth.from_mapping(
        {
            "cik": CIK,
            "accession": ACCESSION,
            "source_set_sha256": SOURCE_SHA,
            "version": 4,
            "spans": {SPAN_IDS[0]: {"classification": "A_MEMBER_THAT_WAS_RENAMED"}},
        }
    )
    assert restored.span(SPAN_IDS[0]) is SpanClassification.REQUIRES_REVIEW
    assert restored.spans[SPAN_IDS[0]].classification == "A_MEMBER_THAT_WAS_RENAMED"


def test_a_truth_document_survives_a_round_trip_through_its_mapping() -> None:
    """Every field, in all three groups, including the flag that decides whether it counts."""
    truth = (
        BenchmarkTruth.empty(cik=CIK, accession=ACCESSION, source_set_sha256=SOURCE_SHA)
        .with_judgement(
            "span",
            Judgement(
                item_id=SPAN_IDS[0],
                classification=SpanClassification.MATERIAL_FILING_CONTENT.value,
                reviewer="a reviewer",
                at=AT,
                note="the first item of the annual report",
                evidence="read against the preserved bytes",
            ),
        )
        .with_judgement(
            "table",
            Judgement(
                item_id=TABLE_ID,
                classification=TableClassification.EMPTY.value,
                reviewer="",
                at=AT,
                note="proposed mechanically",
                suggested=True,
                evidence="none of its 4 cells carries a non-whitespace character",
            ),
        )
        .with_judgement(
            "image",
            Judgement(
                item_id=IMAGE,
                classification=ImageClassification.DATA_BEARING.value,
                reviewer="a reviewer",
                at=AT,
            ),
        )
    )
    assert BenchmarkTruth.from_mapping(truth.to_mapping()) == truth


def test_a_truth_mapping_says_it_is_evidence_about_one_filing_and_never_a_rule() -> None:
    """rules.md section 21 rule 14. One issuer is a fixture, never a specification."""
    document = _truth().to_mapping()
    assert document["schema_version"] == "benchmark-truth-v1"
    assert "never a rule about filings" in document["scope_note"]


def test_from_mapping_of_a_document_with_no_optional_key_is_empty_rather_than_broken() -> None:
    restored = BenchmarkTruth.from_mapping({})
    assert restored.version == 0
    assert restored.spans == {} and restored.tables == {} and restored.images == {}


def test_suggest_proposes_duplicate_rendering_for_a_byte_identical_table() -> None:
    inventory = _inventory(
        tables=(
            _table_element(table_id=f"{MEMBER}#t0"),
            _table_element(table_id=f"{MEMBER}#t1", duplicate_of=f"{MEMBER}#t0"),
        )
    )
    proposals = suggest(inventory, at=AT)
    proposal = proposals.tables[f"{MEMBER}#t1"]
    assert proposal.classification == TableClassification.DUPLICATE_RENDERING.value
    assert proposal.suggested is True
    assert "byte-identical" in proposal.evidence
    assert proposals.table(f"{MEMBER}#t1") is TableClassification.REQUIRES_REVIEW
    assert f"{MEMBER}#t0" not in proposals.tables, "a table with text and no twin needs no proposal"


def test_suggest_proposes_empty_for_a_table_whose_cells_carry_no_text() -> None:
    inventory = _inventory(tables=(_table_element(table_id=f"{MEMBER}#t2", cells=("  ", "")),))
    proposal = suggest(inventory, at=AT).tables[f"{MEMBER}#t2"]
    assert proposal.classification == TableClassification.EMPTY.value
    assert proposal.suggested is True
    assert "non-whitespace" in proposal.evidence


def test_suggest_proposes_repeated_content_for_a_span_whose_characters_recur() -> None:
    inventory = _inventory(spans=(_span(0), _span(1, duplicate_of=SPAN_IDS[0])))
    proposals = suggest(inventory, at=AT)
    assert proposals.spans[SPAN_IDS[1]].classification == SpanClassification.REPEATED_CONTENT.value
    assert proposals.spans[SPAN_IDS[1]].suggested is True
    assert SPAN_IDS[0] not in proposals.spans


def test_suggest_accepts_none_of_its_own_proposals_and_derives_the_same_document_twice() -> None:
    """`at` is passed in rather than read from a clock: a denominator that changes every time it is
    derived cannot be compared against itself."""
    inventory = _inventory(
        spans=(_span(0), _span(1, duplicate_of=SPAN_IDS[0])),
        tables=(_table_element(cells=("", " ")),),
    )
    proposals = suggest(inventory, at=AT)
    assert proposals.reviewed_count == 0
    assert proposals.suggestion_count == 2
    assert proposals.version == 0
    assert proposals == suggest(inventory, at=AT)


# --- resolving a coverage claim -------------------------------------------------------------------


def test_a_claim_whose_two_anchors_resolve_becomes_an_interval() -> None:
    (resolved,) = resolve_claims((_claim(0, 1),), _index())
    assert resolved.finding == ""
    assert resolved.bounded is True
    assert resolved.interval == Interval(_bounds(0)[0], _bounds(1)[1])


def test_a_claim_whose_start_anchor_is_not_in_the_bytes_bounds_nothing() -> None:
    claim = CoverageClaim(
        member=MEMBER,
        start_anchor="a sentence that was never filed",
        end_anchor=LINES[1][-28:],
        intermediate_anchors=(),
        part_id="part-a",
        purpose="",
        unresolved=False,
    )
    (resolved,) = resolve_claims((claim,), _index())
    assert resolved.interval is None
    assert resolved.finding == "the start anchor does not resolve in the preserved bytes"


def test_a_claim_whose_end_anchor_is_not_in_the_bytes_bounds_nothing() -> None:
    claim = CoverageClaim(
        member=MEMBER,
        start_anchor=LINES[0][:28],
        end_anchor="a sentence that was never filed",
        intermediate_anchors=(),
        part_id="part-a",
        purpose="",
        unresolved=False,
    )
    (resolved,) = resolve_claims((claim,), _index())
    assert resolved.interval is None
    assert resolved.finding == "the end anchor does not resolve in the preserved bytes"


def test_a_claim_neither_of_whose_anchors_resolve_says_so_once() -> None:
    claim = CoverageClaim(
        member=MEMBER,
        start_anchor="neither of these",
        end_anchor="was ever filed",
        intermediate_anchors=(),
        part_id="part-a",
        purpose="",
        unresolved=False,
    )
    (resolved,) = resolve_claims((claim,), _index())
    assert resolved.finding == "neither anchor resolves in the preserved bytes"


def test_a_claim_whose_anchors_land_in_two_members_bounds_nothing() -> None:
    """Two offsets in two coordinate systems describe no single region, and an interval built from
    them would silently claim everything between them in whichever member happened to be named."""
    claim = CoverageClaim(
        member=MEMBER,
        start_anchor=LINES[0][:28],
        end_anchor="Subsidiaries of the registrant",
        intermediate_anchors=(),
        part_id="part-a",
        purpose="",
        unresolved=False,
    )
    (resolved,) = resolve_claims((claim,), _index({EXHIBIT: EXHIBIT_TEXT}))
    assert resolved.interval is None
    assert "resolve in different members" in resolved.finding
    assert MEMBER in resolved.finding and EXHIBIT in resolved.finding


def test_a_reversed_pair_is_recorded_and_never_silently_swapped() -> None:
    """A reversed pair usually means one anchor matched the wrong occurrence. Reordering it would
    manufacture an interval nobody claimed, and the manufactured one would look exactly right."""
    (resolved,) = resolve_claims((_reversed_claim(),), _index())
    assert resolved.interval is None
    assert "resolves BEFORE the start anchor" in resolved.finding
    assert "Recorded rather than swapped" in resolved.finding
    assert resolved.start.resolved and resolved.end.resolved


class _IndexResolvingWithoutAnOffset(ArtifactIndex):
    """An index whose anchors resolve and locate nothing. No real resolution reaches this state.

    The guard it exercises is worth a test anyway: without it the ledger builds `Interval(None,
    None)`, and a TypeError raised deep inside the accounting is a far worse report than a finding
    naming the claim that caused it.
    """

    def resolve(self, filename: str, quote: str, *, node_id: str) -> ReferenceOutcome:
        return ReferenceOutcome(filename, quote, Resolution.EXACT, 1, None, node_id)


def test_an_anchor_that_resolves_without_an_offset_bounds_nothing() -> None:
    index = _IndexResolvingWithoutAnOffset({MEMBER: SOURCE_TEXT})
    (resolved,) = resolve_claims((_claim(0, 1),), index)
    assert resolved.interval is None
    assert resolved.finding == "an anchor resolved without an offset"


def test_a_resolved_claim_reports_both_resolutions_and_the_finding_in_its_mapping() -> None:
    (resolved,) = resolve_claims((_reversed_claim(),), _index())
    document = resolved.to_mapping()
    assert document["interval"] is None
    assert document["part_id"] == "part-reversed"
    assert document["start_resolution"]["resolved"] is True
    assert document["model_declared_unresolved"] is False
    assert document["intermediate_anchor_count"] == 0


# --- the four dispositions ------------------------------------------------------------------------


def test_a_span_inside_a_covered_interval_is_covered() -> None:
    ledger = _build(claims=(_claim(0, 0),))
    assert ledger.spans.dispositions[SPAN_IDS[0]] is Disposition.COVERED


def test_a_span_nobody_touched_is_silently_omitted() -> None:
    ledger = _build(claims=(_claim(0, 0),))
    assert ledger.spans.dispositions[SPAN_IDS[1]] is Disposition.SILENTLY_OMITTED
    assert "no coverage claim bounds it" in ledger.spans.reasons[SPAN_IDS[1]]


def test_a_span_a_reviewer_called_navigation_is_human_excluded() -> None:
    ledger = _build(
        truth=_reviewed_truth(("span", SPAN_IDS[1], SpanClassification.NAVIGATION.value)),
        claims=(_claim(0, 0),),
    )
    assert ledger.spans.dispositions[SPAN_IDS[1]] is Disposition.HUMAN_EXCLUDED
    assert "a reviewer classified it NAVIGATION" in ledger.spans.reasons[SPAN_IDS[1]]


def test_a_span_the_model_declared_unresolved_is_unresolved_and_not_omitted() -> None:
    """rules.md section 21 rule 5: uncertainty produces PARTIAL, never a false complete — and never
    a silent omission either. A model that says it could not finish a region has done the right
    thing, and the ledger has to be able to tell that apart from saying nothing at all."""
    ledger = _build(claims=(_claim(0, 0),), declared_unresolved_spans=frozenset({SPAN_IDS[1]}))
    assert ledger.spans.dispositions[SPAN_IDS[1]] is Disposition.UNRESOLVED
    assert ledger.coverage.spans_unresolved == 1


def test_the_four_dispositions_are_mutually_exclusive_and_exhaustive() -> None:
    """One item, one disposition, and no fifth outcome. Silence has no place to hide."""
    ledger = _build(
        truth=_reviewed_truth(("span", SPAN_IDS[1], SpanClassification.NAVIGATION.value)),
        claims=(_claim(0, 0),),
        declared_unresolved_spans=frozenset({SPAN_IDS[2]}),
    )
    assert ledger.spans.dispositions == {
        SPAN_IDS[0]: Disposition.COVERED,
        SPAN_IDS[1]: Disposition.HUMAN_EXCLUDED,
        SPAN_IDS[2]: Disposition.UNRESOLVED,
        SPAN_IDS[3]: Disposition.SILENTLY_OMITTED,
    }
    assert set(ledger.spans.dispositions.values()) == set(Disposition)
    assert sum(ledger.spans.count(value) for value in Disposition) == len(SPAN_IDS)
    for span_id in SPAN_IDS:
        holders = [value for value in Disposition if span_id in ledger.spans.ids(value)]
        assert holders == [ledger.spans.dispositions[span_id]], f"{span_id} sits in {holders}"


def test_an_unresolved_declaration_beats_a_covering_claim_and_the_model_is_believed() -> None:
    """MUTATION PROOF FOR THE ORDER OF THE CHECKS. A claim's interval may bound a region the model
    then admitted it could not finish; counting that as covered would erase the admission."""
    ledger = _build(claims=(_claim(0, 3),), declared_unresolved_spans=frozenset({SPAN_IDS[2]}))
    assert ledger.spans.dispositions[SPAN_IDS[2]] is Disposition.UNRESOLVED


def test_a_resolved_reference_covers_the_span_it_lands_in_without_any_bounding_claim() -> None:
    """A weaker signal than an interval, recorded as covering only the characters it matched."""
    index = _index()
    outcome = index.resolve(MEMBER, "Legal Proceedings are described", node_id="n1")
    assert outcome.resolved, "the fixture quote must resolve for this test to mean anything"
    ledger = _build(claims=(), reference_outcomes=(outcome,))
    assert ledger.spans.dispositions[SPAN_IDS[2]] is Disposition.COVERED
    assert ledger.spans.dispositions[SPAN_IDS[0]] is Disposition.SILENTLY_OMITTED


def test_a_span_the_source_markup_itself_hides_is_excluded_without_a_reviewer() -> None:
    """An `ix:hidden` block exists to carry tagged facts that are never rendered. It is not
    human-readable disclosure, it is excluded on transport evidence alone, and it leaves the
    denominator."""
    ledger = _build(
        inventory=_inventory(
            spans=(_span(0), _span(1, hidden=HiddenReason.IX_HIDDEN)),
            tables=(_table_element(),),
            images=(_image_record(),),
        ),
        claims=(_claim(0, 0),),
    )
    assert ledger.spans.dispositions[SPAN_IDS[1]] is Disposition.HUMAN_EXCLUDED
    assert "the source's own markup hides it: IX_HIDDEN" in ledger.spans.reasons[SPAN_IDS[1]]
    assert ledger.coverage.spans_total == 1, "a hidden span is not part of the visible denominator"
    assert ledger.coverage.spans_human_excluded == 0
    assert ledger.coverage.spans_silently_omitted == 0


# --- the number the gate turns on -----------------------------------------------------------------


def test_covering_half_the_filing_reports_exactly_the_other_half_as_silently_omitted() -> None:
    """THE FIGURE THIS PACKAGE EXISTS TO PRODUCE, ON A DENOMINATOR OF FOUR.

    Two of four visible spans are bounded by the claim and two are never mentioned in any form.
    A reference rate over the same parse would report 100 percent, because the two lines the model
    said nothing about contributed nothing to count.
    """
    ledger = _build(claims=(_claim(0, 1),))
    assert ledger.coverage.spans_total == 4
    assert ledger.coverage.spans_covered == 2
    assert ledger.coverage.spans_unresolved == 0
    assert ledger.coverage.spans_human_excluded == 0
    assert ledger.coverage.spans_silently_omitted == 2
    assert ledger.coverage.spans_percent == 50.0
    assert ledger.spans.ids(Disposition.SILENTLY_OMITTED) == (SPAN_IDS[2], SPAN_IDS[3])
    assert any("2 visible source span(s)" in finding for finding in ledger.findings)


def test_the_tail_the_parse_never_reached_is_reported_as_a_gap_in_the_member() -> None:
    ledger = _build(claims=(_claim(0, 1),))
    (gap,) = ledger.gaps_by_member[MEMBER]
    assert gap.start == _bounds(1)[1]
    assert gap.end == len(SOURCE_TEXT)


def test_two_parts_claiming_one_paragraph_are_reported_and_never_deduplicated() -> None:
    ledger = _build(claims=(_claim(0, 1, part_id="part-a"), _claim(1, 3, part_id="part-b")))
    assert ledger.overlaps_by_member[MEMBER] == (Interval(_bounds(1)[0], _bounds(1)[1]),)
    assert ledger.coverage.intervals_overlapping == 1
    assert ledger.coverage.intervals_covered == 1, "the union is one interval; the overlap is extra"
    assert ledger.coverage.characters_covered <= ledger.coverage.characters_total


def test_a_ledger_built_against_another_filings_truth_is_refused() -> None:
    """A coverage figure computed against another filing's denominator is not approximately right.
    It is precisely, confidently wrong, which is the failure mode ADR-0016 was written about."""
    with pytest.raises(LedgerInputError, match="another filing's denominator"):
        _build(truth=_reviewed_truth_for_another_filing())


def _reviewed_truth_for_another_filing() -> BenchmarkTruth:
    return BenchmarkTruth.empty(
        cik="0000066740", accession="0000066740-96-000018", source_set_sha256="d" * 64
    )


def test_a_truth_document_naming_no_source_set_is_accepted_because_it_contradicts_nothing() -> None:
    """MUTATION PROOF FOR THE GUARD'S OWN CONDITION. A truth document with no hash makes no claim
    about which filing it describes, so there is nothing for the inventory to disagree with."""
    ledger = _build(truth=_reviewed_truth_for_no_particular_filing())
    assert ledger.source_set_sha256 == SOURCE_SHA


def _reviewed_truth_for_no_particular_filing() -> BenchmarkTruth:
    return BenchmarkTruth.empty(cik=CIK, accession=ACCESSION, source_set_sha256="")


# --- narrative is not a table ---------------------------------------------------------------------


def test_prose_about_a_table_does_not_discharge_the_table() -> None:
    """THE MOST IMPORTANT TEST IN THIS FILE.

    The parse here does everything Phase 2.1's candidates did and nothing more. It bounds the whole
    document with a claim whose anchors resolve. It cites the table's own figures, and every one of
    those references resolves in the preserved bytes. It emits no structured table.

    Every reference-based measurement calls that a success. It is not one. A number quoted in
    prose proves the number appears in the filing; it does not preserve which row, which column and
    which period it belonged to, and those three facts are what a table IS. The element is therefore
    SILENTLY_OMITTED, and the span carrying the same characters is COVERED at the same time — the
    two accountings are separate on purpose, because collapsing them is exactly how narrative
    repetition of a figure came to look like table coverage.
    """
    index = _index()
    citations = tuple(
        index.resolve(MEMBER, quote, node_id=f"n{position}")
        for position, quote in enumerate(("391,035", "383,285", "Net sales 391,035"))
    )
    assert all(outcome.resolved for outcome in citations), "the fixture citations must resolve"

    ledger = _build(claims=(_claim(0, 3),), reference_outcomes=citations, structured_tables=())

    assert ledger.spans.dispositions[SPAN_IDS[3]] is Disposition.COVERED
    assert ledger.tables.dispositions[TABLE_ID] is Disposition.SILENTLY_OMITTED
    assert "Silence is not coverage" in ledger.tables.reasons[TABLE_ID]
    assert ledger.table_state.elements_data_bearing == 1
    assert ledger.table_state.elements_accounted == 0
    assert ledger.table_state.elements_silently_omitted == 1
    assert ledger.table_state.structured_emitted == 0
    assert ledger.coverage.spans_silently_omitted == 0
    assert any("table element(s) are unaccounted for" in f for f in ledger.findings)
    assert _failed(_gate(ledger)) == (4,)


def test_a_structured_table_mapping_to_the_element_does_discharge_it() -> None:
    """MUTATION PROOF FOR THE TEST ABOVE. The element is reachable; prose is what failed to
    reach it."""
    ledger = _build(claims=(_claim(0, 3),))
    assert ledger.tables.dispositions[TABLE_ID] is Disposition.COVERED
    assert ledger.table_state.elements_accounted == 1
    assert ledger.table_state.data_bearing_percent == 100.0


def test_a_table_a_reviewer_called_layout_is_excluded_and_leaves_the_required_set() -> None:
    ledger = _build(
        truth=_reviewed_truth(("table", TABLE_ID, TableClassification.LAYOUT.value)),
        structured_tables=(),
    )
    assert ledger.tables.dispositions[TABLE_ID] is Disposition.HUMAN_EXCLUDED
    assert ledger.table_state.elements_data_bearing == 0
    assert ledger.table_state.elements_human_excluded == 1
    assert _failed(_gate(ledger)) == ()


def test_a_table_the_model_declared_unresolved_is_unresolved_rather_than_omitted() -> None:
    ledger = _build(structured_tables=(), declared_unresolved_tables=frozenset({TABLE_ID}))
    assert ledger.tables.dispositions[TABLE_ID] is Disposition.UNRESOLVED
    assert ledger.table_state.elements_unresolved == 1
    assert ledger.table_state.elements_silently_omitted == 0


def test_a_model_classification_of_layout_is_counted_and_never_applied() -> None:
    """The model's own word about its own table. Recorded beside the human's, never instead
    of it."""
    ledger = _build(structured_tables=(_structured_table(classification="LAYOUT scaffolding"),))
    assert ledger.table_state.model_classified_layout == 1
    assert ledger.table_state.model_classified_navigation == 0
    assert ledger.tables.dispositions[TABLE_ID] is Disposition.COVERED


# --- images ---------------------------------------------------------------------------------------


def test_a_text_only_parser_is_not_penalised_for_lacking_vision() -> None:
    """`not_analysed_text_only` is a count and not a failure. The parse simply does not claim image
    coverage, and separating those two statements is the whole reason this is not a boolean."""
    ledger = _build(image_references=frozenset(), model_accepts_images=False)
    assert ledger.images.dispositions[IMAGE] is Disposition.UNRESOLVED
    assert "text-only" in ledger.images.reasons[IMAGE]
    assert ledger.image_state.not_analysed_text_only == 1
    assert ledger.image_state.silently_omitted == 0
    assert _failed(_gate(ledger)) == ()


def test_an_image_a_multimodal_parser_was_given_and_never_mentioned_is_silently_omitted() -> None:
    ledger = _build(image_references=frozenset())
    assert ledger.images.dispositions[IMAGE] is Disposition.SILENTLY_OMITTED
    assert ledger.image_state.silently_omitted == 1
    assert ledger.image_state.submitted_to_parser == 1


def test_an_image_a_reviewer_called_a_logo_is_excluded() -> None:
    ledger = _build(
        truth=_reviewed_truth(("image", IMAGE, ImageClassification.LOGO.value)),
        image_references=frozenset(),
    )
    assert ledger.images.dispositions[IMAGE] is Disposition.HUMAN_EXCLUDED
    assert ledger.image_state.human_excluded == 1
    assert ledger.image_state.silently_omitted == 0


# --- members --------------------------------------------------------------------------------------


def test_a_member_whose_content_never_reaches_the_model_is_not_a_coverage_target() -> None:
    """A taxonomy schema is transport. Demanding coverage of it would make every filing incomplete
    forever, and the transport role is recorded as the reason so nobody has to guess later."""
    ledger = _build(
        inventory=_inventory(
            tables=(_table_element(),),
            images=(_image_record(),),
            members=(_text_member(), _image_member(), _transport_member()),
        )
    )
    assert ledger.members.dispositions["schema.xsd"] is Disposition.HUMAN_EXCLUDED
    assert "transport role TRANSPORT_ONLY" in ledger.members.reasons["schema.xsd"]
    assert ledger.coverage.members_total == 2
    assert _failed(_gate(ledger)) == ()


def test_a_member_carrying_no_visible_text_at_all_is_excluded_rather_than_omitted() -> None:
    ledger = _build(
        inventory=_inventory(
            spans=(),
            tables=(),
            images=(_image_record(),),
            members=(_text_member(), _image_member()),
        ),
        claims=(),
        structured_tables=(),
    )
    assert ledger.members.dispositions[MEMBER] is Disposition.HUMAN_EXCLUDED
    assert "no visible text span at all" in ledger.members.reasons[MEMBER]


def test_a_member_not_one_of_whose_spans_is_covered_is_silently_omitted() -> None:
    ledger = _build(claims=())
    assert ledger.members.dispositions[MEMBER] is Disposition.SILENTLY_OMITTED
    assert "not one visible span" in ledger.members.reasons[MEMBER]


# --- structured table validation ------------------------------------------------------------------


def _validate(
    table: StructuredTable, *, inventory: FilingInventory | None = None
) -> TableValidation:
    return validate_table(
        table,
        inventory=_inventory(tables=(_table_element(),)) if inventory is None else inventory,
        submitted_members=frozenset({MEMBER}),
        known_table_ids=frozenset({table.table_id}),
    )


def test_a_structured_table_drawn_from_its_source_element_passes() -> None:
    result = _validate(_structured_table())
    assert result.passes is True
    assert result.source_resolved is True
    assert result.cells_total == 4
    assert result.cells_text_found == 4
    assert result.cells_text_missing == 0
    assert result.numeric_cells == 3, "three figures and one row label"
    assert result.numeric_cells_found == 3
    assert result.grid_collisions == 0
    assert result.findings == ()


def test_a_structured_table_naming_no_such_element_fails_with_source_unresolved() -> None:
    result = _validate(_structured_table(source_table_id=f"{MEMBER}#t99"))
    assert result.source_resolved is False
    assert result.passes is False
    assert any("names no table element" in finding for finding in result.findings)


def test_a_structured_table_naming_no_source_element_at_all_cannot_discharge_one() -> None:
    result = _validate(_structured_table(source_table_id=""))
    assert result.source_resolved is False
    assert any("cannot discharge that element's coverage" in f for f in result.findings)


def test_a_cell_that_is_nowhere_in_the_source_is_counted_missing_and_fails_the_table() -> None:
    """A cell neither in the source nor declared unresolved is a cell the model supplied from
    somewhere other than this filing. It is the one thing this validator refuses outright."""
    table = _structured_table(rows=[[{"text": "Net sales"}, {"text": "999,999"}]])
    result = _validate(table)
    assert result.cells_text_missing == 1
    assert result.cells_text_found == 1
    assert result.passes is False
    assert any("somewhere other than this filing" in f for f in result.findings)


def test_a_cell_the_model_declared_unresolved_is_exposed_and_does_not_fail_the_table() -> None:
    """An unresolved cell is a PASS. A model that says a cell is illegible in the source has done
    the right thing, and the gate counts it as exposed rather than as broken."""
    table = _structured_table(
        rows=[[{"text": "Net sales"}, {"text": "", "unresolved": True}]],
    )
    result = _validate(table)
    assert result.cells_unresolved == 1
    assert result.cells_text_missing == 0
    assert result.passes is True


def test_a_cell_with_no_text_at_all_is_neither_found_nor_fabricated() -> None:
    """A blank cell at a blank grid position says nothing false about the filing. Counting it
    missing would accuse a model of inventing an emptiness, and the accusation this validator
    makes is a serious one."""
    result = _validate(_structured_table(rows=[[{"text": "Net sales"}, {"text": ""}]]))
    assert result.cells_total == 2
    assert result.cells_text_found == 1
    assert result.cells_text_missing == 0
    assert result.cells_unresolved == 0
    assert result.passes is True


def test_two_cells_at_one_grid_position_after_spans_are_applied_is_a_collision() -> None:
    """The spans are what make this invisible by eye: both cells declare a different column and the
    first one's width puts them on top of each other anyway."""
    table = _structured_table(
        rows=[
            [
                {"row": 0, "column": 0, "column_span": 2, "text": "Net sales"},
                {"row": 0, "column": 1, "text": "391,035"},
            ]
        ]
    )
    result = _validate(table)
    assert result.grid_collisions == 1
    assert result.passes is False
    assert any("claimed by more than one cell" in f for f in result.findings)


def test_a_row_span_collides_down_the_grid_as_well_as_across_it() -> None:
    table = _structured_table(
        rows=[
            [
                {"row": 0, "column": 0, "row_span": 2, "text": "Net sales"},
                {"row": 1, "column": 0, "text": "391,035"},
            ]
        ]
    )
    assert _validate(table).grid_collisions == 1


def test_two_tables_answering_to_one_identifier_both_record_a_collision() -> None:
    """A duplicated identifier is a failure of the PARSE, not of one table: two tables answering to
    one name cannot both be cited, reviewed or superseded, and neither is the wrong one."""
    results = validate_tables(
        (_structured_table(), _structured_table(rows=[[{"text": "391,035"}]])),
        inventory=_inventory(tables=(_table_element(),)),
        submitted_members=frozenset({MEMBER}),
    )
    assert len(results) == 2
    assert all(result.grid_collisions == 1 for result in results)
    assert all(result.passes is False for result in results)
    assert all(any("more than one table" in f for f in r.findings) for r in results)


def test_two_tables_with_distinct_identifiers_are_left_alone() -> None:
    """MUTATION PROOF. The uniqueness sweep must not add a collision to every multi-table parse."""
    results = validate_tables(
        (_structured_table(), _structured_table(table_id="a second table")),
        inventory=_inventory(tables=(_table_element(),)),
        submitted_members=frozenset({MEMBER}),
    )
    assert [result.grid_collisions for result in results] == [0, 0]
    assert all(result.passes for result in results)


def test_a_source_member_nobody_submitted_is_a_finding() -> None:
    result = _validate(_structured_table(source_member="a-file-nobody-sent.htm"))
    assert any("was not submitted to the model" in f for f in result.findings)


def test_a_source_member_disagreeing_with_the_inventory_is_a_finding() -> None:
    inventory = _inventory(tables=(_table_element(),), members=(_text_member(), _image_member()))
    result = validate_table(
        _structured_table(source_member=IMAGE),
        inventory=inventory,
        submitted_members=frozenset({MEMBER, IMAGE}),
        known_table_ids=frozenset(),
    )
    assert any("disagrees with the inventory" in f for f in result.findings)


def test_a_continuation_link_naming_no_table_in_this_parse_is_a_finding() -> None:
    result = _validate(_structured_table(continues_table_id="a table from another parse"))
    assert any("names no table in this parse" in f for f in result.findings)


def test_an_anchor_that_quotes_a_caption_outside_the_element_is_a_finding_not_a_refusal() -> None:
    """A table's caption legitimately sits outside the `table` element, so this cannot be fatal."""
    result = _validate(_structured_table(source_anchor_start="Consolidated Statements of Sales"))
    assert result.passes is True
    assert any("source_anchor_start does not occur" in f for f in result.findings)


def test_the_normalised_value_a_model_offers_is_never_checked_against_anything() -> None:
    """`1,234` may be honestly offered as `1234`, or as `1234000000` after a scale the table
    declares. Deciding which is right means reading the table's own scale note, and reading a
    scale note is interpretation."""
    table = _structured_table(
        rows=[[{"text": "391,035", "value": "391035000000", "unit": "a unit of its own devising"}]]
    )
    result = _validate(table)
    assert result.passes is True
    assert result.findings == ()


def test_a_validation_reports_itself_completely_in_its_mapping() -> None:
    document = _validate(_structured_table()).to_mapping()
    assert document["passes"] is True
    assert document["source_table_id"] == TABLE_ID
    assert document["cells_total"] == 4
    assert document["findings"] == []


def test_table_source_interval_locates_a_real_element_and_refuses_to_invent_one() -> None:
    inventory = _inventory(tables=(_table_element(),))
    assert table_source_interval(TABLE_ID, inventory) == Interval(*_bounds(3))
    assert table_source_interval(f"{MEMBER}#t99", inventory) is None


# --- the gate -------------------------------------------------------------------------------------


def test_all_fourteen_conditions_are_reported_separately() -> None:
    """A weighted score would let a strong showing on twelve dimensions outvote a silently omitted
    financial statement. These are conjunctive, and each is reported with its own evidence."""
    result = _gate(_build())
    assert tuple(condition.number for condition in result.conditions) == tuple(range(1, 15))
    assert len({condition.name for condition in result.conditions}) == 14
    assert all(condition.detail for condition in result.conditions)
    assert result.to_mapping()["conditions_total"] == 14
    assert result.to_mapping()["conditions_passed"] == 14


def test_a_parse_that_accounts_for_every_item_is_a_mechanical_completeness_candidate() -> None:
    result = _gate(_build())
    assert result.is_candidate is True
    assert result.failed == ()
    assert result.status == "MECHANICAL_COMPLETENESS_CANDIDATE"


def test_the_gate_says_in_its_own_mapping_that_passing_is_not_completeness() -> None:
    """It means the result carries enough evidence to undergo human review. It will be misread as
    a score by anyone who has not read this sentence, which is why the sentence ships attached to
    the data rather than in a document beside it."""
    meaning = _gate(_build()).to_mapping()["meaning"]
    assert "NOT a claim that the parse is complete" in meaning
    assert "HUMAN_APPROVED_COMPLETE_FOR_THIS_FILING" in meaning


@pytest.mark.parametrize(
    ("mutation", "expected"),
    [
        pytest.param(
            {"structured_tables_failing_validation": 1}, (5,), id="a-table-fails-validation"
        ),
        pytest.param({"unparseable_effective_artifacts": 1}, (7,), id="an-unreadable-artifact"),
        pytest.param(
            {"serialization": SerializationState.UNPARSEABLE}, (7,), id="unparseable-serialization"
        ),
        pytest.param({"nonterminal_required_jobs": 1}, (8,), id="a-job-still-running"),
        pytest.param(
            {"transport": TransportState.NOT_RUN}, (8,), id="transport-never-reached-a-provider"
        ),
        pytest.param(
            {"transport": TransportState.CREDENTIAL_BLOCKED},
            (8,),
            id="transport-credential-blocked",
        ),
        pytest.param(
            {"transport": TransportState.INCOMPATIBLE}, (8,), id="transport-incompatible-pairing"
        ),
        pytest.param(
            {"transport": TransportState.PROVIDER_FAILED}, (8,), id="transport-provider-failed"
        ),
        pytest.param(
            {"truncations_without_replacement": 1}, (9,), id="a-truncation-nobody-replanned"
        ),
        pytest.param(
            {"reconciliation_created_new_work": True}, (10,), id="reconciliation-still-moving"
        ),
        pytest.param(
            {"convergence": ConvergenceState.INTERRUPTED}, (10,), id="convergence-interrupted"
        ),
        pytest.param({"convergence": ConvergenceState.NOT_RUN}, (10,), id="convergence-never-ran"),
        pytest.param({"repeated_gap_fingerprints": 1}, (11,), id="a-gap-requested-twice"),
        pytest.param({"unsettled_reservations": 1}, (12,), id="an-unsettled-reservation"),
        pytest.param(
            {"human_readiness": HumanReadiness.HUMAN_REJECTED_COMPLETENESS},
            (14,),
            id="a-reviewer-rejected-it",
        ),
    ],
)
def test_flipping_one_gate_input_fails_exactly_the_conditions_it_should(
    mutation: dict[str, Any], expected: tuple[int, ...]
) -> None:
    """MUTATION PROOF FOR THE WHOLE GATE. Every condition is necessary and none is redundant: each
    row below moves one input and exactly the named condition changes its verdict."""
    result = _gate(_build(), **mutation)
    assert _failed(result) == expected
    assert result.is_candidate is False
    assert result.status == "NOT_A_MECHANICAL_COMPLETENESS_CANDIDATE"


@pytest.mark.parametrize(
    ("mutation", "expected"),
    [
        pytest.param({"structured_tables": ()}, (4,), id="a-data-bearing-element-nothing-maps-to"),
        pytest.param({"claims": (_claim(0, 1),)}, (2, 3), id="half-the-filing-never-claimed"),
        pytest.param({"image_references": frozenset()}, (1, 3, 6), id="an-image-nobody-referenced"),
        pytest.param({"claims": (_reversed_claim(),)}, (1, 2, 3), id="a-claim-that-bounds-nothing"),
        pytest.param({"claims": ()}, (1, 2, 3), id="a-parse-that-claimed-nothing"),
    ],
)
def test_flipping_one_ledger_input_fails_exactly_the_conditions_it_should(
    mutation: dict[str, Any], expected: tuple[int, ...]
) -> None:
    """The coverage conditions, moved one at a time from the parse side rather than the run side.

    An unreferenced image fails three conditions rather than one, and that is the design: it is an
    unaccounted image AND an unaccounted member AND a silent omission, and a reviewer reading only
    condition 6 would not learn that a whole member of the submission went unmentioned.
    """
    result = _gate(_build(**mutation))
    assert _failed(result) == expected


def test_an_incompatible_pairing_fails_condition_eight_and_the_detail_names_the_state() -> None:
    """INCOMPATIBLE is a RESULT under INTACT_SOURCE_ONLY, not a defect: nothing was truncated,
    sliced or swapped to another model. It is folded into condition 8's evidence rather than given
    a condition of its own, so that it cannot look like a distinct kind of failure."""
    result = _gate(_build(), transport=TransportState.INCOMPATIBLE)
    (failed,) = result.failed
    assert failed.number == 8
    assert "transport state INCOMPATIBLE" in failed.detail
    assert failed.name == "no scheduled required job remains nonterminal"


def test_condition_thirteen_shows_unresolved_items_rather_than_judging_them() -> None:
    """It passes unconditionally by design. Unresolved work is disclosed, and disclosure is the
    requirement: a condition that failed on unresolved items would pressure a model into
    guessing, which is the defect the whole unresolved vocabulary exists to prevent."""
    ledger = _build(
        claims=(_claim(0, 3),),
        declared_unresolved_spans=frozenset({SPAN_IDS[2]}),
        declared_unresolved_tables=frozenset({TABLE_ID}),
        structured_tables=(),
    )
    condition = _gate(ledger).conditions[12]
    assert condition.number == 13
    assert condition.passed is True
    assert "1 span(s), 1 table(s)" in condition.detail


def test_the_gate_names_the_members_it_could_not_account_for() -> None:
    result = _gate(_build(image_references=frozenset()))
    (condition,) = [c for c in result.conditions if c.number == 1]
    assert IMAGE in condition.detail


# --- the ledger as a record -----------------------------------------------------------------------


def test_the_ledger_mapping_states_that_nothing_in_it_is_a_completeness_verdict() -> None:
    document = _build(claims=(_claim(0, 1),)).to_mapping()
    assert document["schema_version"] == "completeness-ledger-v1"
    assert "Nothing here is a completeness verdict" in document["verdict_note"]
    assert document["cik"] == CIK
    assert document["accession"] == ACCESSION
    assert document["source_set_sha256"] == SOURCE_SHA
    assert document["span_ledger"]["counts"][Disposition.SILENTLY_OMITTED.value] == 2
    assert document["span_ledger"]["silently_omitted"] == [SPAN_IDS[2], SPAN_IDS[3]]
    assert document["gaps"][MEMBER][0]["start"] == _bounds(1)[1]


def test_the_ledger_records_the_truth_version_its_numbers_were_computed_against() -> None:
    truth = _reviewed_truth()
    ledger = _build(truth=truth)
    assert ledger.truth_version == truth.version


def test_an_unreviewed_inventory_is_reported_as_provisional_rather_than_scored() -> None:
    """An item nobody has classified is neither excused nor demanded. It blocks, and the ledger says
    so in words, because a percentage over an unreviewed denominator reads as a measurement."""
    ledger = _build(truth=_truth())
    assert any("carry no human classification yet" in f for f in ledger.findings)
    assert any("no span has been classified MATERIAL_FILING_CONTENT" in f for f in ledger.findings)


# --- the status dimensions ------------------------------------------------------------------------


def test_spans_silently_omitted_never_goes_negative() -> None:
    """It is a subtraction over four independently derived counts. A negative would print as a
    negative in every report that consumes it, and no reader would know which count was wrong."""
    state = SourceCoverageState(
        members_total=1,
        members_accounted=1,
        spans_total=3,
        spans_covered=3,
        spans_unresolved=2,
        spans_human_excluded=1,
        characters_total=100,
        characters_covered=100,
        intervals_covered=1,
        intervals_overlapping=0,
    )
    assert state.spans_silently_omitted == 0


def test_table_elements_silently_omitted_never_goes_negative() -> None:
    state = TableState(
        elements_total=1,
        elements_data_bearing=1,
        elements_accounted=1,
        elements_human_excluded=1,
        elements_unresolved=1,
        structured_emitted=1,
        structured_source_resolved=1,
        structured_failing_validation=0,
        cells_unresolved=0,
        model_classified_layout=0,
        model_classified_navigation=0,
    )
    assert state.elements_silently_omitted == 0


def test_images_silently_omitted_never_goes_negative() -> None:
    state = ImageState(
        images_total=1,
        submitted_to_parser=1,
        referenced_by_model=1,
        human_excluded=1,
        unresolved=1,
        not_analysed_text_only=1,
    )
    assert state.accounted == 4
    assert state.silently_omitted == 0


def test_every_percentage_is_zero_when_its_denominator_is_zero() -> None:
    """A filing with no visible span is not 100 percent covered, and it is not a division error
    either. Zero is the only honest answer, and it is reported beside the counts that produced
    it."""
    empty = SourceCoverageState(
        members_total=0,
        members_accounted=0,
        spans_total=0,
        spans_covered=0,
        spans_unresolved=0,
        spans_human_excluded=0,
        characters_total=0,
        characters_covered=0,
        intervals_covered=0,
        intervals_overlapping=0,
    )
    assert empty.members_percent == 0.0
    assert empty.spans_percent == 0.0
    assert empty.characters_percent == 0.0
    assert empty.to_mapping()["spans_silently_omitted"] == 0

    no_tables = TableState(
        elements_total=0,
        elements_data_bearing=0,
        elements_accounted=0,
        elements_human_excluded=0,
        elements_unresolved=0,
        structured_emitted=0,
        structured_source_resolved=0,
        structured_failing_validation=0,
        cells_unresolved=0,
        model_classified_layout=0,
        model_classified_navigation=0,
    )
    assert no_tables.data_bearing_percent == 0.0


def test_a_table_state_mapping_says_what_elements_total_does_not_assert() -> None:
    """`elements_total` counts `table` elements in the bytes. It is not a claim that all of them
    carry data — a ledger that treated all 41 of Apple's as required would report every parse as
    incomplete forever."""
    note = _build().table_state.to_mapping()["note"]
    assert "asserts nothing about which of them carry data" in note
