"""Typed errors for the model-directed multipart protocol.

EVERY ONE OF THESE DESCRIBES A STRUCTURAL FAILURE, NEVER A SEMANTIC JUDGEMENT. Nothing here can be
raised because a plan was shallow, a part was thin, a title was odd or a model divided a filing in
a way a person would not have. Those are review findings about a response somebody paid for, and
they reach the review UI attached to the exact bytes that produced them.

What DOES raise: a response that is not one YAML document at all, a plan that gives two parts the
same identifier, a part identifier that cannot safely become a storage token, a dependency cycle.
Those make the work unschedulable rather than unconvincing.
"""

from __future__ import annotations


class MultipartError(Exception):
    """Base class for every multipart-protocol failure."""


class EnvelopeUnreadableError(MultipartError):
    """A response is not one readable YAML 1.2 mapping.

    Deliberately NOT a reason to discard the response. The caller preserves the exact bytes first,
    records this as the finding, and the artifact still reaches review — it was billable and cannot
    be regenerated for free.
    """


class UnsafePartIdentifierError(MultipartError):
    """A model-created identifier cannot be carried safely.

    SECURITY-INVARIANT. A part identifier is chosen by a language model that has just read an
    untrusted filing. It is displayed escaped, it is never interpreted, and it never forms a
    storage key — but an identifier that is empty, unbounded in length, or carries control
    characters is refused outright rather than sanitised into something plausible.
    """


class PlanCycleError(MultipartError):
    """The declared part dependencies contain a cycle, so no order can satisfy them."""


class RecursionDepthExceededError(MultipartError):
    """A branch asked to decompose deeper than the configured operational limit.

    An OPERATIONAL safety limit, never a semantic one. It does not say the filing has no deeper
    structure; it says this system stops spending on that branch and asks a person.
    """

    def __init__(self, message: str, *, depth: int, limit: int) -> None:
        self.depth = depth
        self.limit = limit
        super().__init__(message)
