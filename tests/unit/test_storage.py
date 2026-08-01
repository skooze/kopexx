"""Object storage and hashing tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from packages.storage import FilesystemObjectStore, sha256_bytes, sha256_file, sha256_text


def test_sha256_is_stable_and_matches_known_value() -> None:
    assert sha256_text("") == ("e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855")
    assert sha256_bytes(b"fintek") == sha256_text("fintek")


def test_object_store_round_trip(tmp_path: Path) -> None:
    store = FilesystemObjectStore(tmp_path)
    stored = store.put_text("dera/notes/monthly/2026_06_notes.zip.meta", "content")
    assert store.exists("dera/notes/monthly/2026_06_notes.zip.meta")
    assert store.get_text("dera/notes/monthly/2026_06_notes.zip.meta") == "content"
    assert stored.sha256 == sha256_text("content")
    assert stored.size_bytes == len("content")
    assert stored.uri.startswith("file://")


def test_object_store_rejects_path_traversal(tmp_path: Path) -> None:
    """SECURITY-INVARIANT: a key must never escape the store root."""
    store = FilesystemObjectStore(tmp_path)
    for bad in ("../escape", "a/../../escape", "/etc/passwd"):
        with pytest.raises(ValueError):
            store.put_text(bad, "x")


def test_object_store_rejects_empty_key(tmp_path: Path) -> None:
    store = FilesystemObjectStore(tmp_path)
    with pytest.raises(ValueError):
        store.put_text("   ", "x")


def test_object_store_write_is_atomic(tmp_path: Path) -> None:
    """No partial object may be visible under the final key."""
    store = FilesystemObjectStore(tmp_path)
    store.put_bytes("a/b/c.bin", b"12345")
    assert not list(tmp_path.rglob("*.partial"))
    assert store.get_bytes("a/b/c.bin") == b"12345"


def test_sha256_file_matches_bytes(tmp_path: Path) -> None:
    target = tmp_path / "f.bin"
    target.write_bytes(b"abc" * 1000)
    assert sha256_file(target) == sha256_bytes(b"abc" * 1000)
