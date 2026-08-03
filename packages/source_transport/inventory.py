"""Local source-artifact inventory: what this project already holds, before EDGAR is contacted.

THE RULE THIS IMPLEMENTS. roadmap.md and the Phase 2 brief both spell out the same ten steps:
resolve identity as `(CIK, accession)`, query the local inventory, verify byte count, verify
SHA-256, reuse what is valid, fetch only what is missing, incomplete or hash-invalid, preserve
what is fetched, record provenance, and never silently overwrite a valid original.

`(CIK, ACCESSION)`, NOT ACCESSION ALONE. One accession legitimately belongs to more than one CIK:
`0001193125-16-520367` is a single 10-K/A co-registered by two filers, one submission, identical
bytes. And the accession PREFIX is the filing agent's CIK, not the issuer's — 361 of the 613
preserved corpus filings carry an agent prefix, so resolving ownership from it would produce 361
false mismatches.

VERIFICATION IS RE-COMPUTED, NEVER TRUSTED FROM BOOKKEEPING. A recorded hash proves what a
previous run saw; hashing the bytes on disk proves what this run will send. Those differ exactly
when something has gone wrong, which is the only case that matters.
"""

from __future__ import annotations

from typing import Protocol

from packages.sec_identity import accession_dashed, cik_padded
from packages.storage import ObjectStore, sha256_bytes

from .errors import SourceIntegrityError
from .records import PreservedObject


class SourceInventory(Protocol):
    """Whatever can answer 'do we already hold this member, byte-exactly?'."""

    def find(self, cik: str, accession: str, filename: str) -> PreservedObject | None:
        """The preserved object for one member, or None when it is not held."""

    def read(self, obj: PreservedObject) -> bytes:
        """The exact bytes of a preserved object."""

    def filenames(self, cik: str, accession: str) -> tuple[str, ...]:
        """Every member filename held for this filing. May be empty."""


def verify(obj: PreservedObject, data: bytes) -> None:
    """Refuse a preserved object whose bytes no longer match its record."""
    if len(data) != obj.byte_count:
        raise SourceIntegrityError(
            f"{obj.filename!r} is recorded as {obj.byte_count} bytes and is {len(data)} on disk; "
            "the preserved original is authoritative and a mismatch is re-acquired, not trusted"
        )
    actual = sha256_bytes(data)
    if actual != obj.sha256:
        raise SourceIntegrityError(
            f"{obj.filename!r} hashes to {actual} and is recorded as {obj.sha256}; "
            "the bytes on disk are not the artifact the record describes"
        )


class ObjectStoreInventory:
    """The production-shaped inventory: preserved members inside the object store.

    Keys follow `packages/filing_acquisition.storage_key`, so anything the acquirer preserved is
    found here without a second naming convention to keep in step.
    """

    def __init__(self, objects: ObjectStore) -> None:
        self._objects = objects

    @staticmethod
    def _prefix(cik: str, accession: str) -> str:
        # Deliberately built from the sec_identity helpers rather than reformatted here.
        # rules.md section 5 gives that package sole ownership of both normalisations.
        return f"filings/{cik_padded(cik)}/{accession_dashed(accession).replace('-', '')}/"

    def find(self, cik: str, accession: str, filename: str) -> PreservedObject | None:
        key = f"{self._prefix(cik, accession)}{filename}"
        if not self._objects.exists(key):
            return None
        data = self._objects.get_bytes(key)
        return PreservedObject(
            filename=filename,
            sha256=sha256_bytes(data),
            byte_count=len(data),
            source_url="",
            locator=key,
            acquired_at="",
            acquisition_method="object_store",
            reused=True,
        )

    def read(self, obj: PreservedObject) -> bytes:
        return self._objects.get_bytes(obj.locator)

    def filenames(self, cik: str, accession: str) -> tuple[str, ...]:
        prefix = self._prefix(cik, accession)
        return tuple(key[len(prefix) :] for key in self._objects.list_keys(prefix))


class ManifestInventory:
    """An inventory SUPPLIED as a mapping, for a corpus that already exists on disk.

    THE MANIFEST IS SUPPLIED AND HAS NO DEFAULT PATH. This package does not know where a research
    corpus lives, does not read a file of its own, and has no fallback — the same discipline the
    capability snapshot and the qualifying-form set are held to, and for the same reason: a
    fallback is how a stale inventory keeps answering after the real one has moved.

    The 613-filing research corpus preserved one object per filing, so this inventory answers for
    that object and returns nothing for the rest of the accession's members. That is the correct
    answer: the missing members are then FETCHED, which is exactly the path the raw-first rule
    describes and the path that has to be exercised rather than assumed.
    """

    def __init__(self, entries: dict[tuple[str, str], list[PreservedObject]]) -> None:
        self._entries = {
            (cik_padded(cik), accession_dashed(accession)): objects
            for (cik, accession), objects in entries.items()
        }

    def find(self, cik: str, accession: str, filename: str) -> PreservedObject | None:
        for obj in self._entries.get((cik_padded(cik), accession_dashed(accession)), ()):
            if obj.filename == filename:
                return obj
        return None

    def read(self, obj: PreservedObject) -> bytes:
        with open(obj.locator, "rb") as handle:
            data = handle.read()
        verify(obj, data)
        return data

    def filenames(self, cik: str, accession: str) -> tuple[str, ...]:
        entries = self._entries.get((cik_padded(cik), accession_dashed(accession)), ())
        return tuple(obj.filename for obj in entries)


class CompositeInventory:
    """Ask each inventory in order and take the first that holds the member.

    Order matters and is the caller's choice: the object store this project writes to comes first,
    the read-only research corpus second. A member acquired by a run is then found as the run's
    own preserved object rather than as a corpus entry it happens to duplicate.
    """

    def __init__(self, *inventories: SourceInventory) -> None:
        self._inventories = inventories

    def find(self, cik: str, accession: str, filename: str) -> PreservedObject | None:
        for inventory in self._inventories:
            found = inventory.find(cik, accession, filename)
            if found is not None:
                return found
        return None

    def read(self, obj: PreservedObject) -> bytes:
        """Try each inventory, and fall through on ANY inventory-specific failure.

        `ValueError` used to be missing from this list, and the omission was not theoretical. A
        `PreservedObject` from a manifest carries an ABSOLUTE filesystem path in `locator`, because
        that is what a manifest records. `ObjectStoreInventory.read` hands that to the object
        store, whose traversal guard correctly refuses an absolute key with `ValueError` — and the
        composite let that escape out of the FIRST inventory instead of falling through to the
        manifest inventory that actually held the bytes. The result was a crash at preflight where
        a lookup miss was meant to happen.
        """
        failures: list[str] = []
        for inventory in self._inventories:
            try:
                return inventory.read(obj)
            except (OSError, KeyError, ValueError) as error:
                failures.append(f"{type(inventory).__name__}: {type(error).__name__}: {error}")
                continue
        raise SourceIntegrityError(
            f"no inventory could read {obj.locator!r}: " + "; ".join(failures)
        )

    def filenames(self, cik: str, accession: str) -> tuple[str, ...]:
        seen: list[str] = []
        for inventory in self._inventories:
            for name in inventory.filenames(cik, accession):
                if name not in seen:
                    seen.append(name)
        return tuple(seen)
