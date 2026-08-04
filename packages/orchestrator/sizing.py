"""How large one multipart response is allowed to be, and what the model is told to aim for.

TWO NUMBERS, AND CONFLATING THEM IS THE DEFECT THIS MODULE EXISTS TO PREVENT.

    requested_output_tokens   the cap handed to the provider. Set as high as the model and the
                              remaining context allow, because a cap is a wall: a response that
                              hits it is thrown away and paid for.

    visible_target_tokens     the size the model is TOLD to aim for. Deliberately well below the
                              cap, so that a part which runs slightly long still lands inside the
                              wall instead of against it.

    The gap between them is headroom, and it is the whole point. Phase 2 measured the consequence
    of not having any: three of the five candidates cap output at 8,000 tokens, four of the five
    truncation failures in that benchmark were that cap, and the DEEPEST parse produced — 73 nodes
    with 69 of 72 references resolved — was itself truncated at 8,000 with no way to finish it.

REASONING CONTENT SPENDS THE SAME ALLOWANCE, AND ONE CANDIDATE USES IT HEAVILY. Phase 1 measured a
model whose entire 8-token output budget went to a reasoning block, returning a well-formed
response with no text in it. Phase 2 measured the same model emitting up to 14,980 characters of
reasoning on real filings, 6 attempts out of 6, while the other four emitted none. A target sized
for the visible answer alone reproduces the Phase 1 result at scale, so a model that reasons gets a
materially smaller visible target — and the fact comes from the reviewed capability snapshot, never
from a name test in this file.

EVERY CONSTANT HERE IS A STARTING POINT AND IS LABELLED AS ONE. They were chosen from Phase 2's
measured output lengths and caps, before any filing had been parsed under the multipart protocol.
What replaces them is the measured behaviour of the first multipart proof, not a preference.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Final

from packages.model_catalog import ModelCapability

#: Fraction of the verified output cap a PART may aim to fill with visible content.
#:
#: The reasoning variant is materially lower rather than slightly lower, because reasoning length is
#: not proportional to answer length: the same model produced 14,980 characters of reasoning beside
#: a 4,033-token answer. Half the cap is a bound that survives that, and it costs an extra part
#: rather than a truncated one.
PART_TARGET_FRACTION: Final[float] = 0.75
PART_TARGET_FRACTION_WITH_REASONING: Final[float] = 0.45

#: A part smaller than this is not worth a whole invocation: the intact filing is re-sent on every
#: call, so the input cost of a part is fixed and a tiny part pays it for very little output.
MINIMUM_PART_TARGET_TOKENS: Final[int] = 4000

#: A part larger than this stops being independently reviewable, whatever the model would allow.
#: It also keeps the five candidates' targets within one band of each other, so a cross-model
#: comparison is not measuring "who was allowed to write more".
MAXIMUM_PART_TARGET_TOKENS: Final[int] = 8000

#: A PLAN, a REPLAN, a RECONCILIATION and a GAP REPAIR are all compact by contract: they return a
#: division of work or a judgement, never content. The bound is a guard against a model that starts
#: parsing in a planning call, and it is generous enough that a genuinely long plan is not clipped.
COMPACT_TARGET_FRACTION: Final[float] = 0.5
COMPACT_TARGET_FRACTION_WITH_REASONING: Final[float] = 0.3
MINIMUM_COMPACT_TARGET_TOKENS: Final[int] = 1500
MAXIMUM_COMPACT_TARGET_TOKENS: Final[int] = 4000

#: A format repair returns the same content re-serialised, so it needs room for the original plus
#: whatever quoting adds. Measured on nothing yet; a generous multiple is the safe direction, and
#: the repair is refused rather than clipped when even that does not fit.
REPAIR_HEADROOM_MULTIPLE: Final[float] = 1.6

#: Context reserved on every call so that an under-counting input estimate does not silently turn
#: into a provider rejection.
#:
#: A FLAT RESERVE CANNOT COVER A PROPORTIONAL ERROR, AND THAT IS WHAT R-24 IS. The estimator is a
#: character ratio, so its error scales with the document: 4,000 tokens is generous against a
#: 40,000-token filing and is nothing against a 250,000-token one.
#:
#: MEASURED 2026-08-04, TO THE TOKEN. Apple's 10-Q estimated at 244,708 input tokens and Bedrock
#: counted 254,145 — an under-count of 9,437, or 3.86 percent. With the flat 4,000 reserve the
#: request asked for 8,000 output tokens against a 262,144 limit and was refused at 262,145. ONE
#: TOKEN over, on a filing that fits.
#:
#: THE ESTIMATOR UNDER-COUNTS AND R-24 SAID IT OVER-COUNTS. The compatibility guard's docstring
#: calls the character ratio "an upper bound", and on inline XBRL it is a LOWER one. Phase 2
#: measured 17 percent low on a modern filing; this phase measured 3.86 percent low on another.
#: The direction is consistent and the magnitude is not, so the reserve is sized above the larger
#: of the two measurements this filing produced rather than at either observation.
CONTEXT_SAFETY_FRACTION: Final[float] = 0.05

#: The floor, for a filing small enough that five percent is negligible.
CONTEXT_SAFETY_TOKENS: Final[int] = 4000


def context_safety_tokens(estimated_input_tokens: int) -> int:
    """The reserve for one request, proportional to what is being estimated."""
    return max(CONTEXT_SAFETY_TOKENS, int(estimated_input_tokens * CONTEXT_SAFETY_FRACTION))


@dataclass(frozen=True)
class OutputSizing:
    """The cap for one invocation, the target the model is told, and the arithmetic behind both."""

    requested_output_tokens: int
    visible_target_tokens: int
    model_max_output_tokens: int
    model_context_tokens: int
    estimated_input_tokens: int
    reasoning_shares_allowance: bool
    kind: str

    @property
    def headroom_tokens(self) -> int:
        """What is left between the target and the cap. Where a slightly long part lands."""
        return max(0, self.requested_output_tokens - self.visible_target_tokens)

    @property
    def fits(self) -> bool:
        """Whether there is room for the input and a useful response in this model's context."""
        return self.requested_output_tokens >= MINIMUM_COMPACT_TARGET_TOKENS

    def to_mapping(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "requested_output_tokens": self.requested_output_tokens,
            "visible_target_tokens": self.visible_target_tokens,
            "headroom_tokens": self.headroom_tokens,
            "model_max_output_tokens": self.model_max_output_tokens,
            "model_context_tokens": self.model_context_tokens,
            "estimated_input_tokens": self.estimated_input_tokens,
            "reasoning_shares_the_output_allowance": self.reasoning_shares_allowance,
            "policy_note": (
                "the cap is what the provider is given; the target is what the model is asked to "
                "aim for. The difference is deliberate headroom, because a response that reaches "
                "the cap is discarded and still billed."
            ),
        }


#: Below this many output tokens a call cannot produce a usable answer, so the pairing is refused
#: rather than requested.
#:
#: MEASURED, AND THE DEFECT IT CLOSES REACHED A PROVIDER SDK. On Apple's 10-Q the input left Qwen3
#: VL 235B 3,349 tokens of context, the cap arithmetic floored to ZERO, and the request went out
#: with `inferenceConfig.maxTokens: 0`. botocore refused it — "Invalid value for parameter
#: inferenceConfig.maxTokens, value: 0, valid min value: 1" — and the reservation was charged for a
#: call no provider ever saw.
#:
#: A ZERO IS NOT A SMALL BUDGET, IT IS AN IMPOSSIBLE ONE, and `_cap` returning it made an
#: incompatible pairing look compatible: the compatibility guard checked `input + 0 <= context` and
#: passed. The floor is what turns that back into the refusal it always was.
MINIMUM_USABLE_OUTPUT_TOKENS: Final[int] = 512


def _cap(capability: ModelCapability, estimated_input_tokens: int) -> int:
    """The largest output this model can be asked for, given what the input already occupies.

    Returns 0 when there is not enough room left to be worth asking for. A caller must treat 0 as
    INCOMPATIBLE and refuse; it must never be sent as a request cap.
    """
    context_left = (
        capability.effective_context_tokens(images_submitted=capability.multimodal)
        - estimated_input_tokens
        - context_safety_tokens(estimated_input_tokens)
    )
    room = max(0, min(capability.max_output_tokens, context_left))
    return 0 if room < MINIMUM_USABLE_OUTPUT_TOKENS else room


def _target(
    cap: int, *, fraction: float, reasoning_fraction: float, floor: int, ceiling: int, reasons: bool
) -> int:
    chosen = reasoning_fraction if reasons else fraction
    wanted = int(math.floor(cap * chosen))
    # The floor is applied BEFORE the cap, then clamped by it: a model with very little room left
    # gets a small honest target rather than one that cannot fit.
    return max(1, min(ceiling, max(floor, wanted), cap))


def part_sizing(capability: ModelCapability, *, estimated_input_tokens: int) -> OutputSizing:
    """Sizing for one part or subpart invocation."""
    cap = _cap(capability, estimated_input_tokens)
    return OutputSizing(
        requested_output_tokens=cap,
        visible_target_tokens=_target(
            cap,
            fraction=PART_TARGET_FRACTION,
            reasoning_fraction=PART_TARGET_FRACTION_WITH_REASONING,
            floor=MINIMUM_PART_TARGET_TOKENS,
            ceiling=MAXIMUM_PART_TARGET_TOKENS,
            reasons=capability.emits_reasoning_before_answer,
        ),
        model_max_output_tokens=capability.max_output_tokens,
        model_context_tokens=capability.effective_context_tokens(
            images_submitted=capability.multimodal
        ),
        estimated_input_tokens=estimated_input_tokens,
        reasoning_shares_allowance=capability.emits_reasoning_before_answer,
        kind="part",
    )


def compact_sizing(
    capability: ModelCapability, *, estimated_input_tokens: int, kind: str
) -> OutputSizing:
    """Sizing for a plan, a replan, a reconciliation or a gap repair. All return work, not content."""
    cap = _cap(capability, estimated_input_tokens)
    return OutputSizing(
        requested_output_tokens=cap,
        visible_target_tokens=_target(
            cap,
            fraction=COMPACT_TARGET_FRACTION,
            reasoning_fraction=COMPACT_TARGET_FRACTION_WITH_REASONING,
            floor=MINIMUM_COMPACT_TARGET_TOKENS,
            ceiling=MAXIMUM_COMPACT_TARGET_TOKENS,
            reasons=capability.emits_reasoning_before_answer,
        ),
        model_max_output_tokens=capability.max_output_tokens,
        model_context_tokens=capability.effective_context_tokens(
            images_submitted=capability.multimodal
        ),
        estimated_input_tokens=estimated_input_tokens,
        reasoning_shares_allowance=capability.emits_reasoning_before_answer,
        kind=kind,
    )


def repair_sizing(
    capability: ModelCapability, *, estimated_input_tokens: int, malformed_tokens: int
) -> OutputSizing:
    """Sizing for a format repair, which returns the same content re-serialised.

    The target is the malformed artifact's own size plus room for the quoting that was missing.
    A repair asked for less room than the thing it is repairing would truncate the repair, which
    is the one outcome that would make the original response harder to review rather than easier.
    """
    cap = _cap(capability, estimated_input_tokens)
    wanted = int(math.ceil(malformed_tokens * REPAIR_HEADROOM_MULTIPLE))
    return OutputSizing(
        requested_output_tokens=cap,
        visible_target_tokens=max(1, min(wanted, cap)),
        model_max_output_tokens=capability.max_output_tokens,
        model_context_tokens=capability.effective_context_tokens(
            images_submitted=capability.multimodal
        ),
        estimated_input_tokens=estimated_input_tokens,
        reasoning_shares_allowance=capability.emits_reasoning_before_answer,
        kind="format_repair",
    )
