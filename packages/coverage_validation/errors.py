"""Typed errors for validation of model output."""

from __future__ import annotations


class CoverageValidationError(Exception):
    """Base class for every validation failure."""


class ResponseUnreadableError(CoverageValidationError):
    """The response could not be read as a structured document at all.

    RAISED ONLY BY THE READER, NEVER BY THE VALIDATOR. A response that will not parse is a
    VALIDATION RESULT, not an exception: it was bought, its exact bytes are preserved, it is shown
    raw in the review UI, and a person decides whether the prompt or the model is at fault. The
    validator catches this and records it.
    """
