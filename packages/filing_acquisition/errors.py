"""Typed errors for filing acquisition."""

from __future__ import annotations


class FilingAcquisitionError(Exception):
    """Base class for every error raised by this package."""


class UnsupportedEraError(FilingAcquisitionError):
    """No acquisition strategy is implemented for this filing's era.

    Raised rather than falling back to a generic fetch. The eras differ in what a URL even means:
    a pre-2001 filing has no primary document, and constructing one returns a directory listing
    with HTTP 200. Guessing produces corruption that looks like success.
    """

    def __init__(self, accession: str, era: str) -> None:
        self.accession = accession
        self.era = era
        super().__init__(
            f"filing {accession} is era {era!r}, which has no acquisition strategy yet; "
            "Sprint 3 implements inline_xbrl only"
        )


class SubmissionFormatError(FilingAcquisitionError):
    """Bytes handed to the filed-document lister are not an EDGAR complete submission.

    Raised rather than returning an empty document list. SEC answers a bare folder URL with HTTP
    200 and a directory listing, and a throttle refusal is an HTML page with a 403 — both are
    bytes, both would list zero documents, and "zero documents" is a legitimate-looking answer.
    Failing loudly is the only way the caller can tell the three apart.
    """


class MissingPrimaryDocumentError(FilingAcquisitionError):
    """An inline-XBRL filing reported no primary document name."""

    def __init__(self, accession: str) -> None:
        self.accession = accession
        super().__init__(
            f"filing {accession} claims inline XBRL but has no primary document name; "
            "a URL built from an empty name returns a directory listing, not a filing"
        )
