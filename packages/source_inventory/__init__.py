"""Mechanical inventory of one filing's preserved bytes: members, text spans, tables, images.

THE DENOMINATOR PROBLEM THIS PACKAGE EXISTS TO SOLVE. Phase 2.1 could report that 352 of 364
model-emitted source references resolved against the preserved bytes. It could NOT report what
fraction of the filing that represented, because a source region a model never cited never entered
the count at all. A reference rate measures a model's own citations; it says nothing about what the
model left out in silence.

This package measures the filing instead of the parse. Every visible text span, every table
element, every filed image, counted from the bytes SEC published, before any model is invoked.

    IT IS A VALIDATION INSTRUMENT AND IT IS NOT AN INPUT FILTER. The selected parsing model still
    receives the complete compatible source set intact, in filed order, hash-verified, on every
    invocation. Nothing here narrows, projects, slices or reorders what is sent. rules.md section
    21 rules 6 and 7 are untouched, and visible-content projection remains unapproved.

    IT MEASURES AND DOES NOT ADJUDICATE. An offset, a length, a hash, an element name, a grid
    position and an image header field are transport facts, which rules.md invariant 14 permits.
    Whether a span is a risk factor, whether a table is a financial statement or a layout device,
    whether an image is a chart or a logo — none of that is decided here, or anywhere in backend
    code. The selected parsing model classifies with source evidence; a human reviewer may overrule
    it; this package supplies neither answer.
"""

from .errors import ImageUnreadableError, MarkupUnreadableError, SourceInventoryError
from .images import dimensions, media_type
from .inventory import build_inventory
from .markup import normalize_text, plain_text_spans, walk_markup
from .records import (
    NOT_VISIBLE,
    FilingInventory,
    HiddenReason,
    ImageRecord,
    MemberRecord,
    TableCell,
    TableElement,
    TextSpan,
)

__all__ = [
    "NOT_VISIBLE",
    "FilingInventory",
    "HiddenReason",
    "ImageRecord",
    "ImageUnreadableError",
    "MarkupUnreadableError",
    "MemberRecord",
    "SourceInventoryError",
    "TableCell",
    "TableElement",
    "TextSpan",
    "build_inventory",
    "dimensions",
    "media_type",
    "normalize_text",
    "plain_text_spans",
    "walk_markup",
]
