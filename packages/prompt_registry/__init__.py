"""Versioned, hash-verified prompts.

A prompt version that has been used is EVIDENCE: it produced a response somebody paid for. This
package is what makes editing one impossible by accident — the manifest records a SHA-256 per
version, loading re-hashes the file, and a mismatch is a hard failure rather than a warning.
"""

from .errors import (
    PromptFormatError,
    PromptIntegrityError,
    PromptNotFoundError,
    PromptRegistryError,
)
from .registry import PromptRegistry, PromptVersion

__all__ = [
    "PromptFormatError",
    "PromptIntegrityError",
    "PromptNotFoundError",
    "PromptRegistry",
    "PromptRegistryError",
    "PromptVersion",
]
