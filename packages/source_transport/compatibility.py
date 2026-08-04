"""Does the INTACT source set fit the selected model? A yes/no with the numbers behind it.

`INTACT_SOURCE_ONLY` IS THE AUTHORIZED MODE. If the complete relevant human-readable source set
does not fit, that is a RESULT and the pairing is refused. Nothing is truncated, sliced,
projected, split into parts, or swapped to a different model — rules.md section 21 rules 6, 7, 9
and 10. The user picks another model, or the answer stays no.

WHY THIS MODULE TAKES NUMBERS AND NOT A CAPABILITY OBJECT. It is handed a context limit, an output
limit and an image flag rather than importing `packages/model_catalog`. Those numbers come from
the reviewed capability snapshot and have exactly one home; taking them as arguments keeps this
package free of any opinion about which models exist and keeps its tests free of a snapshot.

EVERY TOKEN FIGURE HERE IS AN ESTIMATE. `estimate_tokens` is a character ratio, not a provider
tokenizer, and it over-estimates slightly on purpose because this guard runs BEFORE the money is
spent. The real counts come back in the provider's usage block, and comparing the two is one of
the measurements Phase 2 exists to produce.

    R-24 IS OPEN AND THIS IS WHERE IT BITES. A character-ratio estimate is an upper bound, not a
    count. A filing that this module calls compatible can still be refused by the provider, and a
    filing it calls incompatible might have fitted. The estimate is recorded beside the measured
    usage on every invocation so the size of that gap stops being a guess.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final

from packages.llm_gateway import estimate_tokens

from .dispositions import MemberDisposition
from .records import SourceSet

#: An UNVERIFIED upper bound for what one filed image costs as input tokens.
#:
#: Bedrock publishes no separate image price for these candidates and bills image input as input
#: tokens, but it does not publish the conversion. Rather than leave a hole in a guard that runs
#: before money is spent, a deliberately generous constant is charged and LABELLED as unverified.
#: It is used only to make the pre-spend bound conservative; the measured figure arrives in the
#: usage block of the first multimodal invocation, and the difference between the two is recorded.
#: A number that is too large refuses a run that would have fitted, which is the safe direction.
UNVERIFIED_TOKENS_PER_IMAGE: Final[int] = 4000


@dataclass(frozen=True)
class CompatibilityReport:
    """Whether this filing can be sent to this model intact, and the arithmetic that says so."""

    compatible: bool
    reason: str
    detail: str
    estimated_input_tokens: int
    prompt_tokens: int
    text_tokens: int
    image_tokens: int
    image_count: int
    submitted_bytes: int
    model_context_tokens: int
    requested_output_tokens: int
    unknown_member_count: int
    images_unprocessed: bool
    uncovered_member_count: int

    @property
    def headroom_tokens(self) -> int:
        """Context left over after the estimated input and the requested output."""
        return (
            self.model_context_tokens - self.estimated_input_tokens - self.requested_output_tokens
        )

    def to_mapping(self) -> dict[str, Any]:
        return {
            "compatible": self.compatible,
            "reason": self.reason,
            "detail": self.detail,
            "estimated_input_tokens": self.estimated_input_tokens,
            "prompt_tokens": self.prompt_tokens,
            "text_tokens": self.text_tokens,
            "image_tokens": self.image_tokens,
            "image_tokens_are_verified": False,
            "image_count": self.image_count,
            "submitted_bytes": self.submitted_bytes,
            "model_context_tokens": self.model_context_tokens,
            "requested_output_tokens": self.requested_output_tokens,
            "headroom_tokens": self.headroom_tokens,
            "unknown_member_count": self.unknown_member_count,
            "images_unprocessed": self.images_unprocessed,
            "uncovered_member_count": self.uncovered_member_count,
            "token_values_are": (
                "ESTIMATES from a character ratio, never provider tokenizer counts"
            ),
        }


def assess(
    source_set: SourceSet,
    *,
    prompt_text: str,
    model_context_tokens: int,
    requested_output_tokens: int,
    model_accepts_images: bool,
) -> CompatibilityReport:
    """Assess one filing against one model under INTACT_SOURCE_ONLY."""
    prompt_tokens = estimate_tokens(prompt_text)
    text_tokens = sum(estimate_tokens(m.text or "") for m in source_set.text_members)

    images = source_set.image_members
    # A text-only parser receives no images. They are NOT dropped from the record: they stay in
    # the source set, they are reported unanalysed, and the run may not claim image coverage.
    images_unprocessed = bool(images) and not model_accepts_images
    image_count = len(images) if model_accepts_images else 0
    image_tokens = image_count * UNVERIFIED_TOKENS_PER_IMAGE

    estimated = prompt_tokens + text_tokens + image_tokens
    submitted_bytes = sum(
        m.byte_count
        for m in source_set.submitted_members
        if model_accepts_images or m.disposition is not MemberDisposition.PARSER_INPUT_IMAGE
    )
    unknown = source_set.unknown_members

    if unknown:
        names = ", ".join(m.filename or f"sequence {m.sequence}" for m in unknown)
        return CompatibilityReport(
            compatible=False,
            reason="unknown_member_role",
            detail=(
                f"{len(unknown)} filed member(s) have a transport role this system does not "
                f"recognise and will not guess: {names}. An unknown role fails closed rather than "
                "being dropped from the source set or submitted as bytes no model can use."
            ),
            estimated_input_tokens=estimated,
            prompt_tokens=prompt_tokens,
            text_tokens=text_tokens,
            image_tokens=image_tokens,
            image_count=image_count,
            submitted_bytes=submitted_bytes,
            model_context_tokens=model_context_tokens,
            requested_output_tokens=requested_output_tokens,
            unknown_member_count=len(unknown),
            images_unprocessed=images_unprocessed,
            uncovered_member_count=len(source_set.uncovered_members),
        )

    # A ZERO OUTPUT BUDGET IS AN IMPOSSIBLE REQUEST, NOT A SMALL ONE, and it must not pass here.
    #
    # MEASURED 2026-08-04. On Apple's 10-Q accession 0000320193-25-000008 the intact source set
    # left Qwen3 VL 235B roughly 3,300 tokens of context, the sizing policy floored its output cap
    # to zero, and `estimated + 0 <= context` was TRUE — so an incompatible pairing was reported
    # compatible, the request went out with `inferenceConfig.maxTokens: 0`, and botocore refused it
    # before transport while the reservation was charged.
    #
    # The arithmetic was right and the question was wrong. "Does the input fit" is not the question
    # this guard exists to answer; "can this model be asked to parse this filing" is, and a model
    # that has no room to answer cannot.
    if requested_output_tokens <= 0:
        return CompatibilityReport(
            compatible=False,
            reason="no_room_for_an_answer",
            detail=(
                f"the complete source set is estimated at {estimated:,} input tokens against a "
                f"verified context of {model_context_tokens:,}, which leaves no usable room for a "
                "response. INTACT_SOURCE_ONLY is the authorized mode: nothing is truncated, sliced "
                "or split, and no other model is substituted. Select a model with a larger "
                "verified context."
            ),
            estimated_input_tokens=estimated,
            prompt_tokens=prompt_tokens,
            text_tokens=text_tokens,
            image_tokens=image_tokens,
            image_count=image_count,
            submitted_bytes=submitted_bytes,
            model_context_tokens=model_context_tokens,
            requested_output_tokens=requested_output_tokens,
            unknown_member_count=0,
            images_unprocessed=images_unprocessed,
            uncovered_member_count=len(source_set.uncovered_members),
        )

    # The output shares the context window with the input on every candidate's Converse path, so
    # the guard reserves room for both. Sizing only the input is how a request is accepted and
    # then truncated at max_tokens with the parse half-finished.
    required = estimated + requested_output_tokens
    fits = required <= model_context_tokens
    if fits:
        reason, detail = (
            "fits",
            (
                f"the complete source set is estimated at {estimated:,} input tokens and the run "
                f"requests {requested_output_tokens:,} output tokens, against a verified context of "
                f"{model_context_tokens:,}. Token figures are ESTIMATES from a character ratio."
            ),
        )
    else:
        reason, detail = (
            "source_set_exceeds_context",
            (
                f"the complete source set is estimated at {estimated:,} input tokens and the run "
                f"requests {requested_output_tokens:,} output tokens, which is {required:,} against a "
                f"verified context of {model_context_tokens:,} — over by {required - model_context_tokens:,}. "
                "INTACT_SOURCE_ONLY is the authorized mode: nothing is truncated, sliced or split, and "
                "no other model is substituted. Select a model with a larger verified context."
            ),
        )

    return CompatibilityReport(
        compatible=fits,
        reason=reason,
        detail=detail,
        estimated_input_tokens=estimated,
        prompt_tokens=prompt_tokens,
        text_tokens=text_tokens,
        image_tokens=image_tokens,
        image_count=image_count,
        submitted_bytes=submitted_bytes,
        model_context_tokens=model_context_tokens,
        requested_output_tokens=requested_output_tokens,
        unknown_member_count=0,
        images_unprocessed=images_unprocessed,
        uncovered_member_count=len(source_set.uncovered_members),
    )


def image_coverage_report(source_set: SourceSet, *, model_accepts_images: bool) -> dict[str, Any]:
    """What happened to every image-bearing member, stated plainly.

    A text-only parser produces `analysed: false` with the affected documents NAMED. The Phase 2
    brief and roadmap.md both require the same thing and for the same reason: a run that quietly
    omits images while reporting a complete parse has made a false completeness claim.
    """
    images = source_set.image_members
    # THREE CASES, NOT TWO. Reporting `analysed: false` beside a reason reading "the model received
    # these images itself" is what happens when a filing with NO images is squeezed into a boolean
    # that only ever meant "were the images handled". A filing with no images has nothing to
    # analyse, and saying so is different from saying something was skipped.
    if not images:
        reason = "this filing has no image-bearing member, so there is nothing to analyse"
    elif model_accepts_images:
        reason = "the selected parsing model is multimodal and received these images itself"
    else:
        reason = (
            "the selected parsing model is text-only and no separate image model was selected, so "
            "image-bearing content was NOT analysed and this run does not claim image coverage"
        )
    return {
        "image_member_count": len(images),
        "analysed": bool(images) and model_accepts_images,
        "nothing_to_analyse": not images,
        "reason": reason,
        "members": [
            {
                "filename": m.filename,
                "sha256": m.sha256,
                "byte_count": m.byte_count,
                "image_format": m.image_format,
                "submitted_to_parser": model_accepts_images,
            }
            for m in images
        ],
    }
