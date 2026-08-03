"""Fetch one filing member from EDGAR and preserve it byte-for-byte, with provenance.

WHY THIS LIVES HERE AND NOT IN `packages/source_transport`. rules.md section 5 gives this package
byte-exact acquisition, gives `packages/sec_client` all SEC traffic, and gives `packages/storage`
durable preservation. Source-set assembly needs a member fetched; it does not need an HTTP client,
a rate limiter or a store, and keeping all three out of it is what lets the entire assembly path
run in the test suite with no network at all.

FETCHED ONLY WHEN MISSING. The caller has already asked the local inventory and verified the hash
of anything it holds. Reaching this module means the member is genuinely absent, incomplete or
hash-invalid — the seventh step of the raw-first sequence, not the first.

A VALID ORIGINAL IS NEVER OVERWRITTEN. If the key already holds bytes, they are returned as they
are and no request is made. `force=True` exists for a caller that has proved the stored copy
invalid, and it says so at the call site rather than being the default.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from packages.sec_identity import accession_dashed, cik_archive, cik_padded, filing_folder_url
from packages.storage import ObjectStore, sha256_bytes

from .acquisition import storage_key


class SecMemberFetcher:
    """Retrieve one member of one accession from EDGAR and preserve it.

    Returns the provenance record and the exact bytes. The record's shape matches what
    `packages/source_transport` expects from its inventory, so a fetched member and a reused one
    are indistinguishable downstream except for the `reused` flag — which is the flag the UI shows
    when it reports `source already held, no SEC request`.
    """

    def __init__(self, client: Any, store: ObjectStore) -> None:
        self._client = client
        self._store = store
        self.requests_made = 0

    def fetch(
        self, cik: str, accession: str, filename: str, *, force: bool = False
    ) -> tuple[Any, bytes]:
        from packages.source_transport import PreservedObject  # local: avoids an import cycle

        padded = cik_padded(cik)
        dashed = accession_dashed(accession)
        key = storage_key(padded, dashed, filename)
        url = f"{filing_folder_url(cik_archive(padded), dashed)}/{filename}"

        if not force and self._store.exists(key):
            data = self._store.get_bytes(key)
            return (
                PreservedObject(
                    filename=filename,
                    sha256=sha256_bytes(data),
                    byte_count=len(data),
                    source_url=url,
                    locator=key,
                    acquired_at="",
                    acquisition_method="object_store",
                    reused=True,
                ),
                data,
            )

        data = self._client.get_bytes(url)
        self.requests_made += 1
        self._store.put_bytes(key, data)
        return (
            PreservedObject(
                filename=filename,
                sha256=sha256_bytes(data),
                byte_count=len(data),
                source_url=url,
                locator=key,
                acquired_at=datetime.now(UTC).isoformat(),
                acquisition_method="sec_https",
                reused=False,
            ),
            data,
        )
