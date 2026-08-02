"""The Apple FY2025 10-Q canonicalization regression, and proof that it can fail.

Sprint 4 measured these three filings and recorded the results in docs/sprints/SPRINT-0004.md, but
only the 10-K's note and attachment counts were ever asserted. CI therefore proved the 10-Qs' TABLE
OWNERSHIP census — tests/unit/test_table_ownership_regression.py — while their canonical-footnote
and attached-child counts were held nowhere a test could check. A measured result that no test
asserts is a claim; this file turns the three quarterly measurements into guards.

Post-Sprint-4 hardening. It adds no behaviour: every expected value below was produced by the
canonicalizer as committed, read back from the committed FilingSummary fixtures, and none of the
Sprint 4 measurements changed.

WHY THE HEADINGS ARE SYNTHESIZED. Stage 4 reconciles the note count against `Note N —` headings
parsed from the primary document, and the primary documents are not committed — they are 6 MB of
content SEC hosts authoritatively. The 10-K regression has always synthesized headings for the same
reason. The consequence is stated plainly: DISPLAYED NOTE NUMBERS COME FROM THE PRIMARY DOCUMENT AND
ARE NOT ASSERTED HERE. What is asserted is the filed order the FilingSummary fixes, the sequence
position each note takes within it, and each note's title as filed.
"""

from __future__ import annotations

import copy
from pathlib import Path

import pytest

from packages.footnote_canonicalizer import (
    COMPLETE,
    PARTIAL,
    CanonicalizationResult,
    ExclusionList,
    canonicalize,
    evaluate,
)
from packages.footnote_extractor import NoteHeading, read_inventory

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "filings"

# Complete accessions, as recorded in tests/fixtures/filings/manifest.yaml. Written out in full
# rather than abbreviated: an accession is the filing's identity, and a shortened form cannot be
# matched back to the manifest that pins the source URL and hash.
Q1 = "0000320193-25-000008"
Q2 = "0000320193-25-000057"
Q3 = "0000320193-25-000073"
TEN_QS = (Q1, Q2, Q3)

# Measured against the committed FilingSummary fixtures, not predicted.
#
# Q1 and Q2 are structurally identical. Q3 differs by exactly two child blocks, both on the debt
# note, which is why the totals are 23/23/25 and not a single number — see the distributions below.
EXPECTED = {
    Q1: {
        "candidates": 12,
        "footnotes": 10,
        "excluded": 2,
        "child_blocks": 23,
        "attached": 23,
        "orphans": 0,
        "ambiguous": 0,
        "distribution": [1, 4, 2, 4, 3, 1, 1, 4, 0, 3],
    },
    Q2: {
        "candidates": 12,
        "footnotes": 10,
        "excluded": 2,
        "child_blocks": 23,
        "attached": 23,
        "orphans": 0,
        "ambiguous": 0,
        "distribution": [1, 4, 2, 4, 3, 1, 1, 4, 0, 3],
    },
    Q3: {
        "candidates": 12,
        "footnotes": 10,
        "excluded": 2,
        "child_blocks": 25,
        "attached": 25,
        "orphans": 0,
        "ambiguous": 0,
        "distribution": [1, 4, 2, 4, 3, 3, 1, 4, 0, 3],
    },
}

# The ten notes, in filed order, identical across all three quarters. Titles are the filer's own
# ShortName from FilingSummary.xml.
#
# `Contingencies` carries zero child blocks in every quarter. That is a real property of these
# filings, not a defect: a note with no Tables or Details report has no child to attach. Recorded
# explicitly so a future change that starts inventing children for it fails here.
EXPECTED_TITLES = [
    "Summary of Significant Accounting Policies",
    "Revenue",
    "Earnings Per Share",
    "Financial Instruments",
    "Condensed Consolidated Financial Statement Details",
    "Debt",
    "Shareholders' Equity",
    "Share-Based Compensation",
    "Contingencies",
    "Segment Information and Geographic Data",
]

# Both quarterly exclusions come from the `ecd` namespace rule, so both carry the item label the
# exclusion list attaches to that namespace. The 10-K excludes three disclosures; a 10-Q excludes
# two, and they are not the same two.
EXPECTED_EXCLUDED_TITLES = ["Pay vs Performance Disclosure", "Insider Trading Arrangements"]
EXPECTED_EXCLUDED_ROLES = {
    "http://xbrl.sec.gov/ecd/role/PvpDisclosure",
    "http://xbrl.sec.gov/ecd/role/InsiderTradingArrangements",
}


def build(accession: str, inventory=None) -> CanonicalizationResult:
    """Canonicalize one quarterly filing from its committed FilingSummary fixture.

    Two passes. The first learns how many footnotes the filing has so the synthesized heading set
    matches it; the second is the result under test. Hardcoding the heading count would make stage
    4's reconciliation assert against a number this file chose rather than one the filing produced.
    """
    inventory = inventory if inventory is not None else read_inventory(_summary(accession))
    exclusions = ExclusionList.load()
    discovered = canonicalize(
        accession=accession, inventory=inventory, headings=(), exclusions=exclusions
    )
    headings = tuple(
        NoteHeading(number=i, title=f"Note {i}", line_index=i, joined_from_next_line=True)
        for i in range(1, len(discovered.footnotes) + 1)
    )
    return canonicalize(
        accession=accession, inventory=inventory, headings=headings, exclusions=exclusions
    )


def _summary(accession: str) -> Path:
    return FIXTURES / accession / "filing-summary.xml"


@pytest.fixture(scope="module")
def results() -> dict[str, CanonicalizationResult]:
    return {accession: build(accession) for accession in TEN_QS}


def _distribution(result: CanonicalizationResult) -> list[int]:
    return [len(result.children_of(note.role_uri)) for note in result.footnotes]


# --- the regression -------------------------------------------------------------------------------


@pytest.mark.parametrize("accession", TEN_QS)
def test_quarterly_canonicalization(accession: str, results) -> None:
    """THE REGRESSION. Ten footnotes, every child attached, no orphan, no ambiguity."""
    result = results[accession]
    expected = EXPECTED[accession]

    assert len(result.candidates) == expected["candidates"]
    assert len(result.footnotes) == expected["footnotes"]
    assert len(result.excluded) == expected["excluded"]
    assert result.child_block_count == expected["child_blocks"]
    assert result.attached_count == expected["attached"]
    assert result.orphan_count == expected["orphans"]
    assert result.flagged_for_review == []
    assert evaluate(result).extraction_status == COMPLETE


@pytest.mark.parametrize("accession", TEN_QS)
def test_no_attachment_is_ambiguous(accession: str, results) -> None:
    """An attachment with competitors was decided between candidates, not by an unambiguous match.

    Zero here is what makes `grouping_method='role_uri'` at confidence 1.0 an honest record.
    """
    ambiguous = [a for a in results[accession].attachments if a.competing_candidates]
    assert len(ambiguous) == EXPECTED[accession]["ambiguous"]
    assert ambiguous == []


@pytest.mark.parametrize("accession", TEN_QS)
def test_children_are_distributed_across_the_right_notes(accession: str, results) -> None:
    """A correct total spread the wrong way passes a count check and is still wrong.

    Q3's extra two blocks belong to the debt note. A distribution check is what distinguishes that
    from two extra blocks landing anywhere else and still summing to 25.
    """
    result = results[accession]
    actual = _distribution(result)
    assert actual == EXPECTED[accession]["distribution"]
    assert sum(actual) == EXPECTED[accession]["attached"]


@pytest.mark.parametrize("accession", TEN_QS)
def test_notes_appear_in_filed_order_with_the_filed_titles(accession: str, results) -> None:
    """Filed order and title, plus the sequence position each note takes.

    Displayed note numbers come from the primary document and are not committed as a fixture; the
    ordinal position within the filed order is what this asserts instead.
    """
    result = results[accession]

    positions = [note.report.position for note in result.footnotes]
    assert positions == sorted(positions), "footnotes are not in filed order"
    assert len(set(positions)) == len(positions), "two footnotes share a filed position"

    assert [note.title for note in result.footnotes] == EXPECTED_TITLES

    # The ordinal a note receives is its rank in FILED order. Re-sorting by filed position must
    # therefore change nothing; if it does, the list is ordered by something else that happens to
    # agree on this filing.
    ranked = sorted(result.footnotes, key=lambda note: note.report.position)
    assert [note.title for note in ranked] == EXPECTED_TITLES
    assert [note.role_uri for note in ranked] == [note.role_uri for note in result.footnotes]


@pytest.mark.parametrize("accession", TEN_QS)
def test_every_child_block_is_unique_and_attached_exactly_once(accession: str, results) -> None:
    """One block, one attachment, one parent.

    Two attachments naming the same block would double a note's content and inflate the model
    budget for it; the same block attached to two notes would put a tax detail under debt.
    """
    result = results[accession]
    identities = [attachment.child.external_id for attachment in result.attachments]

    assert len(identities) == EXPECTED[accession]["child_blocks"]
    assert len(set(identities)) == len(identities), "a child block appears in two attachments"
    assert all(identities), "a child block has no identity"

    parents_by_child: dict[str, set[str | None]] = {}
    for attachment in result.attachments:
        parents_by_child.setdefault(attachment.child.external_id, set()).add(
            attachment.parent_role_uri
        )
    assert all(len(parents) == 1 for parents in parents_by_child.values())


@pytest.mark.parametrize("accession", TEN_QS)
def test_every_attachment_resolves_to_one_of_the_ten_notes(accession: str, results) -> None:
    result = results[accession]
    note_roles = {note.role_uri for note in result.footnotes}

    assert len(note_roles) == EXPECTED[accession]["footnotes"], "two notes share a role URI"
    for attachment in result.attachments:
        assert attachment.parent_role_uri in note_roles
        assert attachment.stage == 3
        assert attachment.method == "role_uri"
        assert attachment.confidence == 1.0


@pytest.mark.parametrize("accession", TEN_QS)
def test_the_excluded_disclosures_never_enter_the_footnote_set(accession: str, results) -> None:
    """The exclusion must remove the disclosure from the notes, not merely label it.

    An excluded disclosure that stays in `footnotes` would be summarized as a financial-statement
    footnote, which is exactly the over-inclusion the canonicalization layer exists to prevent.
    """
    result = results[accession]

    assert [note.title for note in result.excluded] == EXPECTED_EXCLUDED_TITLES
    assert {note.role_uri for note in result.excluded} == EXPECTED_EXCLUDED_ROLES

    footnote_roles = {note.role_uri for note in result.footnotes}
    footnote_titles = {note.title for note in result.footnotes}
    for excluded in result.excluded:
        assert excluded.role_uri not in footnote_roles
        assert excluded.title not in footnote_titles
        assert excluded.verdict.rule and excluded.verdict.matched_on
        # No child block may be attached to something that is not a footnote.
        assert result.children_of(excluded.role_uri) == []


@pytest.mark.parametrize("accession", TEN_QS)
def test_canonicalizing_twice_produces_an_identical_record(accession: str) -> None:
    """Determinism at the source, before any database is involved.

    tests/integration/test_ten_q_persistence.py carries the database-backed half: an identical
    rerun inserts nothing, updates nothing, and leaves the persisted digest unchanged.
    """
    first, second = build(accession), build(accession)

    assert _distribution(first) == _distribution(second)
    assert [note.title for note in first.footnotes] == [note.title for note in second.footnotes]
    assert [
        (a.child.external_id, a.parent_role_uri, a.stage, a.method, a.confidence)
        for a in first.attachments
    ] == [
        (a.child.external_id, a.parent_role_uri, a.stage, a.method, a.confidence)
        for a in second.attachments
    ]


def test_the_three_quarters_differ_only_where_measured() -> None:
    """Q1 and Q2 are identical in shape; Q3 differs by two debt-note child blocks.

    Stated as a test so a change that quietly makes all three the same — or all three different —
    cannot pass as normal variation.
    """
    assert EXPECTED[Q1]["distribution"] == EXPECTED[Q2]["distribution"]
    assert EXPECTED[Q3]["distribution"] != EXPECTED[Q1]["distribution"]

    difference = [
        q3 - q1
        for q3, q1 in zip(EXPECTED[Q3]["distribution"], EXPECTED[Q1]["distribution"], strict=True)
    ]
    assert difference == [0, 0, 0, 0, 0, 2, 0, 0, 0, 0], "the difference moved off the debt note"
    assert EXPECTED_TITLES[difference.index(2)] == "Debt"


# --- mutation proofs: each new assertion must be able to fail --------------------------------------
#
# A regression test whose failure has never been observed is a claim. Each proof below damages one
# thing, asserts the corresponding check rejects it, and works on a deep copy so nothing is
# restored by hand and nothing can leak into another test.


@pytest.mark.parametrize("accession", TEN_QS)
def test_mutation_a_removed_footnote_is_detected(accession: str, results) -> None:
    damaged = copy.deepcopy(results[accession])
    damaged.footnotes.pop(5)

    assert len(damaged.footnotes) != EXPECTED[accession]["footnotes"]
    assert _distribution(damaged) != EXPECTED[accession]["distribution"]
    assert [note.title for note in damaged.footnotes] != EXPECTED_TITLES


@pytest.mark.parametrize("accession", TEN_QS)
def test_mutation_a_removed_attachment_is_detected(accession: str, results) -> None:
    """Detaching one child must move the orphan count, the attached count, and completeness."""
    damaged = copy.deepcopy(results[accession])
    damaged.attachments[0].parent_role_uri = None

    assert damaged.orphan_count == 1
    assert damaged.attached_count == EXPECTED[accession]["attached"] - 1
    assert _distribution(damaged) != EXPECTED[accession]["distribution"]
    assert evaluate(damaged).extraction_status == PARTIAL


@pytest.mark.parametrize("accession", TEN_QS)
def test_mutation_a_child_attached_to_the_wrong_note_is_detected(accession: str, results) -> None:
    """The total stays right. Only the distribution can catch this."""
    result = results[accession]
    damaged = copy.deepcopy(result)

    moved = damaged.attachments[0]
    origin = moved.parent_role_uri
    destination = next(
        note.role_uri for note in damaged.footnotes if note.role_uri not in (None, origin)
    )
    moved.parent_role_uri = destination

    assert damaged.attached_count == EXPECTED[accession]["attached"], "the total must not move"
    assert damaged.orphan_count == 0, "a misattached child is not an orphan"
    assert _distribution(damaged) != EXPECTED[accession]["distribution"]


@pytest.mark.parametrize("accession", TEN_QS)
def test_mutation_a_promoted_item_disclosure_is_detected(accession: str, results) -> None:
    """Reclassify an excluded disclosure as a canonical footnote."""
    damaged = copy.deepcopy(results[accession])
    promoted = damaged.excluded.pop(0)
    damaged.footnotes.append(promoted)

    assert len(damaged.footnotes) == EXPECTED[accession]["footnotes"] + 1
    assert len(damaged.excluded) == EXPECTED[accession]["excluded"] - 1
    assert [note.title for note in damaged.footnotes] != EXPECTED_TITLES
    assert promoted.role_uri in {note.role_uri for note in damaged.footnotes}


def test_mutation_reducing_the_q3_total_from_twenty_five_is_detected(results) -> None:
    """Q3 has 25 attached child blocks. Asserting 23 for it must fail."""
    result = results[Q3]
    assert result.attached_count == 25
    assert result.attached_count != EXPECTED[Q1]["attached"]

    damaged = copy.deepcopy(result)
    for attachment in damaged.attachments[:2]:
        attachment.parent_role_uri = None

    assert damaged.attached_count == 23
    assert damaged.attached_count != EXPECTED[Q3]["attached"]
    assert damaged.orphan_count == 2
    assert evaluate(damaged).extraction_status == PARTIAL


@pytest.mark.parametrize("accession", TEN_QS)
def test_mutation_a_right_total_with_a_wrong_distribution_is_detected(
    accession: str, results
) -> None:
    """Move one child from a note that has several onto the note that has none.

    The sum is unchanged and no block is orphaned. This is the failure a count check cannot see,
    and it is the reason the distribution is asserted at all.
    """
    damaged = copy.deepcopy(results[accession])
    distribution = _distribution(damaged)

    empty = damaged.footnotes[distribution.index(0)]
    donor = damaged.footnotes[distribution.index(max(distribution))]
    damaged.children_of(donor.role_uri)[0].parent_role_uri = empty.role_uri

    assert damaged.attached_count == EXPECTED[accession]["attached"], "the total must not move"
    assert damaged.orphan_count == 0
    assert _distribution(damaged) != EXPECTED[accession]["distribution"]
    assert sum(_distribution(damaged)) == sum(EXPECTED[accession]["distribution"])


def test_mutation_removing_a_notes_report_changes_the_result(results) -> None:
    """A source report deliberately removed must not still yield ten footnotes.

    Removes the debt note from Q3, which is the note carrying that quarter's three child blocks.
    """
    inventory = read_inventory(_summary(Q3))
    debt = next(r for r in inventory.reports if (r.role or "").endswith("/Debt"))
    survivors = tuple(r for r in inventory.reports if r is not debt)

    damaged = build(
        Q3,
        inventory=type(inventory)(
            reports=survivors,
            source_sha256=inventory.source_sha256,
            source_path=inventory.source_path,
        ),
    )

    assert len(damaged.footnotes) == EXPECTED[Q3]["footnotes"] - 1
    assert damaged.orphan_count == 3, "the debt note's children must orphan, not be reassigned"
    assert evaluate(damaged).extraction_status == PARTIAL
