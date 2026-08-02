"""Group extracted reports into canonical financial-statement footnotes.

OWNS: item-disclosure exclusion, role-URI attachment, TOC reconciliation, heading reconciliation,
canonical identity, the attachment audit, competing candidates, confidence, completeness state,
and orphan reporting.

DOES NOT OWN: HTML table parsing, which is `packages/table_parser`, and model invocation, which
does not occur in this package at all. Every decision here is a string comparison or a count.
"""

from .completeness import (
    COMPLETE,
    FAILED,
    NOT_STARTED,
    PARTIAL,
    REQUIRES_REVIEW,
    ExtractionCompleteness,
    evaluate,
    filing_footnote_status,
    reconciliation_report,
)
from .exclusions import (
    DEFAULT_DEFINITION,
    ExclusionDefinitionError,
    ExclusionList,
    ExclusionVerdict,
)
from .ownership import (
    CANONICAL_FOOTNOTE,
    EXCLUDED_FILING_SECTION,
    FINANCIAL_STATEMENT,
    OTHER_FILING_REPORT,
    UNRESOLVED,
    OwnershipReconciliation,
    TableOwnership,
    classify_tables,
    ownership_report,
)
from .stages import (
    MISMATCH,
    NOT_ATTEMPTED,
    PARSER_VERSION,
    RECONCILED,
    Attachment,
    CandidateNote,
    CanonicalizationResult,
    apply_exclusions,
    attach_by_role_uri,
    canonicalize,
    discover_candidates,
    match_headings_to_footnotes,
    reconcile_against_headings,
    reconcile_against_toc,
)

__all__ = [
    "CANONICAL_FOOTNOTE",
    "COMPLETE",
    "EXCLUDED_FILING_SECTION",
    "FINANCIAL_STATEMENT",
    "DEFAULT_DEFINITION",
    "FAILED",
    "MISMATCH",
    "NOT_ATTEMPTED",
    "NOT_STARTED",
    "OTHER_FILING_REPORT",
    "PARSER_VERSION",
    "PARTIAL",
    "RECONCILED",
    "REQUIRES_REVIEW",
    "UNRESOLVED",
    "Attachment",
    "CandidateNote",
    "CanonicalizationResult",
    "ExclusionDefinitionError",
    "ExclusionList",
    "ExclusionVerdict",
    "ExtractionCompleteness",
    "OwnershipReconciliation",
    "TableOwnership",
    "apply_exclusions",
    "attach_by_role_uri",
    "canonicalize",
    "classify_tables",
    "discover_candidates",
    "evaluate",
    "filing_footnote_status",
    "match_headings_to_footnotes",
    "ownership_report",
    "reconcile_against_headings",
    "reconcile_against_toc",
    "reconciliation_report",
]
