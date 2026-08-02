"""Table ownership, resolved deterministically.

THE CHAIN, every link published by the filer:

    table byte offset in the primary document
      -> innermost ix:nonNumeric span containing it        the filer's own note boundary
      -> that span's TextBlock concept
      -> the presentation roles that concept appears under  from the filing's _pre.xml
      -> a canonical footnote, or an excluded item disclosure, or a statement role
      -> footnote_id, or an explicit non-footnote classification

Nothing here uses proximity, document order, title similarity, or a byte-offset map. A table is
owned by the note the FILER wrapped it in, or it is not owned by a note at all.

WHY THIS MATTERS BEYOND TIDINESS. Sprint 5 summarizes one canonical footnote per job and validates
every number in the summary against that footnote's own source blocks and tables. A filing-level
table pool cannot distinguish a value in this note from one in another note, from a
financial-statement table, or from a table inside an excluded Item 408 disclosure. Ownership is
what makes footnote-scoped numeric validation possible at all.

FAIL CLOSED. A table whose owner cannot be established is `UNRESOLVED` with its full candidate
set recorded. It is never attached to the nearest note, and an unresolved table that belongs to a
canonical footnote prevents `COMPLETE`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from packages.footnote_extractor.presentation import PresentationLinkbase
from packages.footnote_extractor.tagged_blocks import TaggedSpan, innermost_span_at

from .stages import CanonicalizationResult

# The five outcomes. Every parsed table receives exactly one.
CANONICAL_FOOTNOTE = "CANONICAL_FOOTNOTE"
EXCLUDED_FILING_SECTION = "EXCLUDED_FILING_SECTION"
FINANCIAL_STATEMENT = "FINANCIAL_STATEMENT"
OTHER_FILING_REPORT = "OTHER_FILING_REPORT"
UNRESOLVED = "UNRESOLVED"

OWNERSHIP_METHOD = "tagged_text_block_role"


@dataclass
class TableOwnership:
    """One table's classification and the evidence for it."""

    external_id: str
    classification: str
    owner_role_uri: str | None = None
    owner_title: str | None = None
    concept: str | None = None
    candidate_roles: list[str] = field(default_factory=list)
    method: str | None = None
    reason: str = ""

    @property
    def is_footnote_owned(self) -> bool:
        return self.classification == CANONICAL_FOOTNOTE

    def as_evidence(self) -> dict[str, Any]:
        return {
            "classification": self.classification,
            "owner_role_uri": self.owner_role_uri,
            "concept": self.concept,
            "candidate_roles": self.candidate_roles,
            "method": self.method,
            "reason": self.reason,
        }


@dataclass
class OwnershipReconciliation:
    """The classification census for one filing."""

    accession: str
    ownership: list[TableOwnership] = field(default_factory=list)

    def count(self, classification: str) -> int:
        return sum(1 for o in self.ownership if o.classification == classification)

    @property
    def total(self) -> int:
        return len(self.ownership)

    @property
    def unresolved(self) -> list[TableOwnership]:
        return [o for o in self.ownership if o.classification == UNRESOLVED]

    @property
    def has_unresolved_footnote_tables(self) -> bool:
        """An unresolved table whose innermost span IS a note concept.

        A table outside every tagged block is a page header or a layout device, not a footnote
        table, and does not block completeness. One inside a note-level concept that could not be
        resolved to a role does.
        """
        return any(o.concept for o in self.unresolved)

    def as_record(self) -> dict[str, Any]:
        return {
            "accession": self.accession,
            "total": self.total,
            "canonical_footnote": self.count(CANONICAL_FOOTNOTE),
            "excluded_filing_section": self.count(EXCLUDED_FILING_SECTION),
            "financial_statement": self.count(FINANCIAL_STATEMENT),
            "other_filing_report": self.count(OTHER_FILING_REPORT),
            "unresolved": self.count(UNRESOLVED),
        }


def _role_index(result: CanonicalizationResult) -> tuple[dict[str, str], dict[str, str], set[str]]:
    """Role URI to (canonical footnote role, excluded role, child role) lookups.

    A child role resolves to the parent it was ATTACHED to in stage 3, so ownership inherits the
    decision that was already audited rather than re-deriving it by a second mechanism that could
    disagree.
    """
    footnote_roles = {n.role_uri: n.title for n in result.footnotes if n.role_uri}
    excluded_roles = {n.role_uri: n.title for n in result.excluded if n.role_uri}
    child_to_parent = {
        a.child.role: a.parent_role_uri
        for a in result.attachments
        if a.child.role and a.parent_role_uri
    }
    return footnote_roles, excluded_roles, set(child_to_parent)


def _resolve_role(
    candidate_roles: list[str],
    result: CanonicalizationResult,
) -> tuple[str | None, str, str]:
    """Map a concept's presentation roles to one canonical footnote role.

    Returns (footnote role, classification, reason). Every branch is explicit; there is no
    fallback that picks the first candidate.
    """
    footnote_roles, excluded_roles, _ = _role_index(result)
    child_to_parent = {
        a.child.role: a.parent_role_uri
        for a in result.attachments
        if a.child.role and a.parent_role_uri
    }

    direct = [r for r in candidate_roles if r in footnote_roles]
    if len(set(direct)) == 1:
        return (
            direct[0],
            CANONICAL_FOOTNOTE,
            "the concept is presented under a canonical footnote role",
        )

    # A child role — `...Tables`, `...Details` — resolves through the attachment stage 3 audited.
    through_child = {child_to_parent[r] for r in candidate_roles if r in child_to_parent}
    if len(through_child) == 1:
        return (
            through_child.pop(),
            CANONICAL_FOOTNOTE,
            "the concept is presented under a child role already attached to this footnote",
        )

    excluded = [r for r in candidate_roles if r in excluded_roles]
    if excluded and not direct and not through_child:
        return (
            None,
            EXCLUDED_FILING_SECTION,
            "the concept is presented only under an excluded item-disclosure role",
        )

    if len(set(direct)) > 1 or len(through_child) > 1:
        return (
            None,
            UNRESOLVED,
            "the concept is presented under more than one canonical footnote; a tie is not "
            "broken silently",
        )

    return None, UNRESOLVED, "no presentation role for this concept resolves to a footnote"


def _statement_verdict(
    table: Any,
    numeric_spans: list[TaggedSpan],
    concept_roles: dict[str, list[str]],
    statement_roles: set[str],
) -> TableOwnership | None:
    """Classify a table that sits outside every narrative block by the facts inside it.

    A financial statement is not wrapped in a TextBlock: the filer tags each figure individually
    with `ix:nonFraction`. So a statement table has no containing narrative span, and the
    deterministic signal is the concepts of the numeric facts within its own byte range — if those
    concepts are presented under a Statements role, the table is a statement.

    Without this the five primary statements landed in OTHER_FILING_REPORT alongside 31 cover and
    layout tables, which is not wrong exactly, but it loses the distinction Sprint 5's validator
    needs between a statement figure and a stray page element.
    """
    if table.source_offset is None or not table.raw_html:
        return None
    start = table.source_offset
    end = start + len(table.raw_html)

    concepts = {
        span.concept for span in numeric_spans if span.concept and start <= span.start < end
    }
    if not concepts:
        return None

    roles: set[str] = set()
    for concept in concepts:
        roles.update(concept_roles.get(concept, []))
    if not roles & statement_roles:
        return None

    return TableOwnership(
        external_id=table.external_id,
        classification=FINANCIAL_STATEMENT,
        concept=None,
        candidate_roles=sorted(roles & statement_roles),
        method=OWNERSHIP_METHOD,
        reason=(
            f"the table sits outside every narrative block and its {len(concepts)} tagged numeric "
            "fact(s) are presented under a statement role"
        ),
    )


def classify_tables(
    result: CanonicalizationResult,
    tables: list[Any],
    spans: list[TaggedSpan],
    linkbase: PresentationLinkbase,
    *,
    statement_roles: set[str] | None = None,
    numeric_spans: list[TaggedSpan] | None = None,
) -> OwnershipReconciliation:
    """Classify every parsed table for one filing.

    `tables` are `ParsedTable` objects carrying `source_offset`; the type is not imported to keep
    this module free of a dependency on the table parser, which it does not otherwise use.
    """
    reconciliation = OwnershipReconciliation(accession=result.accession)
    concept_roles = linkbase.concept_to_roles()
    statement_roles = statement_roles or set()
    numeric_spans = numeric_spans or []

    for table in tables:
        if table.source_offset is None:
            reconciliation.ownership.append(
                TableOwnership(
                    external_id=table.external_id,
                    classification=UNRESOLVED,
                    reason="the table has no recorded source offset",
                )
            )
            continue

        span = innermost_span_at(spans, table.source_offset)
        if span is None or not span.concept:
            # Outside every narrative block. Either a statement, which is tagged fact-by-fact, or
            # filing furniture: a cover layout, a page header, a signature block.
            statement = _statement_verdict(table, numeric_spans, concept_roles, statement_roles)
            reconciliation.ownership.append(
                statement
                or TableOwnership(
                    external_id=table.external_id,
                    classification=OTHER_FILING_REPORT,
                    method=OWNERSHIP_METHOD,
                    reason=(
                        "the table sits outside every narrative block and carries no tagged "
                        "numeric fact presented under a statement role"
                    ),
                )
            )
            continue

        candidates = concept_roles.get(span.concept, [])
        if not candidates:
            reconciliation.ownership.append(
                TableOwnership(
                    external_id=table.external_id,
                    classification=UNRESOLVED,
                    concept=span.concept,
                    method=OWNERSHIP_METHOD,
                    reason="the concept appears in no presentation role",
                )
            )
            continue

        if any(role in statement_roles for role in candidates) and not any(
            role in {n.role_uri for n in result.footnotes} for role in candidates
        ):
            reconciliation.ownership.append(
                TableOwnership(
                    external_id=table.external_id,
                    classification=FINANCIAL_STATEMENT,
                    concept=span.concept,
                    candidate_roles=candidates,
                    method=OWNERSHIP_METHOD,
                    reason="the concept is presented only under a statement role",
                )
            )
            continue

        role, classification, reason = _resolve_role(candidates, result)
        titles = {n.role_uri: n.title for n in result.footnotes if n.role_uri}
        reconciliation.ownership.append(
            TableOwnership(
                external_id=table.external_id,
                classification=classification,
                owner_role_uri=role,
                owner_title=titles.get(role) if role else None,
                concept=span.concept,
                candidate_roles=candidates,
                method=OWNERSHIP_METHOD,
                reason=reason,
            )
        )

    return reconciliation


def ownership_report(reconciliation: OwnershipReconciliation) -> str:
    """Plain-text classification census, per the LLM content boundary."""
    rule = "-" * 78
    lines = [
        rule,
        f"TABLE OWNERSHIP  {reconciliation.accession}",
        rule,
        f"{'total tables':<34}{reconciliation.total}",
        f"{'  canonical footnote':<34}{reconciliation.count(CANONICAL_FOOTNOTE)}",
        f"{'  excluded filing section':<34}{reconciliation.count(EXCLUDED_FILING_SECTION)}",
        f"{'  financial statement':<34}{reconciliation.count(FINANCIAL_STATEMENT)}",
        f"{'  other filing report':<34}{reconciliation.count(OTHER_FILING_REPORT)}",
        f"{'  unresolved':<34}{reconciliation.count(UNRESOLVED)}",
    ]
    for item in reconciliation.unresolved:
        lines.append(f"    UNRESOLVED {item.external_id}: {item.reason}")
        lines.append(f"      concept={item.concept} candidates={item.candidate_roles}")
    lines.append(rule)
    return "\n".join(lines)
