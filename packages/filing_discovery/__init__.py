"""Filing discovery: which 10-K and 10-Q filings an issuer has, before anything is downloaded."""

from .discovery import (
    ANNUAL_FORMS,
    QUARTERLY_FORMS,
    DiscoveredFiling,
    classify_era,
    discover_filings,
    is_amendment,
    is_covered_form,
    issuer_profile,
)
from .errors import FilingDiscoveryError, ReconciliationError, SubmissionsShapeError
from .reconcile import (
    parse_master_index,
    quarters_between,
    raise_if_incomplete,
    reconcile_against_master,
)

__all__ = [
    "ANNUAL_FORMS",
    "QUARTERLY_FORMS",
    "DiscoveredFiling",
    "FilingDiscoveryError",
    "ReconciliationError",
    "SubmissionsShapeError",
    "classify_era",
    "discover_filings",
    "is_amendment",
    "is_covered_form",
    "issuer_profile",
    "parse_master_index",
    "quarters_between",
    "raise_if_incomplete",
    "reconcile_against_master",
]
