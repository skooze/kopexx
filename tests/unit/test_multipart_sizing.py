"""The output-sizing policy: a cap, a target, and the headroom between them.

THE DEFECT THIS POLICY EXISTS TO PREVENT IS MEASURED, NOT IMAGINED. Phase 2 asked five candidates
for a whole filing in one response. Three of them cap output at 8,000 tokens, four of that
benchmark's five truncation failures were that cap, and the deepest parse produced — 73 nodes, 69
of 72 references resolved — was itself truncated at 8,000 with no way to finish it.

WHAT THE TESTS BELOW ACTUALLY ASSERT. That the target is always meaningfully below the cap; that a
model which spends output on reasoning gets a smaller target; that no model is named anywhere in
the policy; and that a model with almost no context left gets a small honest number rather than one
that cannot fit.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from packages.model_catalog import (
    Availability,
    Mapping,
    ModelCapability,
    PriceInputs,
    SmokeInstruction,
    SmokeTransport,
)
from packages.orchestrator.sizing import (
    CONTEXT_SAFETY_TOKENS,
    MAXIMUM_PART_TARGET_TOKENS,
    MINIMUM_PART_TARGET_TOKENS,
    compact_sizing,
    part_sizing,
    repair_sizing,
)

PRICE = PriceInputs(
    input_per_1k=Decimal("0.001"),
    output_per_1k=Decimal("0.004"),
    currency="USD",
    source="synthetic",
    effective_date="2026-01-01",
)


def _capability(
    *, context: int = 200_000, output: int = 8_000, reasons: bool = False
) -> ModelCapability:
    return ModelCapability(
        label="Synthetic",
        provider="Synthetic",
        model_id="synthetic.model",
        model_name="Synthetic",
        version_qualifier="v1",
        mapping=Mapping.UNIQUE,
        availability=Availability.AVAILABLE,
        access_status="granted",
        verified_regions=("region-one",),
        inference_profile_required=False,
        inference_profile_id=None,
        text_input=True,
        image_input=False,
        multimodal=False,
        image_verified=False,
        context_tokens=context,
        max_output_tokens=output,
        invocation_apis=("Converse",),
        streaming_supported=True,
        price=PRICE,
        smoke_transport=SmokeTransport.ACCEPTED,
        smoke_instruction=SmokeInstruction.EXACT,
        blocker=None,
        disabled_reason=None,
        emits_reasoning_before_answer=reasons,
    )


def test_the_target_is_always_below_the_cap_so_a_slightly_long_part_still_lands() -> None:
    for output in (8_000, 16_000, 32_000):
        sizing = part_sizing(_capability(output=output), estimated_input_tokens=40_000)
        assert sizing.visible_target_tokens < sizing.requested_output_tokens, (
            f"a {output}-token cap produced no headroom at all"
        )
        assert sizing.headroom_tokens > 0


def test_a_model_that_spends_output_on_reasoning_gets_a_smaller_target() -> None:
    """Phase 1 measured an 8-token budget consumed entirely by reasoning. At part scale that is a
    truncated part and a replanning cycle."""
    plain = part_sizing(_capability(output=16_000), estimated_input_tokens=40_000)
    reasoning = part_sizing(_capability(output=16_000, reasons=True), estimated_input_tokens=40_000)
    assert reasoning.visible_target_tokens < plain.visible_target_tokens
    assert reasoning.reasoning_shares_allowance is True
    assert plain.reasoning_shares_allowance is False


@pytest.mark.parametrize("output", [8_000, 16_000, 32_000])
def test_every_candidate_targets_the_same_band_so_a_comparison_is_not_about_room(
    output: int,
) -> None:
    """A 32K model writing four times as much as an 8K one would make a cross-model comparison a
    measurement of who was allowed more room."""
    sizing = part_sizing(_capability(output=output), estimated_input_tokens=40_000)
    assert MINIMUM_PART_TARGET_TOKENS <= sizing.visible_target_tokens <= MAXIMUM_PART_TARGET_TOKENS


def test_a_compact_call_is_bounded_well_below_a_part() -> None:
    """A plan, a replan, a reconciliation and a gap repair return work, never content."""
    part = part_sizing(_capability(output=32_000), estimated_input_tokens=40_000)
    plan = compact_sizing(_capability(output=32_000), estimated_input_tokens=40_000, kind="plan")
    assert plan.visible_target_tokens < part.visible_target_tokens
    assert plan.kind == "plan"


def test_the_cap_never_exceeds_what_the_context_has_left() -> None:
    sizing = part_sizing(_capability(context=50_000, output=32_000), estimated_input_tokens=40_000)
    assert sizing.requested_output_tokens == 50_000 - 40_000 - CONTEXT_SAFETY_TOKENS


def test_a_model_with_no_room_left_gets_an_honest_zero_rather_than_an_impossible_number() -> None:
    sizing = part_sizing(_capability(context=10_000), estimated_input_tokens=40_000)
    assert sizing.requested_output_tokens == 0
    assert sizing.fits is False


def test_a_format_repair_is_sized_from_the_artifact_it_repairs() -> None:
    """A repair asked for less room than the thing it repairs would truncate the repair."""
    small = repair_sizing(_capability(), estimated_input_tokens=1_000, malformed_tokens=1_000)
    large = repair_sizing(_capability(), estimated_input_tokens=4_000, malformed_tokens=4_000)
    assert large.visible_target_tokens > small.visible_target_tokens
    assert small.visible_target_tokens > 1_000, "a repair needs room for the quoting it adds"


def test_the_sizing_policy_names_no_model_anywhere() -> None:
    """The reasoning fact comes from the reviewed snapshot, never from a name test in the policy."""
    from pathlib import Path

    source = (
        Path(__file__).resolve().parents[2] / "packages" / "orchestrator" / "sizing.py"
    ).read_text(encoding="utf-8")
    import ast

    tree = ast.parse(source)
    docstrings = {
        node.body[0].value
        for node in ast.walk(tree)
        if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef)
        and node.body
        and isinstance(node.body[0], ast.Expr)
        and isinstance(node.body[0].value, ast.Constant)
    }
    literals = [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and node not in docstrings
    ]
    for label in ("GPT", "Nemotron", "Qwen", "Llama", "openai", "meta.", "nvidia"):
        assert not any(label.lower() in value.lower() for value in literals), (
            f"the sizing policy names {label!r} in an evaluated literal"
        )


def test_the_sizing_mapping_states_what_the_two_numbers_mean() -> None:
    mapping = part_sizing(_capability(), estimated_input_tokens=40_000).to_mapping()
    assert mapping["requested_output_tokens"] > mapping["visible_target_tokens"]
    assert "discarded and still billed" in mapping["policy_note"]
