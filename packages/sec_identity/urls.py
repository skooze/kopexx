"""SEC URL construction.

This module is the only place in the repository permitted to build SEC URLs.

SEC-INVARIANT: the Archives host takes the unpadded issuer CIK; data.sec.gov takes the padded
form. See packages/sec_identity/cik.py.

HISTORICAL-FORMAT: an empty primary-document name must never be concatenated into a URL. SEC
answers the resulting bare folder URL with HTTP 200 and a directory listing, which a naive
fetcher will happily store as though it were the filing.
"""

from __future__ import annotations

from .accession import accession_dashed, accession_undashed
from .cik import cik_archive, cik_padded
from .errors import MissingPrimaryDocumentError

ARCHIVES_HOST = "https://www.sec.gov"
DATA_HOST = "https://data.sec.gov"
EFTS_HOST = "https://efts.sec.gov"


def submissions_url(cik: str | int) -> str:
    """Return the submissions API URL for an issuer (padded CIK)."""
    return f"{DATA_HOST}/submissions/CIK{cik_padded(cik)}.json"


def submissions_shard_url(shard_filename: str) -> str:
    """Return the URL for an overflow submissions shard from ``filings.files[]``.

    SEC-INVARIANT: filings.recent is capped at 1000 entries. Roughly a third of issuers have
    older filings that exist only in these shards. Reading only filings.recent silently
    truncates history.
    """
    return f"{DATA_HOST}/submissions/{shard_filename}"


def filing_folder_url(cik: str | int, accession: str) -> str:
    """Return the Archives folder URL for a filing (unpadded CIK, undashed accession)."""
    return f"{ARCHIVES_HOST}/Archives/edgar/data/{cik_archive(cik)}/{accession_undashed(accession)}"


def primary_document_url(cik: str | int, accession: str, primary_document: str) -> str:
    """Return the URL of a filing's primary document.

    Raises MissingPrimaryDocumentError when the primary document name is empty, which is the
    normal state for filings before roughly 2001.
    """
    if primary_document is None or not str(primary_document).strip():
        raise MissingPrimaryDocumentError(
            f"filing {accession_dashed(accession)} has no primary document; "
            "use complete_submission_url() for the pre-2001 era"
        )
    folder = filing_folder_url(cik, accession)
    return f"{folder}/{primary_document.strip()}"


def complete_submission_url(cik: str | int, accession: str) -> str:
    """Return the flat complete-submission text URL (unpadded CIK, DASHED accession).

    This is the only addressable object for pre-2001 filings and the fallback for any filing
    whose primary document name is missing.
    """
    return (
        f"{ARCHIVES_HOST}/Archives/edgar/data/{cik_archive(cik)}/{accession_dashed(accession)}.txt"
    )


def filing_xbrl_zip_url(cik: str | int, accession: str) -> str:
    """Return the per-filing XBRL bundle URL.

    For inline-XBRL filings this bundle contains the primary narrative document as well as the
    schema and all linkbases, at roughly one thirty-third the bytes of the complete submission
    text. It is the preferred acquisition object for the inline era.
    """
    dashed = accession_dashed(accession)
    folder = filing_folder_url(cik, accession)
    return f"{folder}/{dashed}-xbrl.zip"


def filing_index_json_url(cik: str | int, accession: str) -> str:
    """Return the filing folder index URL."""
    return f"{filing_folder_url(cik, accession)}/index.json"


def extracted_instance_url(cik: str | int, accession: str, primary_document: str) -> str:
    """Return the SEC-extracted XBRL instance URL derived from the primary document name.

    SEC publishes its own transformed instance alongside inline-XBRL filings, which removes any
    need for us to implement inline-XBRL transformation. The filename is the primary document
    stem with ``_htm.xml`` appended.
    """
    if primary_document is None or not str(primary_document).strip():
        raise MissingPrimaryDocumentError(
            "cannot derive extracted instance without a primary document name"
        )
    stem = primary_document.strip()
    stem = stem[:-4] if stem.lower().endswith(".htm") else stem
    return f"{filing_folder_url(cik, accession)}/{stem}_htm.xml"


def quarterly_index_url(year: int, quarter: int) -> str:
    """Return the compressed quarterly master index URL.

    The gzip form is roughly six times smaller than the .idx form for identical content.
    """
    if quarter not in (1, 2, 3, 4):
        raise ValueError(f"quarter must be 1-4, got {quarter}")
    return f"{ARCHIVES_HOST}/Archives/edgar/full-index/{year}/QTR{quarter}/master.gz"


def company_tickers_exchange_url() -> str:
    """Return the ticker-to-exchange mapping URL."""
    return f"{ARCHIVES_HOST}/files/company_tickers_exchange.json"
