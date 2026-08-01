"""DERA mirror integration test: discovery, storage, ledger, and resumability together."""

from __future__ import annotations

from pathlib import Path

import pytest

from packages.dera_notes import MirrorEntry, MirrorLedger, discover_packages
from packages.storage import FilesystemObjectStore, sha256_bytes

pytestmark = pytest.mark.integration

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def test_mirror_run_is_idempotent(tmp_path: Path) -> None:
    """A second run over an unchanged listing downloads nothing."""
    landing = (FIXTURES / "dera_landing_page.html").read_text(encoding="utf-8")
    store = FilesystemObjectStore(tmp_path / "objects")
    ledger = MirrorLedger(tmp_path / "ledger.json")

    packages = discover_packages(landing)
    downloads = 0

    def run_once() -> int:
        nonlocal downloads
        performed = 0
        for package in ledger.pending(packages):
            payload = f"fake-zip-for-{package.filename}".encode()
            stored = store.put_bytes(package.ledger_key, payload)
            ledger.record(
                MirrorEntry.create(
                    package,
                    sha256=stored.sha256,
                    size_bytes=stored.size_bytes,
                    storage_key=package.ledger_key,
                )
            )
            performed += 1
            downloads += 1
        ledger.save()
        return performed

    first = run_once()
    assert first == len(packages)

    second = run_once()
    assert second == 0, "an unchanged listing must produce no further downloads"
    assert downloads == len(packages)

    # Every recorded hash matches the stored bytes.
    for package in packages:
        entry = ledger.get(package.filename)
        assert entry is not None
        assert entry.sha256 == sha256_bytes(store.get_bytes(package.ledger_key))
        assert entry.storage_key == package.ledger_key
        assert entry.retrieved_at


def test_mirror_records_full_provenance(tmp_path: Path) -> None:
    landing = (FIXTURES / "dera_landing_page.html").read_text(encoding="utf-8")
    ledger = MirrorLedger(tmp_path / "ledger.json")
    package = discover_packages(landing)[0]
    ledger.record(
        MirrorEntry.create(package, sha256="a" * 64, size_bytes=10, storage_key=package.ledger_key)
    )
    entry = ledger.get(package.filename)
    assert entry is not None
    assert entry.url.startswith("https://www.sec.gov/")
    assert entry.period
    assert entry.cadence in {"monthly", "quarterly"}
    assert entry.format_version == "notes-v1"
