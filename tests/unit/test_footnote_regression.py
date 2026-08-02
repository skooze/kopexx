"""The Apple FY2025 10-K regression test, and proof that it can fail.

This is the test that guards the thesis the whole product rests on: a 10-K has 13 financial
statement footnotes, not the 71 renderer reports, 58 TextBlock facts, or 16 Notes-category
candidates a naive count produces.

A regression test whose failure has never been observed is a claim, not a guard. The mutation
proofs below introduce each of the four failures the specification names and assert that the
regression test detects every one.
"""

from __future__ import annotations

import copy
from pathlib import Path

import pytest

from packages.footnote_canonicalizer import (
    COMPLETE,
    PARTIAL,
    ExclusionList,
    canonicalize,
    evaluate,
)
from packages.footnote_extractor import NoteHeading, read_inventory

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "filings"
TEN_K = FIXTURES / "0000320193-25-000079" / "filing-summary.xml"

# Measured from the filed document, not predicted. See docs/sprints/SPRINT-0004.md.
EXPECTED_CANDIDATES = 16
EXPECTED_FOOTNOTES = 13
EXPECTED_CHILD_BLOCKS = 46
EXPECTED_ATTACHED = 46
EXPECTED_ORPHANS = 0
EXPECTED_EXCLUSIONS = 3

# Per-note child counts, in filed order. A total of 46 spread the wrong way would pass a count
# check while attaching a tax detail to the debt note.
EXPECTED_CHILDREN_PER_NOTE = [1, 4, 3, 4, 3, 3, 6, 4, 5, 3, 4, 2, 4]


def build(inventory=None):
    exclusions = ExclusionList.load()
    headings = tuple(
        NoteHeading(number=i, title=f"Note {i}", line_index=i, joined_from_next_line=True)
        for i in range(1, EXPECTED_FOOTNOTES + 1)
    )
    return canonicalize(
        accession="0000320193-25-000079",
        inventory=inventory or read_inventory(TEN_K),
        headings=headings,
        exclusions=exclusions,
    )


@pytest.fixture(scope="module")
def result():
    return build()


# --- the regression test ------------------------------------------------------------------------


def test_apple_fy2025_canonicalization(result) -> None:
    """THE REGRESSION TEST. 13 footnotes, 46 attached, zero orphans, three exclusions."""
    assert len(result.candidates) == EXPECTED_CANDIDATES
    assert len(result.footnotes) == EXPECTED_FOOTNOTES
    assert len(result.excluded) == EXPECTED_EXCLUSIONS
    assert result.child_block_count == EXPECTED_CHILD_BLOCKS
    assert result.attached_count == EXPECTED_ATTACHED
    assert result.orphan_count == EXPECTED_ORPHANS
    assert result.flagged_for_review == []
    assert evaluate(result).extraction_status == COMPLETE


def test_children_are_distributed_across_the_right_notes(result) -> None:
    """A total of 46 spread the wrong way passes a count check and is still wrong."""
    actual = [len(result.children_of(n.role_uri)) for n in result.footnotes]
    assert actual == EXPECTED_CHILDREN_PER_NOTE
    assert sum(actual) == EXPECTED_ATTACHED


def test_filed_order_is_preserved(result) -> None:
    positions = [n.report.position for n in result.footnotes]
    assert positions == sorted(positions)


def test_every_attachment_carries_a_full_audit_record(result) -> None:
    """The product must later explain why a block was attached where it was.

    Storing only the parent foreign key cannot answer that.
    """
    for attachment in result.attachments:
        assert attachment.evidence
        assert attachment.reason
        if attachment.is_attached:
            assert attachment.stage == 3
            assert attachment.method == "role_uri"
            assert attachment.confidence == 1.0
            assert attachment.evidence["matched_parent_role_uri"]
            # An unambiguous match has no competitors, but the field is still represented.
            assert attachment.competing_candidates == []


def test_the_excluded_disclosures_are_the_item_408_and_1c_ones(result) -> None:
    items = sorted(n.verdict.item for n in result.excluded)
    assert items == ["Item 1C", "Item 408", "Item 408"]
    for note in result.excluded:
        assert note.verdict.rule and note.verdict.matched_on


def test_no_issuer_specific_logic_produced_this_result() -> None:
    """The exclusions come from YAML, and no CODE in the packages names an issuer.

    A branch of the form `if cik == "0000320193"` would make this test pass and every other filer
    fail. That is the defect. Naming the filing the measured numbers came from, in a docstring, is
    provenance and is required.

    Distinguishing the two took two attempts, and the second was found by mutation rather than by
    reading:

      1. Skipping lines starting with `#` or a quote flagged eight docstring CONTINUATION lines,
         which do not start with a quote.
      2. Skipping every STRING token then missed `if cik == "0000320193"` entirely — the issuer is
         a string literal, so exempting all strings exempts exactly the defect being hunted.

    The AST walk below exempts docstrings specifically and inspects every other literal and name.
    """
    import ast
    import re

    packages = Path(__file__).resolve().parents[2] / "packages"
    pattern = re.compile(r"(apple|aapl|0000320193)", re.IGNORECASE)
    offenders = []

    for name in ("footnote_extractor", "footnote_canonicalizer", "table_parser"):
        for path in sorted((packages / name).rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

            docstrings = set()
            for node in ast.walk(tree):
                if isinstance(
                    node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef
                ):
                    body = getattr(node, "body", [])
                    if (
                        body
                        and isinstance(body[0], ast.Expr)
                        and isinstance(body[0].value, ast.Constant)
                        and isinstance(body[0].value.value, str)
                    ):
                        docstrings.add(id(body[0].value))

            for node in ast.walk(tree):
                if isinstance(node, ast.Constant) and isinstance(node.value, str):
                    if id(node) in docstrings:
                        continue
                    if pattern.search(node.value):
                        offenders.append(f"{path.name}:{node.lineno}: literal {node.value!r}")
                elif isinstance(node, ast.Name) and pattern.search(node.id):
                    offenders.append(f"{path.name}:{node.lineno}: name {node.id}")
                elif isinstance(node, ast.Attribute) and pattern.search(node.attr):
                    offenders.append(f"{path.name}:{node.lineno}: attribute {node.attr}")

    assert not offenders, f"issuer-specific reference in shipped CODE: {offenders}"


# --- mutation proofs: the regression test must be able to fail -----------------------------------


def test_mutation_an_omitted_note_is_detected(result) -> None:
    """Remove one canonical footnote. The count check and the distribution check must both fail."""
    damaged = copy.deepcopy(result)
    damaged.footnotes.pop(6)

    assert len(damaged.footnotes) != EXPECTED_FOOTNOTES
    actual = [len(damaged.children_of(n.role_uri)) for n in damaged.footnotes]
    assert actual != EXPECTED_CHILDREN_PER_NOTE


def test_mutation_an_orphaned_child_is_detected(result) -> None:
    """Detach one child. Orphan count, attached count, and completeness must all change."""
    damaged = copy.deepcopy(result)
    damaged.attachments[0].parent_role_uri = None

    assert damaged.orphan_count == 1
    assert damaged.attached_count == EXPECTED_ATTACHED - 1
    assert evaluate(damaged).extraction_status == PARTIAL
    assert evaluate(damaged).extraction_status != COMPLETE


def test_mutation_a_misclassified_exclusion_is_detected(result) -> None:
    """Promote an Item 408 disclosure to a footnote. The counts must move in both directions."""
    damaged = copy.deepcopy(result)
    promoted = damaged.excluded.pop(0)
    damaged.footnotes.append(promoted)

    assert len(damaged.footnotes) == EXPECTED_FOOTNOTES + 1
    assert len(damaged.excluded) == EXPECTED_EXCLUSIONS - 1


def test_mutation_a_duplicate_attachment_is_detected(result) -> None:
    """Attach one child twice. The child-block total must exceed the expected count."""
    damaged = copy.deepcopy(result)
    damaged.attachments.append(copy.deepcopy(damaged.attachments[0]))

    assert damaged.child_block_count == EXPECTED_CHILD_BLOCKS + 1
    assert damaged.attached_count == EXPECTED_ATTACHED + 1


def test_mutation_removing_a_notes_report_changes_the_candidate_count() -> None:
    """A source report deliberately removed must not still yield 13 footnotes."""
    inventory = read_inventory(TEN_K)
    survivors = tuple(r for r in inventory.reports if r.role != "http://www.apple.com/role/Debt")
    damaged = build(
        inventory=type(inventory)(
            reports=survivors,
            source_sha256=inventory.source_sha256,
            source_path=inventory.source_path,
        )
    )
    assert len(damaged.footnotes) == EXPECTED_FOOTNOTES - 1
    # Its five children now match no parent and become orphans rather than being reassigned.
    assert damaged.orphan_count == 5
    assert evaluate(damaged).extraction_status == PARTIAL
