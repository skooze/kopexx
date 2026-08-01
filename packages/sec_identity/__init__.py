"""SEC identity normalization: the single home for CIK, accession, and URL construction.

No other package may reimplement these transformations. See rules.md, section 5.
"""

from .accession import (
    accession_dashed,
    accession_filer_prefix,
    accession_undashed,
    is_valid_accession,
    parse_accession,
)
from .cik import cik_archive, cik_padded, cik_submissions_stem, parse_cik
from .errors import (
    InvalidAccessionError,
    InvalidCikError,
    MissingPrimaryDocumentError,
    SecIdentityError,
)
from .urls import (
    ARCHIVES_HOST,
    DATA_HOST,
    EFTS_HOST,
    company_tickers_exchange_url,
    complete_submission_url,
    extracted_instance_url,
    filing_folder_url,
    filing_index_json_url,
    filing_xbrl_zip_url,
    primary_document_url,
    quarterly_index_url,
    submissions_shard_url,
    submissions_url,
)

__all__ = [
    "ARCHIVES_HOST",
    "DATA_HOST",
    "EFTS_HOST",
    "InvalidAccessionError",
    "InvalidCikError",
    "MissingPrimaryDocumentError",
    "SecIdentityError",
    "accession_dashed",
    "accession_filer_prefix",
    "accession_undashed",
    "cik_archive",
    "cik_padded",
    "cik_submissions_stem",
    "company_tickers_exchange_url",
    "complete_submission_url",
    "extracted_instance_url",
    "filing_folder_url",
    "filing_index_json_url",
    "filing_xbrl_zip_url",
    "is_valid_accession",
    "parse_accession",
    "parse_cik",
    "primary_document_url",
    "quarterly_index_url",
    "submissions_shard_url",
    "submissions_url",
]
