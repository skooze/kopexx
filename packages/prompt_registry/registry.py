"""Versioned prompts, loaded by identity and hash — never by whatever is on disk today.

WHAT THIS ENFORCES. rules.md section 10 puts prompts under `prompts/`, versioned, never inline in
application code. The Phase 2 brief adds the part that makes a version mean something: a prompt
version is never overwritten after it has been used, historical prompt evidence is never edited in
place, and a prompt change creates a NEW version.

THE HASH IS THE ENFORCEMENT. Every invocation records the prompt id, the version, the exact bytes
and their SHA-256. `load` re-hashes the file and refuses it if the bytes have moved from what the
manifest recorded. Editing an in-use prompt therefore fails at load, fails in the test suite, and
fails in CI — rather than quietly changing what a hundred stored invocations claim to have asked.

THE MANIFEST PATH IS SUPPLIED AND HAS NO DEFAULT. Same rule as the capability snapshot and the
qualifying-form set, for the same reason: a default path is how a stale artifact keeps answering
after the real one has moved.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from packages.llm_gateway import parse_yaml, require_mapping
from packages.storage import sha256_text

from .errors import (
    PromptFormatError,
    PromptIntegrityError,
    PromptNotFoundError,
)

_REQUIRED_KEYS = ("prompt_id", "version", "file", "sha256", "created", "status", "role")


@dataclass(frozen=True)
class PromptVersion:
    """One immutable prompt version, with its exact bytes and their hash."""

    prompt_id: str
    version: str
    filename: str
    sha256: str
    created: str
    status: str
    role: str
    text: str
    supersedes: str | None = None
    superseded_by: str | None = None
    note: str = ""

    @property
    def identity(self) -> str:
        """`prompt-id@version`. What a run record quotes and a reviewer compares."""
        return f"{self.prompt_id}@{self.version}"

    def to_mapping(self) -> dict[str, Any]:
        return {
            "prompt_id": self.prompt_id,
            "version": self.version,
            "sha256": self.sha256,
            "created": self.created,
            "status": self.status,
            "role": self.role,
            "supersedes": self.supersedes,
            "superseded_by": self.superseded_by,
        }


class PromptRegistry:
    """Every declared prompt version, verified against its recorded hash on load."""

    def __init__(self, versions: tuple[PromptVersion, ...]) -> None:
        self._versions = versions

    @classmethod
    def from_directory(
        cls, directory: str | Path, *, manifest_name: str = "versions.yaml"
    ) -> PromptRegistry:
        """Load a registry from a prompt directory, verifying every declared file.

        The directory is SUPPLIED. This class knows no path of its own.
        """
        root = Path(directory)
        manifest_path = root / manifest_name
        if not manifest_path.is_file():
            raise PromptNotFoundError(
                f"no prompt manifest at {manifest_path}; a prompt directory without a manifest "
                "has no way to prove a version was not edited after it was used"
            )
        document = require_mapping(parse_yaml(manifest_path.read_text(encoding="utf-8")))
        raw_prompts = document.get("prompts")
        if not isinstance(raw_prompts, list) or not raw_prompts:
            raise PromptFormatError("the prompt manifest declares no prompts")

        versions: list[PromptVersion] = []
        seen: set[str] = set()
        for index, raw in enumerate(raw_prompts):
            if not isinstance(raw, dict):
                raise PromptFormatError(f"prompts[{index}] is not a mapping")
            for key in _REQUIRED_KEYS:
                if key not in raw:
                    raise PromptFormatError(f"prompts[{index}] is missing required field {key!r}")

            filename = str(raw["file"])
            # SECURITY-INVARIANT: a manifest entry names a file INSIDE the prompt directory.
            # A manifest is tracked source rather than a request, and the guard is still here:
            # the one place a filename is concatenated into a path is the one place to check it.
            candidate = (root / filename).resolve()
            if not candidate.is_relative_to(root.resolve()):
                raise PromptFormatError(f"prompt file {filename!r} escapes the prompt directory")
            if not candidate.is_file():
                raise PromptNotFoundError(
                    f"the manifest declares {filename!r} and it is not on disk"
                )

            text = candidate.read_text(encoding="utf-8")
            actual = sha256_text(text)
            declared = str(raw["sha256"])
            if actual != declared:
                raise PromptIntegrityError(
                    f"{filename!r} hashes to {actual} and the manifest records {declared}. "
                    "A prompt version is never edited after it has been used: add a NEW version "
                    "with a new file and a new manifest entry, and leave this one as it is."
                )

            version = PromptVersion(
                prompt_id=str(raw["prompt_id"]),
                version=str(raw["version"]),
                filename=filename,
                sha256=actual,
                created=str(raw["created"]),
                status=str(raw["status"]),
                role=str(raw["role"]),
                text=text,
                supersedes=(str(raw["supersedes"]) if raw.get("supersedes") is not None else None),
                superseded_by=(
                    str(raw["superseded_by"]) if raw.get("superseded_by") is not None else None
                ),
                note=str(raw.get("note") or ""),
            )
            if version.identity in seen:
                raise PromptFormatError(
                    f"duplicate prompt version {version.identity!r}; an identity must resolve to "
                    "exactly one set of bytes"
                )
            seen.add(version.identity)
            versions.append(version)
        return cls(tuple(versions))

    @property
    def versions(self) -> tuple[PromptVersion, ...]:
        return self._versions

    def get(self, prompt_id: str, version: str) -> PromptVersion:
        """One exact version. There is no 'latest' shortcut here on purpose.

        A run records which prompt produced its response, and a caller that asked for 'the latest'
        has recorded nothing a later reader can reproduce. `active_for` exists for choosing one,
        and it returns a version with a number attached.
        """
        for candidate in self._versions:
            if candidate.prompt_id == prompt_id and candidate.version == version:
                return candidate
        known = ", ".join(v.identity for v in self._versions)
        raise PromptNotFoundError(f"no prompt version {prompt_id}@{version}; known: {known}")

    def active_for(self, role: str) -> PromptVersion:
        """The single ACTIVE prompt for a role, or a refusal naming what it found.

        Two active prompts for one role is a configuration error, not a preference to resolve.
        Picking between them here would make the choice invisible in the run record.
        """
        active = [v for v in self._versions if v.role == role and v.status == "ACTIVE"]
        if not active:
            raise PromptNotFoundError(f"no ACTIVE prompt is declared for the {role!r} role")
        if len(active) > 1:
            names = ", ".join(v.identity for v in active)
            raise PromptFormatError(
                f"{len(active)} ACTIVE prompts are declared for the {role!r} role: {names}. "
                "Exactly one may be active; choosing between them is a product decision."
            )
        return active[0]
