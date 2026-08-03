"""Validation of model output against the PRESERVED SOURCE BYTES.

Interpretation is the model's; proof is the backend's. This package is the proof half: it reads a
parsed artifact elastically, resolves every source reference it carries against the bytes SEC
published, computes generic numeric and coverage signals, and reports what it found.

It never grades a parse against another parse. rules.md section 21 rule 15 withdrew the
deterministic oracle for exactly that reason, and nothing here reintroduces one as a benchmark, a
hint, a fallback, a derived index or a fixture generator.

It never issues a COMPLETE verdict. What it measures are signals; the complete-content invariant
asks a stronger question than any of them answer, and rounding signals up to a completeness claim
is the false complete the invariant exists to forbid.
"""

from .errors import CoverageValidationError, ResponseUnreadableError
from .numbers import NumericSignals, extract_numbers
from .reader import (
    PROVISIONAL_ENVELOPE_KEYS,
    ParsedDocument,
    ParsedNode,
    SourceReference,
    read,
)
from .references import (
    AMBIGUITY_THRESHOLD,
    RESOLVED,
    ArtifactIndex,
    ReferenceOutcome,
    Resolution,
)
from .validator import ValidationResult, ValidationStatus, validate_response

__all__ = [
    "AMBIGUITY_THRESHOLD",
    "PROVISIONAL_ENVELOPE_KEYS",
    "RESOLVED",
    "ArtifactIndex",
    "CoverageValidationError",
    "NumericSignals",
    "ParsedDocument",
    "ParsedNode",
    "ReferenceOutcome",
    "Resolution",
    "ResponseUnreadableError",
    "SourceReference",
    "ValidationResult",
    "ValidationStatus",
    "extract_numbers",
    "read",
    "validate_response",
]
