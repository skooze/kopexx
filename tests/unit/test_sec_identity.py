"""SEC identity normalization tests.

These cover the traps documented in docs/sec/issuer-identity.md: inverted CIK padding between
SEC host families, dual accession forms inside one URL family, the filing-agent accession prefix,
and the empty pre-2001 primary document.
"""

from __future__ import annotations

import pytest

from packages.sec_identity import (
    InvalidAccessionError,
    InvalidCikError,
    MissingPrimaryDocumentError,
    accession_dashed,
    accession_filer_prefix,
    accession_undashed,
    cik_archive,
    cik_padded,
    complete_submission_url,
    extracted_instance_url,
    filing_xbrl_zip_url,
    primary_document_url,
    quarterly_index_url,
    submissions_url,
)

APPLE_CIK = "0000320193"
APPLE_ACCESSION = "0000320193-25-000079"
APPLE_PRIMARY_DOC = "aapl-20250927.htm"


def test_cik_padded_form() -> None:
    """data.sec.gov requires the ten-digit zero-padded CIK."""
    assert cik_padded("320193") == "0000320193"
    assert cik_padded(320193) == "0000320193"
    assert cik_padded("0000320193") == "0000320193"
    assert cik_padded("CIK0000320193") == "0000320193"
    assert submissions_url(320193) == "https://data.sec.gov/submissions/CIK0000320193.json"


def test_cik_archive_form() -> None:
    """www.sec.gov/Archives requires the unpadded integer CIK.

    A padded CIK produces a 301 redirect and a wasted round trip against a rate limit measured
    in single-digit requests per second.
    """
    assert cik_archive("0000320193") == "320193"
    assert cik_archive(320193) == "320193"
    assert cik_archive("CIK0000320193") == "320193"


@pytest.mark.parametrize("bad", ["", "  ", "abc", "-1", "0", "12a34", None])
def test_cik_rejects_invalid(bad: object) -> None:
    with pytest.raises((InvalidCikError, AttributeError, TypeError)):
        cik_padded(bad)  # type: ignore[arg-type]


def test_cik_rejects_boolean() -> None:
    """bool is an int subclass; True must not silently become CIK 1."""
    with pytest.raises(InvalidCikError):
        cik_padded(True)


def test_accession_dashed_form() -> None:
    """The dashed form is canonical for the submissions API, DERA, and our storage."""
    assert accession_dashed("000032019325000079") == APPLE_ACCESSION
    assert accession_dashed(APPLE_ACCESSION) == APPLE_ACCESSION


def test_accession_undashed_form() -> None:
    """The undashed form is used only as an Archives folder segment."""
    assert accession_undashed(APPLE_ACCESSION) == "000032019325000079"
    assert accession_undashed("000032019325000079") == "000032019325000079"


def test_accession_round_trips() -> None:
    assert accession_dashed(accession_undashed(APPLE_ACCESSION)) == APPLE_ACCESSION
    assert accession_undashed(accession_dashed("000032019325000079")) == "000032019325000079"


@pytest.mark.parametrize("bad", ["", "1234", "0000320193-25", "0000320193_25_000079", "x" * 18])
def test_accession_rejects_invalid(bad: str) -> None:
    with pytest.raises(InvalidAccessionError):
        accession_dashed(bad)


def test_archive_url_uses_issuer_cik() -> None:
    """The Archives path must carry the unpadded ISSUER CIK, not a padded or agent value."""
    url = primary_document_url(APPLE_CIK, APPLE_ACCESSION, APPLE_PRIMARY_DOC)
    assert url == (
        "https://www.sec.gov/Archives/edgar/data/320193/000032019325000079/aapl-20250927.htm"
    )
    assert "/data/0000320193/" not in url


def test_accession_prefix_not_used_as_issuer() -> None:
    """SEC-INVARIANT: the accession prefix can belong to a filing agent.

    Accession 0001140361-26-025622 appears in Apple's filing list but 0001140361 is the agent
    that transmitted it. Building the Archives path from that prefix 404s.
    """
    agent_accession = "0001140361-26-025622"
    assert accession_filer_prefix(agent_accession) == "0001140361"
    url = primary_document_url(APPLE_CIK, agent_accession, "doc.htm")
    assert "/data/320193/" in url, "path must use the issuer CIK"
    assert "/data/1140361/" not in url, "path must never use the filing agent CIK"


def test_empty_primary_document_rejected() -> None:
    """HISTORICAL-FORMAT: pre-2001 filings carry an empty primaryDocument.

    Concatenating it yields a bare folder URL that SEC answers with HTTP 200 and a directory
    listing, which a naive fetcher stores as though it were the filing.
    """
    for empty in ("", "   ", None):
        with pytest.raises(MissingPrimaryDocumentError):
            primary_document_url(APPLE_CIK, "0000320193-94-000016", empty)  # type: ignore[arg-type]


def test_complete_submission_url_uses_dashed_accession() -> None:
    """The flat text fallback keeps the dashes; the folder segment strips them."""
    url = complete_submission_url(320193, "0000320193-94-000016")
    assert url == ("https://www.sec.gov/Archives/edgar/data/320193/0000320193-94-000016.txt")


def test_xbrl_zip_url_mixes_both_accession_forms() -> None:
    """The folder segment is undashed while the filename inside it keeps dashes."""
    url = filing_xbrl_zip_url(320193, APPLE_ACCESSION)
    assert "/000032019325000079/" in url
    assert url.endswith("/0000320193-25-000079-xbrl.zip")


def test_extracted_instance_url_is_derivable() -> None:
    """SEC publishes its own transformed instance, removing any need to implement iXBRL."""
    url = extracted_instance_url(320193, APPLE_ACCESSION, APPLE_PRIMARY_DOC)
    assert url.endswith("/aapl-20250927_htm.xml")


def test_quarterly_index_uses_gzip() -> None:
    """The gzip index is roughly six times smaller than the .idx form for identical content."""
    assert quarterly_index_url(2026, 2).endswith("/full-index/2026/QTR2/master.gz")
    with pytest.raises(ValueError):
        quarterly_index_url(2026, 5)
