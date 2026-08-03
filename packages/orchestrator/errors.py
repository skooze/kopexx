"""Typed errors for the orchestrator."""

from __future__ import annotations


class OrchestratorError(Exception):
    """Base class for every orchestration failure."""


class NoParsingModelError(OrchestratorError):
    """A run was requested without a parsing model.

    The parsing model is the ONLY required role. The other three may be left blank, and a blank
    role runs no stage. What is never permitted is filling a required role by inference — rules.md
    section 21 rule 8, and the reason the request object refuses rather than defaulting.
    """


class CeilingReachedError(OrchestratorError):
    """The next invocation would push cumulative spend past the authorized ceiling.

    The run STOPS here and reports the exact additional amount required. It does not shrink the
    request, drop a filing, pick a cheaper model or lower an output limit to fit — every one of
    those changes the measurement without saying so.
    """

    def __init__(self, message: str, *, required_usd: str, remaining_usd: str) -> None:
        self.required_usd = required_usd
        self.remaining_usd = remaining_usd
        super().__init__(message)


class FilingNotInCatalogError(OrchestratorError):
    """A requested filing is not in the local catalog.

    Its own error type, because it used to raise `NoParsingModelError` — which names an entirely
    different problem and would have been reported to a user as a model-selection failure while
    their model selection was perfectly fine.
    """


class StageNotAuthorizedError(OrchestratorError):
    """Something asked for a stage this phase does not run.

    Phase 2 exercises the parser only. The image, summary and analysis stages have selectors so
    that the progressive workflow is real, and invoking one is a scope violation rather than a
    feature that happens to be missing.
    """
