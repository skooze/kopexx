"""Filing acquisition tests.

Everything here runs against httpx MockTransport and a temporary object store. No network.
"""

from __future__ import annotations

import gzip
import io
import zipfile
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import httpx
import pytest

from packages.filing_acquisition import (
    MissingPrimaryDocumentError,
    UnsupportedEraError,
    acquire_filing,
    plan_inline_xbrl,
    storage_key,
)
from packages.sec_client import DirectoryListingError, FakeClock, SecHttpClient, SecRateLimiters
from packages.storage import FilesystemObjectStore

UA = "Kopexx Research contact@example.com"
ACCESSION = "0000320193-25-000079"
FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


@dataclass
class _Filing:
    """Stand-in for a DiscoveredFiling, so acquisition tests do not need discovery."""

    cik: str = "0000320193"
    accession: str = ACCESSION
    form: str = "10-K"
    filing_date: date = date(2025, 10, 31)
    report_date: date | None = date(2025, 9, 27)
    primary_document: str = "aapl-20250927.htm"
    is_xbrl: bool = True
    is_inline_xbrl: bool = True
    size_bytes: int | None = 9392337
    era: str = "inline_xbrl"
    source: str = "recent"


def _client(handler) -> SecHttpClient:
    return SecHttpClient(
        UA,
        limiters=SecRateLimiters(global_rps=1000.0, efts_rps=1000.0, clock=FakeClock()),
        transport=httpx.MockTransport(handler),
        sleeper=lambda seconds: None,
    )


def _zip_bytes() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("aapl-20250927_htm.xml", b"<xbrl/>" + b"x" * 2048)
    return buffer.getvalue()


def _serving_handler(request: httpx.Request) -> httpx.Response:
    """Answer every object in the inline-XBRL plan with plausible content."""
    path = request.url.path
    if path.endswith(".zip"):
        return httpx.Response(
            200, content=_zip_bytes(), headers={"content-type": "application/zip"}
        )
    if path.endswith(".htm"):
        body = b"<html><body>" + b"filing text " * 200 + b"</body></html>"
        return httpx.Response(200, content=body, headers={"content-type": "text/html"})
    body = b"<?xml version='1.0'?><root>" + b"x" * 2048 + b"</root>"
    return httpx.Response(200, content=body, headers={"content-type": "application/xml"})


# --- planning ---------------------------------------------------------------------------------


def test_plan_covers_every_object_sprint_four_needs() -> None:
    plan = plan_inline_xbrl("320193", ACCESSION, "aapl-20250927.htm")
    assert [role for role, _url, _name in plan] == [
        "primary_document",
        "xbrl_package",
        "extracted_instance",
        "filing_summary",
        "schema",
    ]


def test_plan_derives_the_sec_extracted_instance_rather_than_transforming_ixbrl() -> None:
    """SEC publishes its own extraction. We never implement iXBRL transformation."""
    plan = dict(
        (role, url) for role, url, _ in plan_inline_xbrl("320193", ACCESSION, "aapl-20250927.htm")
    )
    assert plan["extracted_instance"].endswith("aapl-20250927_htm.xml")


def test_plan_uses_the_unpadded_cik_in_archive_paths() -> None:
    """SEC-INVARIANT: data.sec.gov takes the padded CIK; Archives takes the unpadded integer."""
    plan = plan_inline_xbrl("320193", ACCESSION, "aapl-20250927.htm")
    for _role, url, _name in plan:
        assert "/edgar/data/320193/" in url
        assert "/0000320193/" not in url


def test_plan_refuses_an_empty_primary_document() -> None:
    """A URL built from an empty name returns a directory listing with HTTP 200."""
    with pytest.raises(MissingPrimaryDocumentError):
        plan_inline_xbrl("320193", "0000320193-94-000002", "")


def test_storage_key_is_scoped_by_issuer_cik_not_the_accession_prefix() -> None:
    """The accession prefix belongs to the filing agent, which is frequently another company."""
    key = storage_key("0000320193", ACCESSION, "aapl-20250927.htm")
    assert key == "filings/0000320193/000032019325000079/aapl-20250927.htm"


# --- acquisition ------------------------------------------------------------------------------


def test_acquisition_preserves_every_object_with_provenance(tmp_path: Path) -> None:
    store = FilesystemObjectStore(tmp_path / "objects")
    with _client(_serving_handler) as client:
        result = acquire_filing(client, store, _Filing(), workspace=tmp_path / "work")

    assert len(result.objects) == 5
    assert result.downloaded == 5 and result.reused == 0
    for obj in result.objects:
        assert len(obj.sha256) == 64
        assert obj.size_bytes > 0
        assert obj.retrieved_at
        assert store.exists(obj.storage_key)


def test_reacquisition_downloads_nothing_and_rehashes_what_is_stored(tmp_path: Path) -> None:
    """Idempotency is proven by content address, not by a bookkeeping flag."""
    store = FilesystemObjectStore(tmp_path / "objects")
    with _client(_serving_handler) as client:
        first = acquire_filing(client, store, _Filing(), workspace=tmp_path / "work")
        requests_after_first = client.request_count
        second = acquire_filing(client, store, _Filing(), workspace=tmp_path / "work")

    assert second.downloaded == 0 and second.reused == 5
    assert client.request_count == requests_after_first, "a reused object must cost no request"
    assert {o.sha256 for o in first.objects} == {o.sha256 for o in second.objects}


def test_acquisition_leaves_no_temporary_files(tmp_path: Path) -> None:
    workspace = tmp_path / "work"
    store = FilesystemObjectStore(tmp_path / "objects")
    with _client(_serving_handler) as client:
        acquire_filing(client, store, _Filing(), workspace=workspace)
    assert list(workspace.iterdir()) == [], "the workspace must be empty after a clean run"


def test_unsupported_era_raises_rather_than_guessing() -> None:
    """Guessing produces corruption that looks like success."""
    store = FilesystemObjectStore("unused")
    with _client(_serving_handler) as client:
        for era in ("standalone_xbrl", "html_no_xbrl", "pem_armored"):
            with pytest.raises(UnsupportedEraError, match=era):
                acquire_filing(client, store, _Filing(era=era), workspace="unused")


def test_directory_listing_is_rejected_even_where_html_is_expected(tmp_path: Path) -> None:
    """The primary document is HTML, so the blanket HTML guard is relaxed for it.

    A folder index is also HTML, and is exactly the corruption the guard exists to catch, so the
    directory-listing check still has to fire.
    """
    listing = (FIXTURES / "sec_directory_listing.html").read_bytes()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith(".htm"):
            return httpx.Response(200, content=listing, headers={"content-type": "text/html"})
        return _serving_handler(request)

    store = FilesystemObjectStore(tmp_path / "objects")
    with _client(handler) as client, pytest.raises(DirectoryListingError):
        acquire_filing(client, store, _Filing(), workspace=tmp_path / "work")


def test_gzipped_response_is_not_mistaken_for_a_truncated_download(tmp_path: Path) -> None:
    """SEC-INVARIANT: with Content-Encoding set, Content-Length is the COMPRESSED size.

    httpx hands back decompressed bytes, so comparing the two reports a truncation that did not
    happen. Every .htm and .xml SEC serves is gzipped; the DERA path never saw this because a
    .zip is not re-compressed.
    """
    body = b"<html><body>" + b"filing text " * 500 + b"</body></html>"
    compressed = gzip.compress(body)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith(".htm"):
            # Exactly what SEC sends: a gzipped body whose Content-Length describes the
            # COMPRESSED bytes, while the client sees the decompressed ones.
            return httpx.Response(
                200,
                content=compressed,
                headers={
                    "content-type": "text/html",
                    "content-length": str(len(compressed)),
                    "content-encoding": "gzip",
                },
            )
        return _serving_handler(request)

    assert len(compressed) < len(body), "the fixture must actually be compressed"

    store = FilesystemObjectStore(tmp_path / "objects")
    with _client(handler) as client:
        result = acquire_filing(client, store, _Filing(), workspace=tmp_path / "work")

    primary = next(o for o in result.objects if o.role == "primary_document")
    assert primary.size_bytes == len(body), "the decompressed body must be stored whole"


def test_result_record_is_complete_for_a_manifest(tmp_path: Path) -> None:
    store = FilesystemObjectStore(tmp_path / "objects")
    with _client(_serving_handler) as client:
        result = acquire_filing(client, store, _Filing(), workspace=tmp_path / "work")

    record = result.as_record()
    assert record["accession"] == ACCESSION
    assert record["object_count"] == 5
    assert record["total_bytes"] == result.total_bytes
    assert result.key_for("filing_summary") is not None
    assert result.key_for("nonexistent") is None
