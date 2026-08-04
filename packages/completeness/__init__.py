"""The completeness ledger: what a parse accounted for, measured against the preserved bytes.

THE DEFECT THIS PACKAGE EXISTS TO CLOSE. Phase 2.1 could report `352/364 references resolved` and
`47/47 parts terminal` and could not say what fraction of the filing either number described. A
reference rate counts a model's own citations; a source region the model never mentioned never
entered the denominator. A terminal part count says scheduled work finished, not that the filing
was parsed. Both were read as completeness figures and neither was one.

WHAT IS MEASURED HERE, AND AGAINST WHAT.

    the denominator     `packages/source_inventory`, which counts every visible text span, every
                        table element and every filed image in the preserved bytes
    the required set    a human's classification of that inventory, versioned, for ONE filing
    the numerator       coverage claims whose two anchors both resolve in the preserved bytes,
                        plus structured tables that map to a real table element, plus resolved
                        source references
    the answer          four dispositions per item — COVERED, UNRESOLVED, HUMAN_EXCLUDED, and
                        SILENTLY_OMITTED — where the last one is the number that matters

NOTHING HERE ISSUES A COMPLETENESS VERDICT, AND THAT IS STRUCTURAL RATHER THAN POLITE. The strongest
value in `HumanReadiness` that backend code can set is `READY_FOR_REVIEW`. The gate's strongest
verdict is `MECHANICAL_COMPLETENESS_CANDIDATE`, which means the result carries enough evidence to be
reviewed by a person. `HUMAN_APPROVED_COMPLETE_FOR_THIS_FILING` is set by a reviewer and by nothing
else, and it is scoped to one filing, one source hash, one model, one model version, one region or
profile, one prompt version, one settings set and one protocol.

    `rules.md` invariant 13, section 3's COMPLETE-CONTENT-INVARIANT, and section 21 rules 1, 4 and
    5 all say the same thing from different directions: interpretation is the model's, proof is the
    backend's, and uncertainty produces PARTIAL or REVIEW_REQUIRED rather than a false complete.
"""

from .errors import BenchmarkTruthError, CompletenessError, LedgerInputError
from .gate import Condition, GateResult, evaluate
from .intervals import Interval, covered_length, gaps, merge, overlaps
from .ledger import (
    CompletenessLedger,
    CoverageClaim,
    Disposition,
    ItemLedger,
    ResolvedClaim,
    build_ledger,
    resolve_claims,
)
from .status import (
    ConvergenceState,
    HumanReadiness,
    ImageState,
    SerializationState,
    SourceCoverageState,
    TableState,
    TransportState,
)
from .tables import (
    CellOutcome,
    TableValidation,
    classify_cell,
    source_cell_text,
    table_source_interval,
    validate_table,
    validate_tables,
)
from .truth import (
    EXCLUDED_IMAGE,
    EXCLUDED_SPAN,
    EXCLUDED_TABLE,
    REQUIRED_IMAGE,
    REQUIRED_SPAN,
    REQUIRED_TABLE,
    BenchmarkTruth,
    ImageClassification,
    Judgement,
    SpanClassification,
    TableClassification,
    suggest,
)

__all__ = [
    "EXCLUDED_IMAGE",
    "EXCLUDED_SPAN",
    "EXCLUDED_TABLE",
    "REQUIRED_IMAGE",
    "REQUIRED_SPAN",
    "REQUIRED_TABLE",
    "BenchmarkTruth",
    "BenchmarkTruthError",
    "CellOutcome",
    "CompletenessError",
    "CompletenessLedger",
    "Condition",
    "ConvergenceState",
    "CoverageClaim",
    "Disposition",
    "GateResult",
    "HumanReadiness",
    "ImageClassification",
    "ImageState",
    "Interval",
    "ItemLedger",
    "Judgement",
    "LedgerInputError",
    "ResolvedClaim",
    "SerializationState",
    "SourceCoverageState",
    "SpanClassification",
    "TableClassification",
    "TableState",
    "TableValidation",
    "TransportState",
    "build_ledger",
    "classify_cell",
    "covered_length",
    "evaluate",
    "gaps",
    "merge",
    "overlaps",
    "resolve_claims",
    "source_cell_text",
    "suggest",
    "table_source_interval",
    "validate_table",
    "validate_tables",
]
