"""The DERA mirror ledger.

Records what has been mirrored so a run is resumable and idempotent: re-running the mirror after
a complete pass downloads nothing.

IMPLEMENTATION STATUS: an in-memory and JSON-backed ledger is IMPLEMENTED for Sprint 1. The
PostgreSQL-backed ledger is PLANNED for Sprint 2, at which point this interface is retained and
only the backend changes.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from .discovery import DeraPackage


@dataclass(frozen=True)
class MirrorEntry:
    """Provenance for one mirrored package."""

    filename: str
    url: str
    cadence: str
    period: str
    sha256: str
    size_bytes: int
    retrieved_at: str
    storage_key: str
    format_version: str = "notes-v1"

    @classmethod
    def create(
        cls,
        package: DeraPackage,
        *,
        sha256: str,
        size_bytes: int,
        storage_key: str,
    ) -> MirrorEntry:
        return cls(
            filename=package.filename,
            url=package.url,
            cadence=package.cadence.value,
            period=package.period,
            sha256=sha256,
            size_bytes=size_bytes,
            retrieved_at=datetime.now(UTC).isoformat(),
            storage_key=storage_key,
        )


class MirrorLedger:
    """A resumable record of mirrored DERA packages."""

    def __init__(self, path: str | Path | None = None) -> None:
        self._path = Path(path) if path else None
        self._entries: dict[str, MirrorEntry] = {}
        if self._path and self._path.exists():
            self._load()

    def _load(self) -> None:
        assert self._path is not None
        raw = json.loads(self._path.read_text(encoding="utf-8") or "{}")
        self._entries = {k: MirrorEntry(**v) for k, v in raw.items()}

    def save(self) -> None:
        """Persist the ledger, if a path was configured."""
        if self._path is None:
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {k: asdict(v) for k, v in self._entries.items()}
        temporary = self._path.with_suffix(self._path.suffix + ".partial")
        temporary.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        temporary.replace(self._path)

    def has(self, package: DeraPackage) -> bool:
        """Return True when the package has already been mirrored."""
        return package.filename in self._entries

    def record(self, entry: MirrorEntry) -> None:
        """Record a completed download."""
        self._entries[entry.filename] = entry

    def get(self, filename: str) -> MirrorEntry | None:
        return self._entries.get(filename)

    def pending(self, packages: list[DeraPackage]) -> list[DeraPackage]:
        """Return only the packages not yet mirrored. This is what makes a run resumable."""
        return [p for p in packages if not self.has(p)]

    def __len__(self) -> int:
        return len(self._entries)

    @property
    def entries(self) -> dict[str, MirrorEntry]:
        return dict(self._entries)
