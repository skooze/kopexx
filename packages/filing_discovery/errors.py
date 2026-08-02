"""Typed errors for filing discovery."""

from __future__ import annotations


class FilingDiscoveryError(Exception):
    """Base class for every error raised by this package."""


class SubmissionsShapeError(FilingDiscoveryError):
    """The submissions payload did not have the structure we require.

    Raised rather than silently returning fewer filings. A shape change at SEC that we absorb
    quietly would look identical to an issuer that simply filed less.
    """


class ReconciliationError(FilingDiscoveryError):
    """Discovery disagreed with the quarterly master index."""

    def __init__(self, cik: str, missing: tuple[str, ...]) -> None:
        self.cik = cik
        self.missing = missing
        super().__init__(
            f"{len(missing)} filing(s) present in the master index but absent from discovery "
            f"for CIK {cik}: {', '.join(missing[:10])}"
        )
