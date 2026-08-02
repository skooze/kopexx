"""Extraction failures."""

from __future__ import annotations


class ExtractionError(Exception):
    """Base class for footnote extraction failures."""


class ReportInventoryError(ExtractionError):
    """The renderer report inventory could not be read.

    Raised rather than returning an empty inventory: zero reports and an unparseable
    `FilingSummary.xml` are indistinguishable downstream, and the first would silently produce a
    filing with no footnotes.
    """


class PrimaryDocumentError(ExtractionError):
    """The primary document could not be read or carries no recognisable content."""
