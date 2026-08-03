"""Object storage abstraction.

Raw filings, SEC datasets, and the exact model-visible request and response bodies are large,
immutable, and must survive schema changes, so they live in object storage rather than in the
database. The filesystem backend is used locally; an S3 backend implements the same interface in
production.

IMPLEMENTATION STATUS: FilesystemObjectStore IMPLEMENTED; S3ObjectStore PLANNED.
"""

from __future__ import annotations

import os
import shutil
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from .hashing import sha256_bytes


@dataclass(frozen=True)
class StoredObject:
    """Provenance for one stored object."""

    key: str
    uri: str
    sha256: str
    size_bytes: int
    stored_at: datetime
    content_type: str | None = None


class ObjectStore(ABC):
    """Content-addressable-adjacent object storage keyed by explicit path."""

    @abstractmethod
    def put_bytes(self, key: str, data: bytes, *, content_type: str | None = None) -> StoredObject:
        """Store bytes under a key and return provenance."""

    @abstractmethod
    def get_bytes(self, key: str) -> bytes:
        """Retrieve bytes stored under a key."""

    @abstractmethod
    def exists(self, key: str) -> bool:
        """Return True when the key is present."""

    @abstractmethod
    def uri_for(self, key: str) -> str:
        """Return the durable URI for a key."""

    @abstractmethod
    def list_keys(self, prefix: str = "") -> list[str]:
        """Return every stored key beginning with ``prefix``, sorted.

        Added for the evaluation store, which has to enumerate runs and child jobs after a
        restart. Enumeration belongs on this interface rather than in a caller that walks the
        filesystem directly: rules.md section 5 makes this package the single home for durable
        object access, and a caller that reaches past it also reaches past the traversal guard.
        """

    def put_text(self, key: str, text: str, *, content_type: str = "text/plain") -> StoredObject:
        """Store UTF-8 text under a key."""
        return self.put_bytes(key, text.encode("utf-8"), content_type=content_type)

    def get_text(self, key: str) -> str:
        """Retrieve UTF-8 text stored under a key."""
        return self.get_bytes(key).decode("utf-8")


class FilesystemObjectStore(ObjectStore):
    """Local filesystem backend used for development and tests."""

    def __init__(self, root: str | Path) -> None:
        self._root = Path(root).resolve()
        self._root.mkdir(parents=True, exist_ok=True)

    def _path_for(self, key: str) -> Path:
        cleaned = key.strip()
        if not cleaned:
            raise ValueError("object key must not be empty")
        # SECURITY-INVARIANT: an object key is a relative path inside the store. An absolute key
        # is rejected rather than silently reinterpreted as relative, because a caller that
        # passed one has a defect and quietly rewriting it would hide that defect.
        if cleaned.startswith("/") or cleaned.startswith("\\"):
            raise ValueError(f"object key must be relative, got absolute path: {key!r}")
        candidate = (self._root / cleaned).resolve()
        # SECURITY-INVARIANT: a key must never escape the store root via traversal.
        if not candidate.is_relative_to(self._root):
            raise ValueError(f"object key escapes the store root: {key!r}")
        return candidate

    def put_bytes(self, key: str, data: bytes, *, content_type: str | None = None) -> StoredObject:
        path = self._path_for(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".partial")
        # WRITE, FLUSH, FSYNC, THEN RENAME. `write_bytes` alone flushes to the operating system
        # and returns; the bytes may still be in the page cache when the rename lands. A crash in
        # that window leaves a file that exists, has the right name, and is empty — which is worse
        # than a missing file, because a reader cannot tell it apart from a legitimately empty
        # object. The evaluation store records exact model responses that cost money to obtain and
        # cannot be regenerated for free, so the fsync is not optional here.
        with open(temporary, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        # Atomic replace so a killed writer never leaves a truncated object visible.
        temporary.replace(path)
        return StoredObject(
            key=key,
            uri=self.uri_for(key),
            sha256=sha256_bytes(data),
            size_bytes=len(data),
            stored_at=datetime.now(UTC),
            content_type=content_type,
        )

    def get_bytes(self, key: str) -> bytes:
        return self._path_for(key).read_bytes()

    def exists(self, key: str) -> bool:
        return self._path_for(key).exists()

    def uri_for(self, key: str) -> str:
        return f"file://{self._path_for(key)}"

    def list_keys(self, prefix: str = "") -> list[str]:
        """Every stored key under ``prefix``, sorted, with in-progress writes excluded.

        A `.partial` file is a write that has not reached its final name yet. Returning one would
        let a reader open bytes the writer has not finished, which is the exact failure the
        temporary-then-rename discipline exists to prevent.
        """
        keys = []
        for path in self._root.rglob("*"):
            if not path.is_file() or path.name.endswith(".partial"):
                continue
            key = path.relative_to(self._root).as_posix()
            if key.startswith(prefix):
                keys.append(key)
        return sorted(keys)

    def clear(self) -> None:
        """Remove every stored object. Test support only."""
        if self._root.exists():
            shutil.rmtree(self._root)
        self._root.mkdir(parents=True, exist_ok=True)
