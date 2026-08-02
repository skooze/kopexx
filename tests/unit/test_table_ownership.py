"""Table ownership: which canonical footnote owns each parsed table.

Ownership is not tidiness. Sprint 5 summarizes one footnote per job and validates every number in
the summary against THAT footnote's tables. A filing-level table pool cannot distinguish a value
in this note from one in another note, from a statement, or from an excluded Item 408 disclosure.
"""

from __future__ import annotations

import pytest

from packages.footnote_canonicalizer import (
    CANONICAL_FOOTNOTE,
    EXCLUDED_FILING_SECTION,
    FINANCIAL_STATEMENT,
    OTHER_FILING_REPORT,
    UNRESOLVED,
    ExclusionList,
    canonicalize,
    classify_tables,
)
from packages.footnote_extractor import RendererReport, ReportInventory
from packages.footnote_extractor.presentation import (
    PresentationLinkbase,
    PresentationLinkbaseError,
    RolePresentation,
    parse_presentation,
)
from packages.footnote_extractor.tagged_blocks import (
    TaggedSpan,
    find_tagged_spans,
    innermost_span_at,
    resolve_continuations,
    text_block_spans,
)

DEBT = "http://x/role/Debt"
DEBT_TABLES = "http://x/role/DebtTables"
LEASES = "http://x/role/Leases"
INSIDER = "http://xbrl.sec.gov/ecd/role/InsiderTrading"
STATEMENT = "http://x/role/ConsolidatedBalanceSheet"


class FakeTable:
    """The two attributes ownership uses. Avoids depending on the table parser here."""

    def __init__(self, external_id: str, offset: int | None, raw: str = "") -> None:
        self.external_id = external_id
        self.source_offset = offset
        self.raw_html = raw


def report(position: int, category: str, name: str, role: str | None) -> RendererReport:
    return RendererReport(
        position=position,
        menu_category=category,
        short_name=name,
        long_name=name,
        role=role,
        html_file_name=None,
        xml_file_name=None,
        report_type="Sheet",
    )


@pytest.fixture(scope="module")
def result():
    reports = [
        report(1, "Notes", "Debt", DEBT),
        report(2, "Notes", "Leases", LEASES),
        report(3, "Notes", "Insider Trading Arrangements", INSIDER),
        report(4, "Tables", "Debt Tables", DEBT_TABLES),
        report(5, "Statements", "Balance Sheet", STATEMENT),
    ]
    return canonicalize(
        accession="X",
        inventory=ReportInventory(tuple(reports), "0" * 64, "synthetic"),
        headings=(),
        exclusions=ExclusionList.load(),
    )


@pytest.fixture
def linkbase() -> PresentationLinkbase:
    return PresentationLinkbase(
        roles={
            DEBT: RolePresentation(DEBT, ("us-gaap:DebtDisclosureTextBlock",)),
            DEBT_TABLES: RolePresentation(DEBT_TABLES, ("us-gaap:ScheduleOfDebtTextBlock",)),
            LEASES: RolePresentation(LEASES, ("us-gaap:LeasesTextBlock",)),
            INSIDER: RolePresentation(INSIDER, ("ecd:InsiderTradingArrTextBlock",)),
            STATEMENT: RolePresentation(STATEMENT, ("us-gaap:Assets",)),
        }
    )


def span(concept: str, start: int, end: int) -> TaggedSpan:
    return TaggedSpan(concept=concept, start=start, end=end, tag="ix:nonnumeric")


# --- the tagged span reader ----------------------------------------------------------------------


def test_a_tagged_element_yields_its_own_byte_range() -> None:
    raw = 'aa<ix:nonNumeric name="us-gaap:DebtDisclosureTextBlock">body</ix:nonNumeric>zz'
    spans = text_block_spans(raw)
    assert len(spans) == 1
    assert spans[0].concept == "us-gaap:DebtDisclosureTextBlock"
    assert raw[spans[0].start : spans[0].end].startswith("<ix:nonNumeric")


def test_nested_spans_each_keep_their_own_range() -> None:
    raw = (
        '<ix:nonNumeric name="outer:ATextBlock">'
        '<ix:nonNumeric name="inner:BTextBlock">x</ix:nonNumeric>'
        "</ix:nonNumeric>"
    )
    spans = text_block_spans(raw)
    assert {s.concept for s in spans} == {"outer:ATextBlock", "inner:BTextBlock"}
    outer = next(s for s in spans if s.concept.startswith("outer"))
    inner = next(s for s in spans if s.concept.startswith("inner"))
    assert outer.start < inner.start and inner.end < outer.end


def test_the_innermost_span_wins() -> None:
    """A table inside a schedule inside a note belongs to the schedule, the more specific answer."""
    spans = [span("outer:ATextBlock", 0, 100), span("inner:BTextBlock", 40, 60)]
    assert innermost_span_at(spans, 50).concept == "inner:BTextBlock"
    assert innermost_span_at(spans, 10).concept == "outer:ATextBlock"
    assert innermost_span_at(spans, 200) is None


def test_a_continuation_inherits_the_concept_that_declared_it() -> None:
    """THE DEFECT THIS PREVENTS.

    A long note's content is split with `continuedAt`, and its tables often live in the
    continuation rather than inside the declaring element. Ignoring continuations classified the
    debt maturity schedule, the commercial-paper table, and the purchase-obligation table as
    unowned filing furniture — a false negative that silently narrows what Sprint 5 can validate.
    """
    raw = (
        '<ix:nonNumeric name="us-gaap:DebtDisclosureTextBlock" continuedAt="c1">a</ix:nonNumeric>'
        'MIDDLE<ix:continuation id="c1">the maturity table</ix:continuation>'
    )
    spans = text_block_spans(raw)
    assert len(spans) == 2
    assert all(s.concept == "us-gaap:DebtDisclosureTextBlock" for s in spans)
    assert any(s.is_continuation for s in spans)


def test_a_continuation_chain_is_followed_transitively() -> None:
    raw = (
        '<ix:nonNumeric name="a:XTextBlock" continuedAt="c1">a</ix:nonNumeric>'
        '<ix:continuation id="c1" continuedAt="c2">b</ix:continuation>'
        '<ix:continuation id="c2">c</ix:continuation>'
    )
    assert len(text_block_spans(raw)) == 3


def test_a_continuation_cycle_terminates() -> None:
    """Malformed markup is a filing defect, not a reason to hang."""
    raw = (
        '<ix:nonNumeric name="a:XTextBlock" continuedAt="c1">a</ix:nonNumeric>'
        '<ix:continuation id="c1" continuedAt="c2">b</ix:continuation>'
        '<ix:continuation id="c2" continuedAt="c1">c</ix:continuation>'
    )
    assert len(text_block_spans(raw)) <= 4


def test_a_dangling_continuation_reference_is_survivable() -> None:
    raw = '<ix:nonNumeric name="a:XTextBlock" continuedAt="missing">a</ix:nonNumeric>'
    assert len(text_block_spans(raw)) == 1


def test_resolve_continuations_is_a_no_op_without_any() -> None:
    spans = [span("a:XTextBlock", 0, 10)]
    assert resolve_continuations(spans) == spans


def test_a_self_closing_fact_opens_no_span() -> None:
    assert find_tagged_spans('<ix:nonFraction name="a:B" />') == []


# --- the presentation linkbase --------------------------------------------------------------------


def test_the_linkbase_indexes_concepts_to_roles(linkbase) -> None:
    index = linkbase.concept_to_roles()
    assert index["us-gaap:DebtDisclosureTextBlock"] == [DEBT]


def test_concept_names_normalize_between_linkbase_and_document() -> None:
    """The linkbase writes `us-gaap_X`; the document writes `us-gaap:X`. Unnormalized they never
    match, and every table would be unownable."""
    parsed = parse_presentation(
        b'<linkbase xmlns="http://www.xbrl.org/2003/linkbase" '
        b'xmlns:xlink="http://www.w3.org/1999/xlink">'
        b'<presentationLink xlink:role="http://x/role/Debt">'
        b'<loc xlink:href="a.xsd#us-gaap_DebtDisclosureTextBlock" xlink:label="l"/>'
        b"</presentationLink></linkbase>"
    )
    assert "us-gaap:DebtDisclosureTextBlock" in parsed.concept_to_roles()


def test_an_empty_linkbase_raises_rather_than_returning_nothing() -> None:
    with pytest.raises(PresentationLinkbaseError, match="no roles"):
        parse_presentation(b'<linkbase xmlns="http://www.xbrl.org/2003/linkbase"/>')


def test_an_unparseable_linkbase_raises() -> None:
    with pytest.raises(PresentationLinkbaseError, match="not parseable"):
        parse_presentation(b"<linkbase")


# --- classification ---------------------------------------------------------------------------------


def classify(result, linkbase, tables, spans, **kwargs):
    return classify_tables(result, tables, spans, linkbase, **kwargs)


def test_a_table_in_a_note_block_is_owned_by_that_note(result, linkbase) -> None:
    rec = classify(
        result,
        linkbase,
        [FakeTable("T1", 50)],
        [span("us-gaap:DebtDisclosureTextBlock", 0, 100)],
    )
    owner = rec.ownership[0]
    assert owner.classification == CANONICAL_FOOTNOTE
    assert owner.owner_role_uri == DEBT
    assert owner.owner_title == "Debt"
    assert owner.method and owner.reason


def test_a_table_in_a_child_block_inherits_the_audited_parent_attachment(result, linkbase) -> None:
    """Ownership reuses the stage-3 decision rather than deriving a second one that could differ."""
    rec = classify(
        result, linkbase, [FakeTable("T1", 50)], [span("us-gaap:ScheduleOfDebtTextBlock", 0, 100)]
    )
    assert rec.ownership[0].classification == CANONICAL_FOOTNOTE
    assert rec.ownership[0].owner_role_uri == DEBT
    assert "already attached" in rec.ownership[0].reason


def test_an_excluded_item_disclosure_table_is_not_a_footnote_table(result, linkbase) -> None:
    rec = classify(
        result, linkbase, [FakeTable("T1", 50)], [span("ecd:InsiderTradingArrTextBlock", 0, 100)]
    )
    assert rec.ownership[0].classification == EXCLUDED_FILING_SECTION
    assert rec.ownership[0].owner_role_uri is None


def test_a_statement_table_is_not_assigned_to_a_note(result, linkbase) -> None:
    """A statement is tagged fact-by-fact, so it has no containing narrative block.

    Its numeric facts are what identify it, not its position relative to a note.
    """
    rec = classify(
        result,
        linkbase,
        [FakeTable("T1", 50, raw="<table>x</table>")],
        [],
        statement_roles={STATEMENT},
        numeric_spans=[TaggedSpan("us-gaap:Assets", 55, 60, "ix:nonfraction")],
    )
    assert rec.ownership[0].classification == FINANCIAL_STATEMENT
    assert rec.ownership[0].owner_role_uri is None


def test_filing_furniture_is_other_not_unresolved(result, linkbase) -> None:
    """A cover layout table is not a defect. Only a table that SHOULD have an owner is."""
    rec = classify(result, linkbase, [FakeTable("T1", 50, raw="<table/>")], [])
    assert rec.ownership[0].classification == OTHER_FILING_REPORT
    assert not rec.has_unresolved_footnote_tables


def test_a_concept_in_two_footnote_roles_fails_closed(result) -> None:
    """A ROLE COLLISION IS NOT BROKEN SILENTLY."""
    ambiguous = PresentationLinkbase(
        roles={
            DEBT: RolePresentation(DEBT, ("shared:XTextBlock",)),
            LEASES: RolePresentation(LEASES, ("shared:XTextBlock",)),
        }
    )
    rec = classify(result, ambiguous, [FakeTable("T1", 50)], [span("shared:XTextBlock", 0, 100)])
    assert rec.ownership[0].classification == UNRESOLVED
    assert "not " in rec.ownership[0].reason
    assert len(rec.ownership[0].candidate_roles) == 2


def test_a_concept_in_no_role_is_unresolved(result, linkbase) -> None:
    rec = classify(result, linkbase, [FakeTable("T1", 50)], [span("unknown:ZTextBlock", 0, 100)])
    assert rec.ownership[0].classification == UNRESOLVED
    assert rec.has_unresolved_footnote_tables


def test_a_table_with_no_offset_is_unresolved(result, linkbase) -> None:
    rec = classify(result, linkbase, [FakeTable("T1", None)], [])
    assert rec.ownership[0].classification == UNRESOLVED


def test_duplicate_titles_do_not_cross_assign(result) -> None:
    """Ownership is by role URI and concept, never by title, so two notes named alike cannot
    steal each other's tables."""
    linkbase = PresentationLinkbase(
        roles={
            DEBT: RolePresentation(DEBT, ("a:OneTextBlock",)),
            LEASES: RolePresentation(LEASES, ("a:TwoTextBlock",)),
        }
    )
    rec = classify(
        result,
        linkbase,
        [FakeTable("T1", 10), FakeTable("T2", 210)],
        [span("a:OneTextBlock", 0, 100), span("a:TwoTextBlock", 200, 300)],
    )
    assert rec.ownership[0].owner_role_uri == DEBT
    assert rec.ownership[1].owner_role_uri == LEASES


def test_every_table_receives_exactly_one_classification(result, linkbase) -> None:
    rec = classify(
        result,
        linkbase,
        [FakeTable("T1", 50), FakeTable("T2", 150, raw="<table/>"), FakeTable("T3", None)],
        [span("us-gaap:DebtDisclosureTextBlock", 0, 100)],
    )
    assert rec.total == 3
    assert (
        rec.count(CANONICAL_FOOTNOTE)
        + rec.count(EXCLUDED_FILING_SECTION)
        + rec.count(FINANCIAL_STATEMENT)
        + rec.count(OTHER_FILING_REPORT)
        + rec.count(UNRESOLVED)
        == 3
    )


def test_the_census_record_totals_correctly(result, linkbase) -> None:
    rec = classify(
        result, linkbase, [FakeTable("T1", 50)], [span("us-gaap:DebtDisclosureTextBlock", 0, 100)]
    )
    record = rec.as_record()
    assert record["total"] == 1 and record["canonical_footnote"] == 1
