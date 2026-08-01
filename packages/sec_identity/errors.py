"""Typed errors for SEC identity normalization.

All identity failures raise from this module so callers can distinguish a malformed
identifier from a network or parsing problem.
"""

from __future__ import annotations


class SecIdentityError(ValueError):
    """Base class for every SEC identity failure."""


class InvalidCikError(SecIdentityError):
    """The supplied value is not a usable Central Index Key."""


class InvalidAccessionError(SecIdentityError):
    """The supplied value is not a usable accession number."""


class MissingPrimaryDocumentError(SecIdentityError):
    """A filing URL was requested without a primary document filename.

    HISTORICAL-FORMAT: filings before roughly 2001 carry an empty string (not null) in the
    submissions API ``primaryDocument`` field. Concatenating that empty string produces a bare
    folder URL which SEC answers with HTTP 200 and a directory listing. That is a silent data
    corruption, so we refuse to build the URL at all.
    """
