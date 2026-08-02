"""Canonicalization stages 1 through 5, exclusions, audit, and completeness.

The fixture-level regression test at the end is the one that guards the product thesis: 13
canonical footnotes, 46 attached, zero orphans, three exclusions. Its mutation proofs live in
`test_footnote_regression.py`.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from packages.footnote_canonicalizer import (
    COMPLETE,
    FAILED,
    MISMATCH,
    NOT_ATTEMPTED,
    PARTIAL,
    RECONCILED,
    REQUIRES_REVIEW,
    ExclusionDefinitionError,
    ExclusionList,
    apply_exclusions,
    attach_by_role_uri,
    canonicalize,
    discover_candidates,
    evaluate,
    filing_footnote_status,
    match_headings_to_footnotes,
    reconcile_against_headings,
    reconcile_against_toc,
    reconciliation_report,
)
from packages.footnote_extractor import NoteHeading, RendererReport, read_inventory

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "filings"
TEN_K = FIXTURES / "0000320193-25-000079" / "filing-summary.xml"


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
def exclusions() -> ExclusionList:
    return ExclusionList.load()


@pytest.fixture(scope="module")
def ten_k(exclusions):
    inventory = read_inventory(TEN_K)
    headings = tuple(
        NoteHeading(number=i, title=f"Note {i}", line_index=i, joined_from_next_line=True)
        for i in range(1, 14)
    )
    return canonicalize(
        accession="0000320193-25-000079",
        inventory=inventory,
        headings=headings,
        exclusions=exclusions,
    )


# --- the exclusion definition ------------------------------------------------------------------


def test_the_definition_loads_and_validates(exclusions) -> None:
    assert exclusions.version == "1.0.0"


def test_a_missing_definition_raises(tmp_path: Path) -> None:
    with pytest.raises(ExclusionDefinitionError, match="not found"):
        ExclusionList.load(tmp_path / "absent.yaml")


def test_a_definition_missing_required_keys_raises(tmp_path: Path) -> None:
    partial = tmp_path / "x.yaml"
    partial.write_text("version: '1.0.0'\n", encoding="utf-8")
    with pytest.raises(ExclusionDefinitionError, match="missing"):
        ExclusionList.load(partial)


def test_item_408_insider_trading_is_excluded_by_namespace(exclusions) -> None:
    verdict = exclusions.classify(
        title="Insider Trading Arrangements",
        role_uri="http://xbrl.sec.gov/ecd/role/InsiderTradingArrangements",
    )
    assert verdict.is_excluded and verdict.item == "Item 408"
    assert verdict.rule == "excluded_namespace"


def test_item_1c_cybersecurity_is_excluded_by_namespace(exclusions) -> None:
    verdict = exclusions.classify(
        title="Cybersecurity Risk Management and Strategy Disclosure",
        role_uri="http://xbrl.sec.gov/cyd/role/CybersecurityRiskManagementAndStrategyDisclosure",
    )
    assert verdict.is_excluded and verdict.item == "Item 1C"


def test_a_real_footnote_is_not_excluded(exclusions) -> None:
    verdict = exclusions.classify(title="Debt", role_uri="http://www.apple.com/role/Debt")
    assert not verdict.is_excluded and not verdict.needs_review


def test_a_namespace_prefix_is_matched_as_a_path_segment_not_a_substring(exclusions) -> None:
    """`/ecd/` rather than `ecd`, or a role mentioning `recorded` would be excluded as Item 408."""
    verdict = exclusions.classify(
        title="Recorded Investments", role_uri="http://www.apple.com/role/RecordedInvestments"
    )
    assert not verdict.is_excluded


def test_an_unrecognised_sec_namespace_is_flagged_not_guessed(exclusions) -> None:
    """Silently including inflates the count; silently excluding drops a real footnote.

    Neither is acceptable, so an unknown SEC-hosted taxonomy stops the filing for a human.
    """
    verdict = exclusions.classify(
        title="Some Future Mandate",
        role_uri="http://xbrl.sec.gov/newmandate/role/SomeFutureMandate",
    )
    assert verdict.needs_review
    assert verdict.rule == "unknown_namespace_policy"


def test_an_issuer_extension_role_is_treated_as_a_footnote(exclusions) -> None:
    """91.4 percent of distinct tags are extensions. Flagging them all would stop every filing."""
    verdict = exclusions.classify(title="Leases", role_uri="http://www.someissuer.com/role/Leases")
    assert not verdict.needs_review and not verdict.is_excluded


def test_the_verdict_records_why(exclusions) -> None:
    """A reviewer must be able to answer "why is this not a footnote" without a rerun."""
    verdict = exclusions.classify(
        title="Insider Trading Arrangements", role_uri="http://xbrl.sec.gov/ecd/role/X"
    )
    evidence = verdict.as_evidence()
    assert evidence["decision"] == "excluded"
    assert evidence["rule"] and evidence["item"] and evidence["matched_on"]


# --- stage 3: role-URI attachment ---------------------------------------------------------------


def test_a_unique_prefix_match_attaches_with_full_confidence(exclusions) -> None:
    parents = apply_exclusions([report(1, "Notes", "Debt", "http://x/role/Debt")], exclusions)
    children = [report(2, "Details", "Debt Details", "http://x/role/DebtDetails")]
    attachments = attach_by_role_uri(parents, children)
    assert attachments[0].is_attached
    assert attachments[0].method == "role_uri"
    assert attachments[0].confidence == 1.0
    assert attachments[0].stage == 3


def test_a_child_matching_no_parent_is_an_orphan_not_a_guess(exclusions) -> None:
    parents = apply_exclusions([report(1, "Notes", "Debt", "http://x/role/Debt")], exclusions)
    children = [report(2, "Details", "Unrelated", "http://x/role/SomethingElse")]
    attachments = attach_by_role_uri(parents, children)
    assert not attachments[0].is_attached
    assert attachments[0].competing_candidates == []
    assert "no parent role URI is a prefix" in attachments[0].reason


def test_an_ambiguous_child_stays_unattached_and_records_both_candidates(exclusions) -> None:
    """A TIE IS NEVER BROKEN SILENTLY.

    Choosing the longest or the earliest match would be a convention nobody agreed to, and
    afterwards it would look identical to a correct attachment. An orphan is visible and fixable.
    """
    parents = apply_exclusions(
        [
            report(1, "Notes", "Debt", "http://x/role/Debt"),
            report(2, "Notes", "Debt Detail", "http://x/role/DebtDetail"),
        ],
        exclusions,
    )
    children = [report(3, "Details", "Ambiguous", "http://x/role/DebtDetailExtra")]
    attachments = attach_by_role_uri(parents, children)
    assert not attachments[0].is_attached
    assert len(attachments[0].competing_candidates) == 2
    assert "not broken silently" in attachments[0].reason


def test_a_child_without_a_role_uri_is_an_orphan(exclusions) -> None:
    parents = apply_exclusions([report(1, "Notes", "Debt", "http://x/role/Debt")], exclusions)
    attachments = attach_by_role_uri(parents, [report(2, "Details", "No role", None)])
    assert not attachments[0].is_attached
    assert "no role URI" in attachments[0].reason


def test_attachment_order_does_not_change_the_result(exclusions) -> None:
    """A child filed before its parent attaches identically to one filed after it."""
    parents = apply_exclusions([report(5, "Notes", "Debt", "http://x/role/Debt")], exclusions)
    early = attach_by_role_uri(parents, [report(1, "Details", "d", "http://x/role/DebtD")])
    late = attach_by_role_uri(parents, [report(9, "Details", "d", "http://x/role/DebtD")])
    assert early[0].parent_role_uri == late[0].parent_role_uri == "http://x/role/Debt"


def test_every_attachment_carries_evidence(exclusions) -> None:
    parents = apply_exclusions([report(1, "Notes", "Debt", "http://x/role/Debt")], exclusions)
    attachment = attach_by_role_uri(parents, [report(2, "Details", "d", "http://x/role/DebtD")])[0]
    assert attachment.evidence["matched_parent_role_uri"] == "http://x/role/Debt"
    assert attachment.evidence["child_role_uri"] == "http://x/role/DebtD"
    assert attachment.reason


# --- stage 4: TOC reconciliation ----------------------------------------------------------------


def test_no_toc_reports_not_attempted_rather_than_reconciled() -> None:
    """Apple's FY2025 10-K has no per-note table of contents.

    Reporting RECONCILED here would claim a confirmation that never happened, and a count cannot
    distinguish "matched" from "nothing to match against".
    """
    status, detail = reconcile_against_toc(13, None)
    assert status == NOT_ATTEMPTED
    assert "no per-note table of contents" in detail


def test_a_matching_toc_reconciles() -> None:
    assert reconcile_against_toc(13, 13)[0] == RECONCILED


def test_a_toc_mismatch_does_not_adjust_the_extracted_set() -> None:
    status, detail = reconcile_against_toc(22, 24)
    assert status == MISMATCH
    assert "not adjusted" in detail


# --- stage 5: heading reconciliation -------------------------------------------------------------


def test_matching_counts_confirm(exclusions) -> None:
    notes = apply_exclusions([report(1, "Notes", "A", "http://x/role/A")], exclusions)
    ok, _ = reconcile_against_headings(notes, (NoteHeading(1, "A", 0, False),))
    assert ok


def test_a_count_disagreement_does_not_confirm(exclusions) -> None:
    notes = apply_exclusions([report(1, "Notes", "A", "http://x/role/A")], exclusions)
    ok, detail = reconcile_against_headings(
        notes, (NoteHeading(1, "A", 0, False), NoteHeading(2, "B", 1, False))
    )
    assert not ok and "2 headings" in detail


def test_non_contiguous_headings_do_not_confirm(exclusions) -> None:
    """A gap means a heading was missed or a false one matched, either way the count is unusable."""
    notes = apply_exclusions(
        [report(1, "Notes", "A", "http://x/role/A"), report(2, "Notes", "B", "http://x/role/B")],
        exclusions,
    )
    ok, detail = reconcile_against_headings(
        notes, (NoteHeading(1, "A", 0, False), NoteHeading(5, "B", 1, False))
    )
    assert not ok and "not contiguous" in detail


def test_headings_match_footnotes_by_normalized_title(exclusions) -> None:
    notes = apply_exclusions(
        [report(1, "Notes", "Shareholders’ Equity", "http://x/role/SE")], exclusions
    )
    mapping = match_headings_to_footnotes(
        notes, (NoteHeading(10, "Shareholders' Equity", 0, False),)
    )
    assert mapping["http://x/role/SE"].number == 10


def test_unmatched_titles_fall_back_to_filed_order(exclusions) -> None:
    """Order alone is fragile; title alone fails on typography. Title first, then order."""
    notes = apply_exclusions(
        [report(1, "Notes", "Totally Different", "http://x/role/A")], exclusions
    )
    mapping = match_headings_to_footnotes(notes, (NoteHeading(7, "Something Else", 0, False),))
    assert mapping["http://x/role/A"].number == 7


# --- completeness ---------------------------------------------------------------------------------


def test_a_clean_extraction_is_complete(ten_k) -> None:
    assert evaluate(ten_k).extraction_status == COMPLETE


def test_an_orphan_makes_the_filing_partial_never_complete(ten_k, exclusions) -> None:
    """NO PERCENTAGE ROUNDS UP. 45 of 46 attached is not complete."""
    import copy

    damaged = copy.deepcopy(ten_k)
    damaged.attachments[0].parent_role_uri = None
    completeness = evaluate(damaged)
    assert completeness.orphan_count == 1
    assert completeness.extraction_status == PARTIAL
    assert completeness.extraction_status != COMPLETE


def test_a_review_flag_requires_review(ten_k) -> None:
    import copy

    damaged = copy.deepcopy(ten_k)
    damaged.flagged_for_review.append(damaged.footnotes[0])
    assert evaluate(damaged).extraction_status == REQUIRES_REVIEW


def test_no_footnotes_is_failed_not_partial(ten_k) -> None:
    import copy

    damaged = copy.deepcopy(ten_k)
    damaged.footnotes = []
    assert evaluate(damaged).extraction_status == FAILED


def test_a_toc_mismatch_makes_the_filing_partial(exclusions) -> None:
    inventory = read_inventory(TEN_K)
    result = canonicalize(
        accession="x",
        inventory=inventory,
        headings=(),
        exclusions=exclusions,
        toc_expected_note_count=24,
    )
    assert evaluate(result).extraction_status == PARTIAL


def test_confidence_is_reduced_by_each_unconfirmed_thing(ten_k) -> None:
    """An unreconciled filing is not as trustworthy as a reconciled one, even when counts agree."""
    completeness = evaluate(ten_k)
    assert completeness.confidence < 1
    assert any("table of contents" in r for r in completeness.reasons)


def test_a_filing_with_no_summaries_is_not_complete_at_the_filing_level(ten_k) -> None:
    """The product requirement is one accepted summary per footnote. Summaries are Sprint 5.

    Reporting COMPLETE for a filing with zero summaries would satisfy an extraction check while
    breaking the requirement the status exists to express.
    """
    completeness = evaluate(ten_k)
    assert completeness.extraction_status == COMPLETE
    assert filing_footnote_status(completeness, accepted_summaries=0) == PARTIAL
    assert filing_footnote_status(completeness, accepted_summaries=12) == PARTIAL
    assert filing_footnote_status(completeness, accepted_summaries=13) == COMPLETE


# --- the report -------------------------------------------------------------------------------


def test_the_reconciliation_report_lists_every_note_and_its_children(ten_k) -> None:
    text = reconciliation_report(ten_k, evaluate(ten_k))
    assert "CANONICAL FOOTNOTES" in text
    for note in ten_k.footnotes:
        assert note.title[:30] in text
    assert "orphans" in text


def test_the_report_emits_no_json_or_markdown(ten_k) -> None:
    """A plain-text operational artifact, per the LLM content boundary."""
    text = reconciliation_report(ten_k, evaluate(ten_k))
    assert "```" not in text
    assert not text.lstrip().startswith("{")


# --- stage 1 and 2 on the real filing ------------------------------------------------------------


def test_stage_one_finds_sixteen_candidates() -> None:
    assert len(discover_candidates(read_inventory(TEN_K))) == 16


def test_stage_two_removes_exactly_three(ten_k) -> None:
    assert len(ten_k.candidates) == 16
    assert len(ten_k.footnotes) == 13
    assert len(ten_k.excluded) == 3
    assert len(ten_k.flagged_for_review) == 0


def test_the_three_exclusions_are_the_item_disclosures(ten_k) -> None:
    items = sorted(note.verdict.item for note in ten_k.excluded)
    assert items == ["Item 1C", "Item 408", "Item 408"]
