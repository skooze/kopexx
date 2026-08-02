"""Canonicalization stages 1 through 5.

    1  candidate discovery          every report the renderer filed under `Notes`
    2  filing-item exclusion        remove Regulation S-K item disclosures
    3  role-URI attachment          attach child blocks to parents by role URI prefix
    4  TOC reconciliation           compare against the filing's own claimed note count
    5  heading reconciliation       independently confirm the count from the document

Stages 6 through 11 — presentation hierarchy, concept overlap, title similarity, filing order,
model adjudication, human review — are NOT implemented. They are fallbacks for children stage 3
leaves unattached, and against the four Apple filings stage 3 leaves none. Implementing a fallback
that never runs would be untested code carrying the authority of tested code.

A TIE IS NEVER BROKEN SILENTLY. When a child's role URI prefixes two parents, the child stays
unattached with both candidates recorded, rather than being assigned to the longer match or the
earlier one. An orphan is visible and fixable; a confidently wrong attachment is neither.

NO MODEL PARTICIPATES. Every decision here is a string comparison or a count.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from packages.footnote_extractor import (
    NoteHeading,
    RendererReport,
    ReportInventory,
    headings_are_contiguous,
    normalize_title,
)

from .exclusions import ExclusionList, ExclusionVerdict

PARSER_VERSION = "canonicalizer-1.0.0"

# Attachment by unique role-URI prefix is exact: either the child's role begins with the parent's
# or it does not. There is no scoring, so a match is certain.
ROLE_URI_CONFIDENCE = 1.0

RECONCILED = "RECONCILED"
MISMATCH = "MISMATCH"
NOT_ATTEMPTED = "NOT_ATTEMPTED"


@dataclass(frozen=True)
class CandidateNote:
    """A stage-1 candidate, carrying its stage-2 verdict."""

    report: RendererReport
    verdict: ExclusionVerdict

    @property
    def role_uri(self) -> str | None:
        return self.report.role

    @property
    def title(self) -> str:
        return self.report.short_name or self.report.long_name or ""


@dataclass
class Attachment:
    """One child block's grouping decision, with everything needed to explain it later.

    Persisted on the CHILD, because stages 3 and 6 through 10 decide per child. Recording the
    audit only on the parent cannot answer "why was this block attached here", which is the exact
    question the audit exists to answer.
    """

    child: RendererReport
    parent_role_uri: str | None
    stage: int | None
    method: str | None
    confidence: float | None
    evidence: dict[str, Any]
    competing_candidates: list[dict[str, Any]] = field(default_factory=list)
    reason: str = ""

    @property
    def is_attached(self) -> bool:
        return self.parent_role_uri is not None


@dataclass
class CanonicalizationResult:
    """Everything the five stages produced for one filing."""

    accession: str
    run_id: uuid.UUID
    inventory_sha256: str

    candidates: list[CandidateNote] = field(default_factory=list)
    footnotes: list[CandidateNote] = field(default_factory=list)
    excluded: list[CandidateNote] = field(default_factory=list)
    flagged_for_review: list[CandidateNote] = field(default_factory=list)
    attachments: list[Attachment] = field(default_factory=list)
    headings: tuple[NoteHeading, ...] = ()

    toc_expected_note_count: int | None = None
    reconciliation_status: str = NOT_ATTEMPTED
    reconciliation_detail: str = ""
    heading_reconciled: bool = False
    heading_detail: str = ""
    unresolved: list[dict[str, Any]] = field(default_factory=list)
    decided_at: str = ""

    @property
    def child_block_count(self) -> int:
        return len(self.attachments)

    @property
    def attached_count(self) -> int:
        return sum(1 for a in self.attachments if a.is_attached)

    @property
    def orphan_count(self) -> int:
        return sum(1 for a in self.attachments if not a.is_attached)

    def children_of(self, role_uri: str | None) -> list[Attachment]:
        return [a for a in self.attachments if a.parent_role_uri == role_uri]

    def as_record(self) -> dict[str, Any]:
        return {
            "accession": self.accession,
            "run_id": str(self.run_id),
            "candidates": len(self.candidates),
            "canonical_footnotes": len(self.footnotes),
            "excluded": len(self.excluded),
            "flagged_for_review": len(self.flagged_for_review),
            "child_blocks": self.child_block_count,
            "attached": self.attached_count,
            "orphans": self.orphan_count,
            "headings_parsed": len(self.headings),
            "toc_expected_note_count": self.toc_expected_note_count,
            "reconciliation_status": self.reconciliation_status,
            "heading_reconciled": self.heading_reconciled,
            "unresolved": self.unresolved,
        }


# --- stage 1 -------------------------------------------------------------------------------


def discover_candidates(inventory: ReportInventory) -> list[RendererReport]:
    """Stage 1. Every report the renderer filed under menu category `Notes`.

    The navigation entry is already excluded by the inventory, which is why this returns 16 for
    Apple's FY2025 10-K rather than 17.
    """
    return list(inventory.candidates())


# --- stage 2 -------------------------------------------------------------------------------


def apply_exclusions(
    candidates: list[RendererReport], exclusions: ExclusionList
) -> list[CandidateNote]:
    """Stage 2. Classify each candidate as a footnote, an item disclosure, or unknown."""
    classified = []
    for report in candidates:
        verdict = exclusions.classify(
            title=report.short_name or report.long_name,
            role_uri=report.role,
        )
        classified.append(CandidateNote(report=report, verdict=verdict))
    return classified


# --- stage 3 -------------------------------------------------------------------------------


def attach_by_role_uri(
    footnotes: list[CandidateNote], children: list[RendererReport]
) -> list[Attachment]:
    """Stage 3. Attach each child to the parent whose role URI its own role URI extends.

    The mechanism: SEC's renderer derives a child's role URI from its parent's by appending a
    suffix, so `.../role/DebtDetails` extends `.../role/Debt`. That makes attachment an exact
    prefix test rather than a similarity score.

    Two guards, both of which produce an orphan rather than a guess:

    - A child with no role URI cannot be matched at all.
    - A child whose role prefixes more than one parent is ambiguous. Both candidates are recorded
      and the child stays unattached, because choosing the longest or the first would be a
      convention nobody agreed to and would look identical to a correct attachment afterwards.
    """
    parents = {note.role_uri: note for note in footnotes if note.role_uri}
    attachments = []

    for child in children:
        role = child.role
        if not role:
            attachments.append(
                Attachment(
                    child=child,
                    parent_role_uri=None,
                    stage=None,
                    method=None,
                    confidence=None,
                    evidence={"child_role_uri": None},
                    reason="child report carries no role URI; stage 3 cannot match it",
                )
            )
            continue

        matches = [parent for parent in parents if role.startswith(parent)]

        if len(matches) == 1:
            attachments.append(
                Attachment(
                    child=child,
                    parent_role_uri=matches[0],
                    stage=3,
                    method="role_uri",
                    confidence=ROLE_URI_CONFIDENCE,
                    evidence={"child_role_uri": role, "matched_parent_role_uri": matches[0]},
                    competing_candidates=[],
                    reason="unique role-URI prefix match",
                )
            )
            continue

        # Zero or many. Both are unresolved, and both are recorded with what was considered.
        attachments.append(
            Attachment(
                child=child,
                parent_role_uri=None,
                stage=None,
                method=None,
                confidence=None,
                evidence={"child_role_uri": role, "prefix_match_count": len(matches)},
                competing_candidates=[
                    {"parent_role_uri": m, "parent_title": parents[m].title} for m in matches
                ],
                reason=(
                    "no parent role URI is a prefix of this child's"
                    if not matches
                    else "ambiguous: the child's role URI extends more than one parent; a tie is "
                    "not broken silently"
                ),
            )
        )

    return attachments


# --- stage 4 -------------------------------------------------------------------------------


def reconcile_against_toc(footnote_count: int, toc_expected: int | None) -> tuple[str, str]:
    """Stage 4. Compare the extracted count with what the filing's own contents claim.

    Returns `NOT_ATTEMPTED` when the filing lists no note index. That is the honest answer and it
    is not the same as `RECONCILED`: Apple's FY2025 10-K opens its notes section directly, with no
    per-note table of contents, so there is nothing to reconcile against. Reporting a match here
    would claim a confirmation that never happened.

    A mismatch never adjusts the extracted set. It records the claim and routes the filing to
    review.
    """
    if toc_expected is None:
        return NOT_ATTEMPTED, "the filing lists no per-note table of contents to reconcile against"
    if toc_expected == footnote_count:
        return RECONCILED, f"table of contents claims {toc_expected}; extraction found the same"
    return (
        MISMATCH,
        f"table of contents claims {toc_expected}; extraction found {footnote_count}. "
        "The extracted set is not adjusted to match.",
    )


# --- stage 5 -------------------------------------------------------------------------------


def reconcile_against_headings(
    footnotes: list[CandidateNote], headings: tuple[NoteHeading, ...]
) -> tuple[bool, str]:
    """Stage 5. Independently confirm the count, and supply displayed numbers and titles.

    This is a confirmation for a filing with renderer metadata and the primary mechanism for a
    pre-2009 filing that has none. Confirmation means the two counts agree AND the heading numbers
    run 1..N without a gap — a gap means a heading was missed or a false one matched, and either
    way the count cannot confirm anything.
    """
    if not headings:
        return False, "no note headings parsed from the primary document"
    if not headings_are_contiguous(headings):
        numbers = [h.number for h in headings]
        return False, f"heading numbers are not contiguous: {numbers}"
    if len(headings) != len(footnotes):
        return (
            False,
            f"{len(headings)} headings parsed against {len(footnotes)} canonical footnotes",
        )
    return True, f"{len(headings)} headings confirm {len(footnotes)} canonical footnotes"


def match_headings_to_footnotes(
    footnotes: list[CandidateNote], headings: tuple[NoteHeading, ...]
) -> dict[str, NoteHeading]:
    """Map each footnote's role URI to the heading that displays it.

    Matched by normalized title first, then by filed order for anything left over. Order alone
    would be fragile if the renderer and the document disagreed; title alone would fail on the
    typographic differences between them, which is why normalization exists.
    """
    matched: dict[str, NoteHeading] = {}
    remaining = list(headings)

    for note in footnotes:
        if not note.role_uri:
            continue
        target = normalize_title(note.title)
        for heading in list(remaining):
            if heading.normalized_title == target:
                matched[note.role_uri] = heading
                remaining.remove(heading)
                break

    unmatched_notes = [n for n in footnotes if n.role_uri and n.role_uri not in matched]
    for note, heading in zip(unmatched_notes, remaining, strict=False):
        if note.role_uri:
            matched[note.role_uri] = heading

    return matched


# --- the pipeline --------------------------------------------------------------------------


def canonicalize(
    *,
    accession: str,
    inventory: ReportInventory,
    headings: tuple[NoteHeading, ...],
    exclusions: ExclusionList,
    toc_expected_note_count: int | None = None,
) -> CanonicalizationResult:
    """Run stages 1 through 5 over one filing."""
    result = CanonicalizationResult(
        accession=accession,
        run_id=uuid.uuid4(),
        inventory_sha256=inventory.source_sha256,
        headings=headings,
        toc_expected_note_count=toc_expected_note_count,
    )

    candidates = discover_candidates(inventory)
    classified = apply_exclusions(candidates, exclusions)
    result.candidates = classified

    for candidate in classified:
        if candidate.verdict.is_excluded:
            result.excluded.append(candidate)
        elif candidate.verdict.needs_review:
            result.flagged_for_review.append(candidate)
            result.unresolved.append(
                {
                    "kind": "unknown_namespace",
                    "title": candidate.title,
                    "role_uri": candidate.role_uri,
                    "reason": "namespace not recognised by the exclusion definition",
                }
            )
        else:
            result.footnotes.append(candidate)

    result.attachments = attach_by_role_uri(result.footnotes, list(inventory.child_blocks()))
    for attachment in result.attachments:
        if not attachment.is_attached:
            result.unresolved.append(
                {
                    "kind": "orphan_child_block",
                    "child": attachment.child.short_name,
                    "child_role_uri": attachment.child.role,
                    "candidates": attachment.competing_candidates,
                    "reason": attachment.reason,
                    "failed_stages": [3],
                }
            )

    result.reconciliation_status, result.reconciliation_detail = reconcile_against_toc(
        len(result.footnotes), toc_expected_note_count
    )
    result.heading_reconciled, result.heading_detail = reconcile_against_headings(
        result.footnotes, headings
    )
    result.decided_at = datetime.now(UTC).isoformat()
    return result
