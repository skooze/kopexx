"""Provider-neutral records for what a model can actually do.

NOTHING IN THIS MODULE NAMES A MODEL, A REGION, A PRICE OR A LIMIT. Every value arrives from the
reviewed capability snapshot the caller supplies. That is the same rule the form-family contract
established after a hardcoded allowlist in runtime source produced a confident, precise and
completely inverted conclusion about SEC form coverage — and it applies with more force here,
because a wrong model identifier or a wrong price is a wrong bill rather than a wrong query.

PROVIDER-NEUTRAL ON PURPOSE. Bedrock is where the first snapshot came from. Nothing below knows
that: there is no AWS import, no ARN, no region-name validation and no provider SDK anywhere in
this package, and an architecture test enforces the last one repository-wide.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from .errors import CapabilityContradictionError


class ModelRole(StrEnum):
    """The four roles the user selects independently.

    rules.md section 21 rule 8: no role inherits another's model. Only PARSING is required; the
    other three may be left blank, and a blank role runs NO stage rather than borrowing one.
    """

    PARSING = "parsing"
    IMAGE = "image"
    SUMMARY = "summary"
    ANALYSIS = "analysis"


class Availability(StrEnum):
    """Whether the provider offers this model to this account at all."""

    AVAILABLE = "AVAILABLE"
    NOT_FOUND_AS_NAMED = "NOT_FOUND_AS_NAMED"
    ACCESS_NOT_GRANTED = "ACCESS_NOT_GRANTED"
    UNAVAILABLE = "UNAVAILABLE"


class Mapping(StrEnum):
    """How cleanly a user-facing LABEL resolves to one provider model."""

    UNIQUE = "UNIQUE"
    AMBIGUOUS = "AMBIGUOUS"
    MISSING = "MISSING"


class SmokeTransport(StrEnum):
    """Whether a minimal invocation was accepted by the provider."""

    NOT_RUN = "NOT_RUN"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"


class SmokeInstruction(StrEnum):
    """Whether that invocation also followed the trivial instruction it was given.

    Tracked SEPARATELY from transport, because they answer different questions and conflating them
    loses the more important one. A model that returns something is reachable; whether the
    something matched a one-word instruction says nothing about reachability.
    """

    NOT_RUN = "NOT_RUN"
    EXACT = "EXACT"
    NONCOMPLIANT = "NONCOMPLIANT"


@dataclass(frozen=True)
class PriceInputs:
    """Official published price inputs, with the source and the date they were true.

    Decimal, not float. These are money, they are multiplied by token counts in the millions, and
    binary floating point is the wrong representation for a number that ends up on a bill.
    """

    input_per_1k: Decimal
    output_per_1k: Decimal
    currency: str
    source: str
    effective_date: str

    def cost(self, input_tokens: int, output_tokens: int) -> Decimal:
        """Cost for a known or bounded token count. Callers round for display, never for arithmetic."""
        if input_tokens < 0 or output_tokens < 0:
            raise ValueError("token counts cannot be negative")
        thousand = Decimal(1000)
        return (Decimal(input_tokens) / thousand) * self.input_per_1k + (
            Decimal(output_tokens) / thousand
        ) * self.output_per_1k


@dataclass(frozen=True)
class ModelCapability:
    """One user-facing candidate, as verified on a stated date.

    `multimodal` is validated against `image_verified` rather than trusted: see __post_init__.
    """

    label: str
    provider: str
    model_id: str
    model_name: str
    version_qualifier: str
    mapping: Mapping
    availability: Availability
    access_status: str
    # AN ORDERED TUPLE, NOT A SET, AND THE ORDER IS THE SNAPSHOT'S. Phase 2 routes a model
    # that is not offered in the preferred region to the FIRST region the reviewed snapshot
    # verified it in. A set would make that choice depend on hash ordering, which is a
    # different region on a different interpreter run — an unreproducible bill.
    verified_regions: tuple[str, ...]
    inference_profile_required: bool
    inference_profile_id: str | None
    text_input: bool
    image_input: bool
    multimodal: bool
    image_verified: bool
    context_tokens: int
    max_output_tokens: int
    invocation_apis: tuple[str, ...]
    streaming_supported: bool
    price: PriceInputs
    smoke_transport: SmokeTransport
    smoke_instruction: SmokeInstruction
    blocker: str | None
    disabled_reason: str | None
    #: Whether this model spends part of its OUTPUT allowance on reasoning content before its
    #: answer. It changes how much visible content a caller may ask for and is therefore a sizing
    #: input, not a curiosity.
    #:
    #: THE DEFAULT IS `True`, AND THE ASYMMETRY IS THE REASON. Assuming a model reasons when it
    #: does not produces a smaller target: more parts, slightly more cost, no lost work. Assuming
    #: it does not when it does produces a target sized for the answer alone — which Phase 1
    #: measured as a well-formed response with no text in it, and which at multipart scale is a
    #: truncated part and a replanning cycle. An unmeasured candidate gets the safe direction.
    emits_reasoning_before_answer: bool = True
    #: The runtime context limit WHEN AN IMAGE IS IN THE REQUEST, when it differs from the
    #: text-only one. Zero means it does not differ, or has not been measured.
    #:
    #: MEASURED 2026-08-04 AND IT IS NOT A ROUNDING DIFFERENCE. Llama 4 Maverick documents a
    #: 1,000,000-token context. Sent Apple's 10-Q with the filing's two GRAPHIC members attached,
    #: Bedrock refused with "Context length: 275912 > limit of 131072 with image provided" — an
    #: eightfold reduction that no model card mentions and that no control-plane API returns.
    #:
    #: A CAPABILITY THAT DEPENDS ON THE REQUEST IS STILL A CAPABILITY. Carrying one number would
    #: mean either refusing text-only work the model can do, or accepting multimodal work it will
    #: reject after the reservation is charged. Phase 2.2 did the second, once, and paid for it.
    context_tokens_with_image_input: int = 0

    def effective_context_tokens(self, *, images_submitted: bool) -> int:
        """The context limit that actually applies to a request of this shape.

        The image-aware limit is used only when images are genuinely going, so a multimodal model
        parsing a filing with no images keeps its full text-only context.
        """
        if images_submitted and self.context_tokens_with_image_input:
            return self.context_tokens_with_image_input
        return self.context_tokens

    def __post_init__(self) -> None:
        if self.multimodal and not (self.image_input and self.image_verified):
            raise CapabilityContradictionError(
                f"{self.label!r} is marked multimodal but its image invocation path is not "
                "verified. A model is labelled Multimodal only after a real image invocation "
                "succeeds, never from a published modality flag."
            )
        if self.inference_profile_required and not self.inference_profile_id:
            raise CapabilityContradictionError(
                f"{self.label!r} requires an inference profile but names none, so nothing could "
                "invoke it"
            )

    @property
    def invocation_id(self) -> str:
        """The identifier a caller actually invokes.

        For a model whose inference type is profile-only, the bare model id is NOT invocable and
        returns a validation error. Returning the profile id here is what keeps that fact in one
        place instead of in every caller.
        """
        if self.inference_profile_required:
            assert self.inference_profile_id is not None  # guaranteed by __post_init__
            return self.inference_profile_id
        return self.model_id

    def supports(self, role: ModelRole) -> bool:
        """Whether this model can fill a role at all, on capability grounds alone."""
        if role is ModelRole.IMAGE:
            return self.image_input and self.image_verified
        return self.text_input

    def unavailable_reason(self, *, role: ModelRole, region: str) -> str | None:
        """The concrete reason this model cannot be selected here, or None when it can.

        This string is the UI's disabled-state explanation. Every branch returns something a
        person can act on, because "unavailable" on its own sends a user to a support channel.
        """
        if self.mapping is Mapping.MISSING:
            return f"{self.label} was not found as named with any provider."
        if self.mapping is Mapping.AMBIGUOUS:
            return (
                f"{self.label} matches more than one provider model. Choosing between them is a "
                "product decision and is not made automatically."
            )
        if self.availability is not Availability.AVAILABLE:
            return self.blocker or f"{self.label} is {self.availability.value.lower()}."
        if region not in self.verified_regions:
            generated = (
                f"{self.label} was not verified in {region}. Verified regions: "
                f"{', '.join(sorted(self.verified_regions))}. Using another region is a "
                "deliberate choice, never an automatic one."
            )
            # The snapshot may add a product-specific note. It is APPENDED rather than
            # substituted, so the generated half always names the region actually requested.
            return (
                f"{generated} {self.disabled_reason}".strip() if self.disabled_reason else generated
            )
        if not self.supports(role):
            if role is ModelRole.IMAGE:
                return (
                    f"{self.label} has no verified image-input path, so it cannot fill the image "
                    "role."
                )
            return f"{self.label} has no text-input path, so it cannot fill the {role.value} role."
        return self.blocker
