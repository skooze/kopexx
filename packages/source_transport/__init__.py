"""Mechanical source-set assembly, local-first reuse, and intact-source compatibility.

WHAT THIS PACKAGE IS FOR. Between "a filing exists" and "a model can be asked about it" there is a
purely mechanical problem: work out which bytes the filer actually filed, prove the ones already
held are still the ones that were held, fetch only what is missing, decode what needs decoding
without losing a byte, and say whether the whole thing fits the selected model intact.

WHAT IT IS FORBIDDEN TO DO. It never decides what any member MEANS. It has no notion of MD&A, a
risk factor, a footnote, a financial statement, an exhibit or a signature block; no importance
ranking; no rule that one member covers the same ground as another. Every disposition it makes is
justified by a byte signature, a filename extension, an XML root namespace, or a field EDGAR
itself declared — and anything it cannot justify that way fails closed into the run plan.

The module it replaces did have those opinions, ruled a courtesy PDF redundant, and suppressed a
filed source range on that judgement. It was deleted for it (ADR-0017).
"""

from .assembly import (
    MemberFetcher,
    RefusingFetcher,
    assemble_source_set,
    load_complete_submission,
)
from .compatibility import (
    UNVERIFIED_TOKENS_PER_IMAGE,
    CompatibilityReport,
    assess,
    image_coverage_report,
)
from .decoding import DecodedText, declared_encoding, decode_source
from .dispositions import (
    COVERED_DISPOSITIONS,
    SEC_RENDERER_DESCRIPTION_PREFIX,
    SUBMITTED_DISPOSITIONS,
    MemberDisposition,
    disposition_for,
    image_format,
)
from .errors import (
    IncompatibleSourceSetError,
    SourceIntegrityError,
    SourceMemberMissingError,
    SourceTransportError,
    UnknownMemberRoleError,
)
from .inventory import (
    CompositeInventory,
    ManifestInventory,
    ObjectStoreInventory,
    SourceInventory,
    verify,
)
from .records import PreservedObject, SourceMember, SourceSet

__all__ = [
    "COVERED_DISPOSITIONS",
    "SEC_RENDERER_DESCRIPTION_PREFIX",
    "SUBMITTED_DISPOSITIONS",
    "UNVERIFIED_TOKENS_PER_IMAGE",
    "CompatibilityReport",
    "CompositeInventory",
    "DecodedText",
    "IncompatibleSourceSetError",
    "ManifestInventory",
    "MemberDisposition",
    "MemberFetcher",
    "ObjectStoreInventory",
    "PreservedObject",
    "RefusingFetcher",
    "SourceIntegrityError",
    "SourceInventory",
    "SourceMember",
    "SourceMemberMissingError",
    "SourceSet",
    "SourceTransportError",
    "UnknownMemberRoleError",
    "assemble_source_set",
    "assess",
    "declared_encoding",
    "decode_source",
    "disposition_for",
    "image_coverage_report",
    "image_format",
    "load_complete_submission",
    "verify",
]
