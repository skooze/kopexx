"""Footnote completeness, computed rather than assumed.

The product requirement is that EVERY financial-statement footnote in every processed 10-K and
10-Q has one canonical record and one active accepted summary. A filing that extracted 12 of 13
notes is not complete, and the dashboard must say so rather than round up.

WHAT THIS MODULE DOES AND DOES NOT DECIDE. Summaries do not exist yet — Sprint 5 builds them. So
extraction completeness is what can honestly be evaluated now, and a filing that extracts perfectly
is `PARTIAL` at the filing level until its summaries exist. Reporting `COMPLETE` for a filing with
zero summaries would satisfy the letter of an extraction check while breaking the product
requirement the status exists to express.

NO PERCENTAGE ROUNDS UP. 45 of 46 children attached is not complete. There is no threshold below
100 percent at which a missing footnote becomes acceptable, because the missing one is exactly the
one an investor needed.

MOST COUNTERS ARE DERIVED, NOT STORED. A count recomputable from child rows is never also stored
on the filing: the stored copy is a second source of truth that goes stale the moment a block is
re-attached. Only judgements with no child rows to recompute from are persisted.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from .stages import MISMATCH, NOT_ATTEMPTED, CanonicalizationResult

COMPLETE = "COMPLETE"
PARTIAL = "PARTIAL"
REQUIRES_REVIEW = "REQUIRES_REVIEW"
FAILED = "FAILED"
NOT_STARTED = "NOT_STARTED"

# Confidence starts at certainty and is reduced by each thing that did not confirm. These are
# judgements, deliberately conservative: an unreconciled filing is not as trustworthy as a
# reconciled one even when every count agrees.
PENALTY_NO_TOC = Decimal("0.05")
PENALTY_TOC_MISMATCH = Decimal("0.50")
PENALTY_NO_HEADING_CONFIRMATION = Decimal("0.20")
PENALTY_PER_ORPHAN = Decimal("0.10")
PENALTY_REVIEW_FLAG = Decimal("0.30")
PENALTY_PER_UNRESOLVED_TABLE = Decimal("0.05")


@dataclass(frozen=True)
class ExtractionCompleteness:
    """The counters and the verdict for one filing's extraction."""

    accession: str
    candidate_count: int
    canonical_footnote_count: int
    child_block_count: int
    attached_child_block_count: int
    orphan_count: int
    excluded_section_count: int
    review_flag_count: int
    headings_parsed: int
    toc_expected_note_count: int | None
    reconciliation_status: str
    heading_reconciled: bool
    tables_total: int
    tables_owned_by_footnote: int
    tables_unresolved: int
    extraction_status: str
    confidence: Decimal
    reasons: tuple[str, ...]

    @property
    def extraction_is_clean(self) -> bool:
        """Extraction produced a complete, unambiguous set.

        Distinct from the filing's `footnote_status`, which cannot be COMPLETE until summaries
        exist. This is what Sprint 4 can actually assert.
        """
        return self.extraction_status == COMPLETE

    def as_record(self) -> dict[str, Any]:
        return {
            "accession": self.accession,
            "candidates": self.candidate_count,
            "canonical_footnotes": self.canonical_footnote_count,
            "child_blocks": self.child_block_count,
            "attached": self.attached_child_block_count,
            "orphans": self.orphan_count,
            "excluded_sections": self.excluded_section_count,
            "flagged_for_review": self.review_flag_count,
            "headings_parsed": self.headings_parsed,
            "toc_expected_note_count": self.toc_expected_note_count,
            "reconciliation_status": self.reconciliation_status,
            "heading_reconciled": self.heading_reconciled,
            "tables_total": self.tables_total,
            "tables_owned_by_footnote": self.tables_owned_by_footnote,
            "tables_unresolved": self.tables_unresolved,
            "extraction_status": self.extraction_status,
            "confidence": str(self.confidence),
            "reasons": list(self.reasons),
        }


def evaluate(
    result: CanonicalizationResult, ownership: Any | None = None
) -> ExtractionCompleteness:
    """Compute the counters and the extraction verdict for one canonicalization run.

    `ownership` is an `OwnershipReconciliation`. It is optional so the five stages stay evaluable
    without table parsing, but when it is supplied an unresolved footnote table blocks COMPLETE:
    Sprint 5 validates a summary's numbers against that footnote's own tables, and a table whose
    owner is unknown is a number the validator cannot scope.
    """
    reasons: list[str] = []
    confidence = Decimal("1.000")

    if result.reconciliation_status == NOT_ATTEMPTED:
        confidence -= PENALTY_NO_TOC
        reasons.append("no per-note table of contents was available to reconcile against")
    elif result.reconciliation_status == MISMATCH:
        confidence -= PENALTY_TOC_MISMATCH
        reasons.append(result.reconciliation_detail)

    if not result.heading_reconciled:
        confidence -= PENALTY_NO_HEADING_CONFIRMATION
        reasons.append(f"headings did not confirm the count: {result.heading_detail}")

    if result.orphan_count:
        confidence -= PENALTY_PER_ORPHAN * result.orphan_count
        reasons.append(f"{result.orphan_count} child block(s) could not be attached")

    if result.flagged_for_review:
        confidence -= PENALTY_REVIEW_FLAG
        reasons.append(f"{len(result.flagged_for_review)} candidate(s) flagged for review")

    unresolved_tables = len(ownership.unresolved) if ownership else 0
    if unresolved_tables:
        confidence -= PENALTY_PER_UNRESOLVED_TABLE * unresolved_tables
        reasons.append(f"{unresolved_tables} table(s) could not be attributed to an owner")

    confidence = max(Decimal("0.000"), min(Decimal("1.000"), confidence)).quantize(Decimal("0.001"))

    status = _status_for(result, ownership)
    if status == COMPLETE and not reasons:
        reasons.append("every candidate classified and every child block attached")

    return ExtractionCompleteness(
        accession=result.accession,
        candidate_count=len(result.candidates),
        canonical_footnote_count=len(result.footnotes),
        child_block_count=result.child_block_count,
        attached_child_block_count=result.attached_count,
        orphan_count=result.orphan_count,
        excluded_section_count=len(result.excluded),
        review_flag_count=len(result.flagged_for_review),
        headings_parsed=len(result.headings),
        toc_expected_note_count=result.toc_expected_note_count,
        reconciliation_status=result.reconciliation_status,
        heading_reconciled=result.heading_reconciled,
        tables_total=ownership.total if ownership else 0,
        tables_owned_by_footnote=(ownership.count("CANONICAL_FOOTNOTE") if ownership else 0),
        tables_unresolved=unresolved_tables,
        extraction_status=status,
        confidence=confidence,
        reasons=tuple(reasons),
    )


def _status_for(result: CanonicalizationResult, ownership: Any | None = None) -> str:
    """The extraction verdict, in order of severity.

    Ordering matters: a filing with zero footnotes AND an orphan is FAILED, not PARTIAL, because
    the more fundamental failure is the one to report.
    """
    if not result.candidates:
        return FAILED
    if not result.footnotes:
        return FAILED
    if result.flagged_for_review:
        return REQUIRES_REVIEW
    if result.orphan_count:
        return PARTIAL
    if result.reconciliation_status == MISMATCH:
        return PARTIAL
    if ownership is not None and ownership.has_unresolved_footnote_tables:
        return PARTIAL
    return COMPLETE


def filing_footnote_status(completeness: ExtractionCompleteness, accepted_summaries: int) -> str:
    """The filing-level status the dashboard shows.

    COMPLETE requires one active accepted summary per canonical footnote. Summarization is
    Sprint 5, so every filing processed today resolves to PARTIAL — correctly. A filing whose
    extraction is flawless but which has no summaries has not delivered the product.
    """
    if completeness.extraction_status == FAILED:
        return FAILED
    if completeness.extraction_status == REQUIRES_REVIEW:
        return REQUIRES_REVIEW
    if accepted_summaries == 0:
        return NOT_STARTED if completeness.canonical_footnote_count == 0 else PARTIAL
    if accepted_summaries < completeness.canonical_footnote_count:
        return PARTIAL
    if completeness.extraction_status != COMPLETE:
        return PARTIAL
    return COMPLETE


def reconciliation_report(
    result: CanonicalizationResult, completeness: ExtractionCompleteness
) -> str:
    """A plain-text listing of every note and its attached child count.

    Plain text, not JSON: this is read by a person, and the LLM content boundary prohibits JSON in
    either direction for anything that could reach a model.
    """
    rule = "-" * 78
    lines = [
        rule,
        f"CANONICAL FOOTNOTES  {result.accession}",
        rule,
        f"{'#':>3}  {'note':<52}{'children':>9}",
    ]
    for index, note in enumerate(result.footnotes, start=1):
        children = len(result.children_of(note.role_uri))
        lines.append(f"{index:>3}. {note.title[:50]:<52}{children:>9}")

    lines += [
        rule,
        f"{'candidates':<34}{completeness.candidate_count}",
        f"{'canonical footnotes':<34}{completeness.canonical_footnote_count}",
        f"{'excluded item disclosures':<34}{completeness.excluded_section_count}",
        f"{'child blocks':<34}{completeness.child_block_count}",
        f"{'attached':<34}{completeness.attached_child_block_count}",
        f"{'orphans':<34}{completeness.orphan_count}",
        f"{'headings parsed':<34}{completeness.headings_parsed}",
        f"{'TOC reconciliation':<34}{completeness.reconciliation_status}",
        f"{'heading confirmation':<34}{'yes' if completeness.heading_reconciled else 'no'}",
        f"{'tables':<34}{completeness.tables_total}",
        f"{'  owned by a footnote':<34}{completeness.tables_owned_by_footnote}",
        f"{'  unresolved':<34}{completeness.tables_unresolved}",
        f"{'extraction status':<34}{completeness.extraction_status}",
        f"{'confidence':<34}{completeness.confidence}",
    ]
    if completeness.reasons:
        lines.append("")
        for reason in completeness.reasons:
            lines.append(f"  - {reason}")
    lines.append(rule)
    return "\n".join(lines)
