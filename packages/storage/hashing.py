"""Content hashing for source provenance.

FINANCIAL-INVARIANT: every acquired source object records a SHA-256 so a later reprocessing run
can prove it read the same bytes the original run read.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import BinaryIO

CHUNK_BYTES = 1024 * 1024


def sha256_bytes(data: bytes) -> str:
    """Return the hex SHA-256 of a byte string."""
    return hashlib.sha256(data).hexdigest()


def sha256_text(text: str) -> str:
    """Return the hex SHA-256 of a string encoded as UTF-8."""
    return sha256_bytes(text.encode("utf-8"))


def sha256_stream(stream: BinaryIO) -> str:
    """Return the hex SHA-256 of a binary stream, read in bounded chunks."""
    digest = hashlib.sha256()
    while True:
        chunk = stream.read(CHUNK_BYTES)
        if not chunk:
            break
        digest.update(chunk)
    return digest.hexdigest()


def sha256_file(path: str | Path) -> str:
    """Return the hex SHA-256 of a file without loading it entirely into memory."""
    with open(path, "rb") as handle:
        return sha256_stream(handle)
