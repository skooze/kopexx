"""SEC DERA Financial Statement and Notes dataset: mirror, package selection, and fact loading."""

from .dimensions import NO_DIMENSIONS, DimensionIndex, parse_segments
from .discovery import (
    NOTES_LANDING_URL,
    DeraPackage,
    PackageCadence,
    classify_filename,
    discover_packages,
)
from .errors import DeraDiscoveryError, DeraError, DeraLedgerError
from .ledger import MirrorEntry, MirrorLedger
from .loader import (
    LoadError,
    LoadResult,
    ReadResult,
    advisory_lock_key,
    load_facts,
    read_package,
    verify_package,
)
from .normalize import (
    NormalizedFact,
    derive_period_start,
    minus_months,
    natural_key,
    normalize_fact,
    split_version,
)
from .reconcile import Check, Reconciliation, reconcile
from .registration import (
    FilingContext,
    RegistrationError,
    SubmissionRecord,
    read_submission,
    register_filing,
    register_mirror_ledger,
)
from .report import full_report, load_report, reconciliation_report, selection_report
from .selection import (
    OPTIONAL_MEMBERS,
    REQUIRED_MEMBERS,
    PackageSelectionError,
    SelectedPackage,
    accessions_in_package,
    assert_members_present,
    locate_filing,
    package_members,
)
from .tsv import TsvParseError, as_date, as_decimal, as_int, clean, count_rows, iter_rows
from .validate import Rejection, Violation, is_loadable, violations

__all__ = [
    "NOTES_LANDING_URL",
    "NO_DIMENSIONS",
    "OPTIONAL_MEMBERS",
    "REQUIRED_MEMBERS",
    "Check",
    "DeraDiscoveryError",
    "DeraError",
    "DeraLedgerError",
    "DeraPackage",
    "DimensionIndex",
    "FilingContext",
    "LoadError",
    "LoadResult",
    "MirrorEntry",
    "MirrorLedger",
    "NormalizedFact",
    "PackageCadence",
    "PackageSelectionError",
    "ReadResult",
    "Reconciliation",
    "RegistrationError",
    "Rejection",
    "SelectedPackage",
    "SubmissionRecord",
    "TsvParseError",
    "Violation",
    "accessions_in_package",
    "advisory_lock_key",
    "as_date",
    "as_decimal",
    "as_int",
    "assert_members_present",
    "classify_filename",
    "clean",
    "count_rows",
    "derive_period_start",
    "discover_packages",
    "full_report",
    "is_loadable",
    "iter_rows",
    "load_facts",
    "load_report",
    "locate_filing",
    "minus_months",
    "natural_key",
    "normalize_fact",
    "package_members",
    "parse_segments",
    "read_package",
    "read_submission",
    "reconcile",
    "reconciliation_report",
    "register_filing",
    "register_mirror_ledger",
    "selection_report",
    "split_version",
    "verify_package",
    "violations",
]
