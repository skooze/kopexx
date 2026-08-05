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


def _seeded(store: FilesystemObjectStore) -> None:
    """A store shaped like the evaluation store: manifests beside deep evidence subtrees."""
    store.put_text("runs/r1/run.yaml", "a")
    store.put_text("runs/r1/jobs/j1/job.yaml", "b")
    store.put_text("runs/r1/jobs/j1/tasks/t1/task.yaml", "c")
    store.put_text("runs/r1/jobs/j1/tasks/t1/evidence/response-visible.txt", "d")
    store.put_text("runs/r1/jobs/j1/tasks/t1/evidence/prompt.txt", "e")
    store.put_text("runs/r1/jobs/j1/tasks/t2/task.yaml", "f")
    store.put_text("runs/r1/jobs/j1/tasks/t2/evidence/envelope.yaml", "g")
    store.put_text("runs/r2/jobs/j9/tasks/t9/task.yaml", "h")


def test_a_prefixed_listing_returns_exactly_what_the_whole_store_walk_would(
    tmp_path: Path,
) -> None:
    """Starting the walk at the prefix is a speed fix and must not change the answer.

    The prefixed listing is compared against the definition it replaced — list everything, then
    filter — because that equivalence is the whole safety argument for not walking from the root.
    """
    store = FilesystemObjectStore(tmp_path)
    _seeded(store)
    for prefix in ("", "runs/", "runs/r1/jobs/j1/tasks/", "runs/r1/jobs/j1/tasks/t", "runs/r2/"):
        expected = sorted(k for k in store.list_keys("") if k.startswith(prefix))
        assert store.list_keys(prefix) == expected, prefix


def test_a_bounded_listing_never_descends_into_the_evidence_it_excludes(tmp_path: Path) -> None:
    """Depth 2 under the tasks prefix is `<task_id>/task.yaml` and nothing below it."""
    store = FilesystemObjectStore(tmp_path)
    _seeded(store)
    keys = store.list_keys("runs/r1/jobs/j1/tasks/", max_depth=2)
    assert keys == [
        "runs/r1/jobs/j1/tasks/t1/task.yaml",
        "runs/r1/jobs/j1/tasks/t2/task.yaml",
    ]
    # The evidence exists and is reachable; it is simply not enumerated to answer this question.
    assert "runs/r1/jobs/j1/tasks/t1/evidence/prompt.txt" in store.list_keys(
        "runs/r1/jobs/j1/tasks/"
    )


def test_a_prefix_may_not_escape_the_store_root(tmp_path: Path) -> None:
    """A prefix reaches a filesystem path, so it gets the same traversal guard a key does."""
    store = FilesystemObjectStore(tmp_path)
    _seeded(store)
    with pytest.raises(ValueError):
        store.list_keys("../../etc/passwd")


def test_an_unbounded_listing_still_returns_the_deep_keys(tmp_path: Path) -> None:
    """`max_depth=None` is the historical behaviour and must stay it."""
    store = FilesystemObjectStore(tmp_path)
    _seeded(store)
    assert len(store.list_keys("")) == 8
    assert len(store.list_keys("runs/r1/jobs/j1/tasks/")) == 5
