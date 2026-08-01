"""Object storage abstraction.

Raw filings, SEC datasets, and the exact model-visible request and response bodies are large,
immutable, and must survive schema changes, so they live in object storage rather than in the
database. The filesystem backend is used locally; an S3 backend implements the same interface in
production.

IMPLEMENTATION STATUS: FilesystemObjectStore IMPLEMENTED; S3ObjectStore PLANNED.
"""

from __future__ import annotations

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
        temporary.write_bytes(data)
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

    def clear(self) -> None:
        """Remove every stored object. Test support only."""
        if self._root.exists():
            shutil.rmtree(self._root)
        self._root.mkdir(parents=True, exist_ok=True)
