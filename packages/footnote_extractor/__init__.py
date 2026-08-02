"""Extract footnote candidates, child disclosure blocks, and note headings from a filing.

OWNS: the report inventory, candidate discovery, child-block extraction, source ordering, source
identifiers, evidence-preserving text normalization, and heading parsing.

DOES NOT OWN: grouping policy. Which candidate is a footnote, which child attaches to which
parent, and whether a filing is complete are decided in `packages/footnote_canonicalizer`. This
package reports what the filing contains; it takes no position on what it means.
"""

from .errors import ExtractionError, PrimaryDocumentError, ReportInventoryError
from .headings import (
    NoteHeading,
    document_lines,
    headings_are_contiguous,
    normalize_title,
    parse_headings,
    read_headings,
)
from .inventory import (
    CHILD_CATEGORIES,
    NOTES_CATEGORY,
    RendererReport,
    ReportInventory,
    read_inventory,
)
from .presentation import (
    PresentationLinkbase,
    PresentationLinkbaseError,
    RolePresentation,
    parse_presentation,
    read_presentation_from_package,
)
from .tagged_blocks import (
    TaggedSpan,
    find_tagged_spans,
    innermost_span_at,
    resolve_continuations,
    text_block_spans,
)

__all__ = [
    "CHILD_CATEGORIES",
    "NOTES_CATEGORY",
    "ExtractionError",
    "NoteHeading",
    "PrimaryDocumentError",
    "RendererReport",
    "ReportInventory",
    "PresentationLinkbase",
    "PresentationLinkbaseError",
    "ReportInventoryError",
    "RolePresentation",
    "TaggedSpan",
    "document_lines",
    "find_tagged_spans",
    "innermost_span_at",
    "headings_are_contiguous",
    "normalize_title",
    "parse_headings",
    "read_headings",
    "parse_presentation",
    "read_inventory",
    "resolve_continuations",
    "read_presentation_from_package",
    "text_block_spans",
]
