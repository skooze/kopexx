"""Typed errors for the prompt registry."""

from __future__ import annotations


class PromptRegistryError(Exception):
    """Base class for every prompt-registry failure."""


class PromptNotFoundError(PromptRegistryError):
    """A declared prompt file, manifest or version is absent."""


class PromptFormatError(PromptRegistryError):
    """The prompt manifest is malformed, or declares an ambiguous configuration."""


class PromptIntegrityError(PromptRegistryError):
    """A prompt file's bytes no longer match the hash the manifest recorded.

    THIS IS THE IMMUTABILITY GUARD AND IT IS NOT ADVISORY. Every stored invocation records the
    prompt version it used. Editing that version in place would retroactively change what all of
    them claim to have asked, and nothing downstream could detect it. A prompt change is a new
    file, a new manifest entry and a new version number.
    """
