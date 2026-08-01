"""SEC HTTP client tests.

Uses httpx MockTransport so the full request path, including rate limiting, throttle
classification, and content assertions, is exercised without touching the network.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import httpx
import pytest

from packages.sec_client import (
    DirectoryListingError,
    FakeClock,
    SecClientError,
    SecHttpClient,
    SecNotFoundError,
    SecRateLimiters,
    SecUndeclaredAutomationError,
)

UA = "FinTek Research contact@example.com"
FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def _client(handler, **kwargs) -> SecHttpClient:
    clock = FakeClock()
    return SecHttpClient(
        UA,
        limiters=SecRateLimiters(global_rps=1000.0, efts_rps=1000.0, clock=clock),
        transport=httpx.MockTransport(handler),
        sleeper=lambda seconds: None,
        **kwargs,
    )


def _zip_bytes(members: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, data in members.items():
            archive.writestr(name, data)
    return buffer.getvalue()


def test_client_requires_a_user_agent() -> None:
    with pytest.raises(ValueError):
        SecHttpClient("")


def test_client_sends_user_agent_and_accept_encoding() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(request.headers)
        return httpx.Response(200, text="ok")

    with _client(handler) as client:
        client.get_text("https://www.sec.gov/x")
    assert seen["user-agent"] == UA
    assert "gzip" in seen["accept-encoding"]


def test_rate_limit_403_is_classified_and_retried() -> None:
    """SEC-INVARIANT: throttling is a 403 with an HTML body, not a 429."""
    body = (FIXTURES / "sec_403_rate_limit.html").read_text()
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(403, text=body, headers={"content-type": "text/html"})
        return httpx.Response(200, text="recovered")

    with _client(handler) as client:
        assert client.get_text("https://www.sec.gov/x") == "recovered"
    assert calls["n"] == 2
    assert client.throttle_events[0]["kind"] == "SecRateLimitedError"
    assert client.throttle_events[0]["reference_id"] == "0.a1b2c3d4.1754067600.2f3e4d5c"


def test_undeclared_automation_403_is_never_retried() -> None:
    """A configuration defect must not generate further blocked traffic."""
    body = (FIXTURES / "sec_403_undeclared_automation.html").read_text()
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(403, text=body, headers={"content-type": "text/html"})

    with _client(handler) as client, pytest.raises(SecUndeclaredAutomationError):
        client.get_text("https://www.sec.gov/x")
    assert calls["n"] == 1, "an undeclared-automation 403 must not be retried"


def test_rate_limit_uses_the_full_cooldown_not_exponential_backoff() -> None:
    """SEC-INVARIANT: backoff from one second extends the block. Only a 600s pause recovers."""
    body = (FIXTURES / "sec_403_rate_limit.html").read_text()
    slept: list[float] = []
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(403, text=body, headers={"content-type": "text/html"})
        return httpx.Response(200, text="ok")

    client = SecHttpClient(
        UA,
        limiters=SecRateLimiters(global_rps=1000.0, efts_rps=1000.0, clock=FakeClock()),
        transport=httpx.MockTransport(handler),
        sleeper=slept.append,
        cooldown_seconds=600,
    )
    with client:
        client.get_text("https://www.sec.gov/x")
    assert slept == [600], f"expected a single 600 second cooldown, got {slept}"


def test_404_is_permanent() -> None:
    with (
        _client(lambda r: httpx.Response(404, text="nope")) as client,
        pytest.raises(SecNotFoundError),
    ):
        client.get_text("https://www.sec.gov/missing")


def test_download_rejects_directory_listing(tmp_path: Path) -> None:
    """HISTORICAL-FORMAT: a folder URL answers 200 with an index page."""
    body = (FIXTURES / "sec_directory_listing.html").read_bytes()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=body, headers={"content-type": "text/html"})

    with _client(handler) as client, pytest.raises(DirectoryListingError):
        client.download("https://www.sec.gov/Archives/edgar/data/320193/x/", tmp_path / "f.htm")
    assert not (tmp_path / "f.htm").exists()
    assert not list(tmp_path.glob("*.partial")), "a rejected download must leave nothing behind"


def test_download_rejects_html_where_zip_expected(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, content=b"<html><body>error</body></html>", headers={"content-type": "text/html"}
        )

    with _client(handler) as client, pytest.raises(SecClientError):
        client.download("https://www.sec.gov/x.zip", tmp_path / "x.zip", expect_zip=True)
    assert not (tmp_path / "x.zip").exists()


def test_download_rejects_truncated_response(tmp_path: Path) -> None:
    """A body shorter than its declared Content-Length is truncated, not merely small."""
    payload = _zip_bytes({"a.txt": b"x" * 4096})

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=payload,
            headers={"content-type": "application/zip", "content-length": str(len(payload) + 5000)},
        )

    with _client(handler) as client, pytest.raises(SecClientError, match="truncated"):
        client.download("https://www.sec.gov/x.zip", tmp_path / "x.zip", expect_zip=True)
    assert not (tmp_path / "x.zip").exists()


def test_download_rejects_corrupt_zip(tmp_path: Path) -> None:
    """A ZIP whose central directory survives but whose members fail CRC must be rejected."""
    good = bytearray(_zip_bytes({"a.txt": b"y" * 8192}))
    good[200:260] = b"\x00" * 60  # corrupt the compressed payload, not the directory

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=bytes(good), headers={"content-type": "application/zip"})

    with _client(handler) as client, pytest.raises(SecClientError):
        client.download("https://www.sec.gov/x.zip", tmp_path / "x.zip", expect_zip=True)
    assert not (tmp_path / "x.zip").exists()


def test_download_rejects_empty_zip(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, content=_zip_bytes({}) + b"\x00" * 600, headers={"content-type": "application/zip"}
        )

    with _client(handler) as client, pytest.raises(SecClientError):
        client.download("https://www.sec.gov/x.zip", tmp_path / "x.zip", expect_zip=True)


def test_successful_download_records_full_provenance(tmp_path: Path) -> None:
    import hashlib

    payload = _zip_bytes({"sub.tsv": b"adsh\tcik\n" + b"x" * 4096})

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=payload,
            headers={
                "content-type": "application/zip",
                "content-length": str(len(payload)),
                "last-modified": "Mon, 13 Jul 2026 11:26:24 GMT",
                "etag": '"abc123"',
            },
        )

    with _client(handler) as client:
        result = client.download("https://www.sec.gov/x.zip", tmp_path / "x.zip", expect_zip=True)

    assert result.sha256 == hashlib.sha256(payload).hexdigest()
    assert result.size_bytes == len(payload)
    assert result.content_length == len(payload)
    assert result.last_modified == "Mon, 13 Jul 2026 11:26:24 GMT"
    assert result.etag == '"abc123"'
    assert result.retrieved_at
    assert (tmp_path / "x.zip").read_bytes() == payload
    assert not list(tmp_path.glob("*.partial"))


def test_transient_error_is_retried_then_succeeds(tmp_path: Path) -> None:
    payload = _zip_bytes({"a.txt": b"z" * 2048})
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(503, text="unavailable")
        return httpx.Response(200, content=payload, headers={"content-type": "application/zip"})

    with _client(handler) as client:
        result = client.download("https://www.sec.gov/x.zip", tmp_path / "x.zip", expect_zip=True)
    assert calls["n"] == 3
    assert result.size_bytes == len(payload)


def test_efts_uses_its_own_slower_bucket() -> None:
    """efts returned 500 on the eighth of eight rapid requests; it gets a separate bucket."""
    clock = FakeClock()
    limiters = SecRateLimiters(global_rps=6.0, efts_rps=1.0, clock=clock)
    client = SecHttpClient(
        UA,
        limiters=limiters,
        transport=httpx.MockTransport(lambda r: httpx.Response(200, text="ok")),
        sleeper=lambda s: None,
    )
    with client:
        assert limiters.for_host("efts.sec.gov") is limiters.efts_bucket
        assert limiters.for_host("www.sec.gov") is limiters.global_bucket
        assert limiters.efts_bucket.requests_per_second == 1.0
        assert limiters.global_bucket.requests_per_second == 6.0


def test_requests_are_counted_for_observability() -> None:
    with _client(lambda r: httpx.Response(200, text="ok")) as client:
        client.get_text("https://www.sec.gov/a")
        client.get_text("https://www.sec.gov/b")
    assert client.request_count == 2
