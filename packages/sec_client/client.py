"""SEC HTTP client.

The only component permitted to issue HTTP requests to an SEC host. Every request passes the
shared rate limiter, carries the validated User-Agent, and has its failures classified by the
throttle module rather than by status code alone.

SEC-INVARIANT: throttling is an HTTP 403 with an HTML body and no Retry-After header. A rate block
requires a full ten-minute cooldown; an undeclared-automation 403 is a configuration defect and is
never retried. See docs/sec/access-policy.md.

IMPLEMENTATION STATUS: IMPLEMENTED (Sprint 2). Single-process only: the rate limiter is
in-process, so exactly one client instance may run at a time. The Redis-backed distributed limiter
is required before multi-process ingestion because the SEC limit is aggregate across machines.
"""

from __future__ import annotations

import hashlib
import time
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from .errors import (
    DirectoryListingError,
    SecClientError,
    SecNotFoundError,
    SecRateLimitedError,
    SecTransientError,
    SecUndeclaredAutomationError,
)
from .rate_limiter import SecRateLimiters
from .throttle import looks_like_directory_listing, raise_for_403

CHUNK_BYTES = 1024 * 1024

# Response bodies below this size that claim to be a binary archive are almost certainly an error
# page rather than real content.
MIN_PLAUSIBLE_ARCHIVE_BYTES = 512

_HTML_SNIFF = (b"<!doctype html", b"<html", b"<HTML", b"<!DOCTYPE HTML")


@dataclass(frozen=True)
class FetchResult:
    """A completed download with the provenance required by the mirror ledger."""

    url: str
    status_code: int
    content_type: str
    content_length: int | None
    last_modified: str | None
    etag: str | None
    sha256: str
    size_bytes: int
    retrieved_at: str
    destination: str

    def as_record(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "status_code": self.status_code,
            "content_type": self.content_type,
            "content_length": self.content_length,
            "last_modified": self.last_modified,
            "etag": self.etag,
            "sha256": self.sha256,
            "size_bytes": self.size_bytes,
            "retrieved_at": self.retrieved_at,
            "destination": self.destination,
        }


class SecHttpClient:
    """Rate-limited, throttle-aware HTTP access to SEC hosts."""

    def __init__(
        self,
        user_agent: str,
        *,
        limiters: SecRateLimiters | None = None,
        cooldown_seconds: int = 600,
        connect_timeout: float = 10.0,
        read_timeout: float = 300.0,
        max_retries: int = 3,
        transport: httpx.BaseTransport | None = None,
        sleeper: Any = time.sleep,
    ) -> None:
        # SEC-INVARIANT: the User-Agent must already be validated by packages.configuration.
        # This client does not re-validate, but it will not construct without one.
        if not user_agent or not user_agent.strip():
            raise ValueError("SecHttpClient requires a validated User-Agent")
        self._limiters = limiters or SecRateLimiters()
        self._cooldown_seconds = cooldown_seconds
        self._max_retries = max_retries
        self._sleep = sleeper
        self._client = httpx.Client(
            headers={
                "User-Agent": user_agent,
                # Accept-Encoding matters: submissions JSON compresses roughly 5.8 to 1.
                "Accept-Encoding": "gzip, deflate",
            },
            timeout=httpx.Timeout(read_timeout, connect=connect_timeout),
            follow_redirects=True,
            transport=transport,
        )
        self.request_count = 0
        self.throttle_events: list[dict[str, Any]] = []

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> SecHttpClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # --- core request path --------------------------------------------------------------------

    def _acquire(self, url: str) -> None:
        host = url.split("//", 1)[-1].split("/", 1)[0]
        self._limiters.for_host(host).acquire()

    def _classify(self, response: httpx.Response, url: str) -> None:
        """Raise the appropriate typed error for a non-success response."""
        if response.status_code == 403:
            body = response.text[:8192]
            error = raise_for_403(body)
            self.throttle_events.append(
                {
                    "url": url,
                    "kind": type(error).__name__,
                    "reference_id": getattr(error, "reference_id", None),
                    "at": datetime.now(UTC).isoformat(),
                }
            )
            raise error
        if response.status_code == 404:
            raise SecNotFoundError(f"not found: {url}")
        if response.status_code >= 500:
            raise SecTransientError(f"server error {response.status_code}: {url}")
        if response.status_code >= 400:
            raise SecClientError(f"unexpected status {response.status_code}: {url}")

    def _handle_retryable(self, error: SecClientError, attempt: int, url: str) -> None:
        """Sleep appropriately, or re-raise when retries are exhausted or the error is permanent."""
        if not error.retryable or attempt >= self._max_retries:
            raise error
        if isinstance(error, SecRateLimitedError):
            # SEC-INVARIANT: recovery requires the rate to stay below threshold for ten full
            # minutes. Backoff starting at one second keeps us above threshold and extends the
            # block, so the only correct response is a hard cooldown.
            self._sleep(self._cooldown_seconds)
        else:
            self._sleep(min(2**attempt, 30))

    def head(self, url: str) -> httpx.Response:
        """Issue a rate-limited HEAD request."""
        for attempt in range(self._max_retries + 1):
            self._acquire(url)
            self.request_count += 1
            try:
                response = self._client.head(url)
                self._classify(response, url)
                return response
            except SecUndeclaredAutomationError:
                raise  # configuration defect; retrying only generates blocked traffic
            except SecClientError as error:
                self._handle_retryable(error, attempt, url)
            except httpx.HTTPError as error:
                self._handle_retryable(SecTransientError(str(error)), attempt, url)
        raise SecTransientError(f"retries exhausted: {url}")

    def get_text(self, url: str) -> str:
        """Fetch a text resource, such as the DERA listing page."""
        for attempt in range(self._max_retries + 1):
            self._acquire(url)
            self.request_count += 1
            try:
                response = self._client.get(url)
                self._classify(response, url)
                return response.text
            except SecUndeclaredAutomationError:
                raise
            except SecClientError as error:
                self._handle_retryable(error, attempt, url)
            except httpx.HTTPError as error:
                self._handle_retryable(SecTransientError(str(error)), attempt, url)
        raise SecTransientError(f"retries exhausted: {url}")

    def get_bytes(self, url: str) -> bytes:
        """Fetch a small binary resource into memory, such as a gzipped quarterly index.

        Use `download` for anything large enough to matter; this holds the whole body. It exists
        because the master index is read once and discarded, and writing it to disk only to parse
        and delete it adds a failure mode without adding a guarantee.
        """
        for attempt in range(self._max_retries + 1):
            self._acquire(url)
            self.request_count += 1
            try:
                response = self._client.get(url)
                self._classify(response, url)
                return response.content
            except SecUndeclaredAutomationError:
                raise
            except SecClientError as error:
                self._handle_retryable(error, attempt, url)
            except httpx.HTTPError as error:
                self._handle_retryable(SecTransientError(str(error)), attempt, url)
        raise SecTransientError(f"retries exhausted: {url}")

    # --- download path ------------------------------------------------------------------------

    def download(
        self,
        url: str,
        destination: str | Path,
        *,
        expect_zip: bool = False,
        expect_html: bool = False,
    ) -> FetchResult:
        """Stream a resource to disk, hashing as it goes, and validate before committing.

        The download writes to a temporary path and is renamed into place only after every
        assertion passes, so a partial or rejected download never appears under the final name.
        """
        target = Path(destination)
        target.parent.mkdir(parents=True, exist_ok=True)
        partial = target.with_suffix(target.suffix + ".partial")

        last_error: SecClientError | None = None
        for attempt in range(self._max_retries + 1):
            self._acquire(url)
            self.request_count += 1
            digest = hashlib.sha256()
            written = 0
            try:
                with self._client.stream("GET", url) as response:
                    if response.status_code >= 400:
                        response.read()
                        self._classify(response, url)
                    content_type = response.headers.get("content-type", "")
                    declared_length = response.headers.get("content-length")
                    # SEC-INVARIANT: when the response is content-encoded, Content-Length is the
                    # COMPRESSED byte count while httpx hands us decompressed bytes. Comparing the
                    # two reports a truncation that did not happen. The DERA path never saw this
                    # because SEC does not re-compress a .zip, but every .htm and .xml is gzipped.
                    if response.headers.get("content-encoding"):
                        declared_length = None
                    first_chunk = True
                    with open(partial, "wb") as handle:
                        for chunk in response.iter_bytes(CHUNK_BYTES):
                            if first_chunk:
                                self._assert_not_error_page(
                                    chunk, url, content_type, expect_zip, expect_html
                                )
                                first_chunk = False
                            handle.write(chunk)
                            digest.update(chunk)
                            written += len(chunk)

                self._assert_complete(written, declared_length, url)
                if expect_zip:
                    self._assert_valid_zip(partial, url)

                partial.replace(target)
                return FetchResult(
                    url=url,
                    status_code=response.status_code,
                    content_type=content_type,
                    content_length=int(declared_length) if declared_length else None,
                    last_modified=response.headers.get("last-modified"),
                    etag=response.headers.get("etag"),
                    sha256=digest.hexdigest(),
                    size_bytes=written,
                    retrieved_at=datetime.now(UTC).isoformat(),
                    destination=str(target),
                )
            except SecUndeclaredAutomationError:
                partial.unlink(missing_ok=True)
                raise
            except (DirectoryListingError, SecNotFoundError):
                partial.unlink(missing_ok=True)
                raise
            except SecClientError as error:
                partial.unlink(missing_ok=True)
                last_error = error
                self._handle_retryable(error, attempt, url)
            except httpx.HTTPError as error:
                partial.unlink(missing_ok=True)
                last_error = SecTransientError(str(error))
                self._handle_retryable(last_error, attempt, url)

        raise last_error or SecTransientError(f"retries exhausted: {url}")

    # --- content assertions -------------------------------------------------------------------

    @staticmethod
    def _assert_not_error_page(
        first_chunk: bytes,
        url: str,
        content_type: str,
        expect_zip: bool,
        expect_html: bool = False,
    ) -> None:
        """Reject an HTML error page or directory listing delivered with a 200 status.

        HISTORICAL-FORMAT: SEC answers a bare folder URL with HTTP 200 and an index page. Storing
        that as content is a silent corruption, so it is an error rather than a warning.

        A filing's primary document is itself HTML, so `expect_html` suppresses the blanket
        rejection. The directory-listing check still runs in that mode, because a folder index is
        also HTML and is exactly the failure this guard exists to catch.
        """
        head = first_chunk[:1024]
        looks_html = any(head.lstrip()[: len(m)].lower() == m.lower() for m in _HTML_SNIFF)
        if looks_html or "text/html" in content_type.lower():
            text = head.decode("utf-8", errors="replace")
            if looks_like_directory_listing(text, content_type):
                raise DirectoryListingError(f"directory listing returned for {url}")
            if not expect_html:
                raise SecClientError(f"HTML page returned where content was expected: {url}")
        if expect_zip and not head.startswith(b"PK"):
            raise SecClientError(f"response is not a ZIP archive (bad magic bytes): {url}")

    @staticmethod
    def _assert_complete(written: int, declared_length: str | None, url: str) -> None:
        """Reject a truncated download."""
        if written < MIN_PLAUSIBLE_ARCHIVE_BYTES:
            raise SecClientError(f"response of {written} bytes is implausibly small: {url}")
        if declared_length is not None:
            expected = int(declared_length)
            if written != expected:
                raise SecTransientError(
                    f"truncated download: got {written} bytes, expected {expected}: {url}"
                )

    @staticmethod
    def _assert_valid_zip(path: Path, url: str) -> None:
        """Reject a corrupt archive.

        testzip() reads every member's CRC, which is the only way to detect corruption that
        preserved the central directory.
        """
        try:
            with zipfile.ZipFile(path) as archive:
                if not archive.namelist():
                    raise SecClientError(f"ZIP archive contains no members: {url}")
                broken = archive.testzip()
                if broken is not None:
                    raise SecClientError(f"ZIP archive member failed CRC: {broken}: {url}")
        except zipfile.BadZipFile as error:
            raise SecClientError(f"invalid ZIP archive: {error}: {url}") from error
