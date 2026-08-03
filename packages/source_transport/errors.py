"""Typed errors for source-set assembly and intact-source compatibility."""

from __future__ import annotations


class SourceTransportError(Exception):
    """Base class for every source-transport failure."""


class SourceMemberMissingError(SourceTransportError):
    """A filed member could not be located locally and could not be fetched.

    Raised rather than assembling a source set without it. A source set missing a filed
    human-readable member is an incomplete source set, and sending one would break the
    complete-content invariant while looking like a successful run.
    """


class SourceIntegrityError(SourceTransportError):
    """A preserved object does not match its recorded byte count or SHA-256.

    The preserved original is authoritative (rules.md section 21 rule 3). A stored object whose
    hash has moved is not the artifact the record describes, and the only safe response is to
    refuse it and re-acquire, never to trust the bytes and update the hash.
    """


class UnknownMemberRoleError(SourceTransportError):
    """A filed member's transport role could not be determined from its bytes.

    FAILS CLOSED. The Phase 2 brief is explicit: an unknown role appears in the run plan and is
    not automatically submitted. Guessing in either direction is a defect — submitting it may
    exceed a limit with content no model can use, and dropping it silently loses filed content.
    """


class IncompatibleSourceSetError(SourceTransportError):
    """The intact source set does not fit the selected model.

    This is a RESULT, not a failure to work around. `INTACT_SOURCE_ONLY` is the authorized mode:
    nothing is truncated, sliced, projected, split or swapped to another model. The user picks a
    different model, or the pairing stays refused.
    """

    def __init__(
        self,
        message: str,
        *,
        source_set_bytes: int,
        estimated_input_tokens: int,
        model_context_tokens: int,
    ) -> None:
        self.source_set_bytes = source_set_bytes
        self.estimated_input_tokens = estimated_input_tokens
        self.model_context_tokens = model_context_tokens
        super().__init__(message)
