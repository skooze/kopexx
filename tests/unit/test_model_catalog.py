"""The provider-neutral capability catalog, and the refusals it exists to make.

HERMETIC. Every test here builds its own synthetic snapshot text. Nothing reaches AWS, nothing
reads a credential, and nothing depends on the committed snapshot staying the shape it has today —
the tests that DO check the committed snapshot are separate, below the synthetic ones, and check
contract properties rather than particular models.

WHAT IS ACTUALLY BEING TESTED. Not that a lookup returns a record; that is arithmetic. The subject
is the set of things this package must REFUSE to do: substitute a model, fall back, widen a region,
pick between ambiguous matches, label something Multimodal that has never processed an image, spend
past a ceiling, or retry a response it simply did not like.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from packages.model_catalog import (
    AmbiguousModelLabelError,
    Availability,
    CapabilityContradictionError,
    CostCeilingExceededError,
    Mapping,
    ModelCapability,
    ModelRole,
    ModelUnavailableError,
    PriceInputs,
    RetryBudget,
    RetryBudgetExceededError,
    SmokeInstruction,
    SmokeTransport,
    SnapshotFormatError,
    SpendLedger,
    UnknownModelLabelError,
    load_snapshot,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
COMMITTED_SNAPSHOT = REPO_ROOT / "docs" / "llm" / "bedrock-capability-snapshot.yaml"

HEADER = """snapshot_version: "1"
verified_on: "2026-01-01"
verified_from_region: region-one
price_source: a published price list
price_effective_date: "2026-01-01"
price_currency: USD
price_unit: per 1000 tokens
candidates:
"""


def candidate(**overrides: object) -> str:
    """One synthetic candidate block. Every field the loader requires, none of them real."""
    fields: dict[str, object] = {
        "label": "Model One",
        "provider": "Provider",
        "model_id": "provider.model-one",
        "model_name": "Model One",
        "version_qualifier": "v1",
        "mapping": "UNIQUE",
        "availability": "AVAILABLE",
        "access_status": "granted",
        "verified_regions": ["region-one"],
        "inference_profile_required": False,
        "inference_profile_id": None,
        "text_input": True,
        "image_input": False,
        "multimodal": False,
        "image_verified": False,
        "context_tokens": 128000,
        "max_output_tokens": 4096,
        "invocation_apis": ["Converse"],
        "streaming_supported": True,
        "price_input_per_1k": 0.001,
        "price_output_per_1k": 0.004,
        "smoke_transport": "ACCEPTED",
        "smoke_instruction": "EXACT",
        "blocker": None,
        "disabled_reason": None,
    }
    fields.update(overrides)

    def render(value: object) -> str:
        if value is None:
            return "null"
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, list):
            return "[" + ", ".join(f'"{v}"' for v in value) + "]"
        if isinstance(value, int | float):
            return str(value)
        return f'"{value}"'

    lines = [f"  - label: {render(fields.pop('label'))}"]
    lines += [f"    {key}: {render(value)}" for key, value in fields.items()]
    return "\n".join(lines) + "\n"


def snapshot(*blocks: str) -> str:
    return HEADER + "".join(blocks or (candidate(),))


# --- label representation and mapping ----------------------------------------------------------


def test_a_label_resolves_to_exactly_one_record() -> None:
    snap = load_snapshot(snapshot())
    assert snap.labels == ("Model One",)
    assert snap.get("Model One").model_id == "provider.model-one"


def test_a_unique_mapping_resolves_to_the_provider_identifier() -> None:
    snap = load_snapshot(snapshot())
    resolved = snap.resolve("Model One", role=ModelRole.PARSING, region="region-one")
    assert resolved.invocation_id == "provider.model-one"
    assert resolved.label == "Model One"
    assert resolved.region == "region-one"


def test_an_ambiguous_mapping_is_refused_rather_than_guessed() -> None:
    """Choosing between two materially different models is a product decision."""
    snap = load_snapshot(snapshot(candidate(mapping="AMBIGUOUS")))
    with pytest.raises(AmbiguousModelLabelError):
        snap.resolve("Model One", role=ModelRole.PARSING, region="region-one")


def test_a_missing_mapping_reports_not_found_as_named() -> None:
    snap = load_snapshot(snapshot(candidate(mapping="MISSING")))
    with pytest.raises(ModelUnavailableError) as error:
        snap.resolve("Model One", role=ModelRole.PARSING, region="region-one")
    assert "not found as named" in error.value.reason.lower()


def test_an_unknown_label_names_the_labels_that_do_exist() -> None:
    """An error that only says 'unknown' sends a user to a support channel."""
    snap = load_snapshot(snapshot())
    with pytest.raises(UnknownModelLabelError) as error:
        snap.get("A Model Nobody Approved")
    assert "Model One" in str(error.value)


def test_duplicate_labels_are_rejected_at_load() -> None:
    with pytest.raises(SnapshotFormatError, match="duplicate label"):
        load_snapshot(snapshot(candidate(), candidate()))


# --- availability, region and role -------------------------------------------------------------


def test_an_unavailable_model_is_reported_never_replaced() -> None:
    """rules.md section 21 rule 9. The catalog has no substitute to offer and must not invent one."""
    snap = load_snapshot(
        snapshot(
            candidate(availability="ACCESS_NOT_GRANTED", blocker="access has not been granted"),
            candidate(label="Model Two", model_id="provider.model-two"),
        )
    )
    with pytest.raises(ModelUnavailableError) as error:
        snap.resolve("Model One", role=ModelRole.PARSING, region="region-one")
    assert error.value.label == "Model One"
    assert "Model Two" not in str(error.value)


def test_a_region_the_model_was_not_verified_in_is_refused() -> None:
    """No silent region change. Verified regions are evidence, not a starting point."""
    snap = load_snapshot(snapshot())
    with pytest.raises(ModelUnavailableError) as error:
        snap.resolve("Model One", role=ModelRole.PARSING, region="region-two")
    assert "region-two" in error.value.reason
    assert "region-one" in error.value.reason


def test_the_region_reason_names_the_region_that_was_asked_for() -> None:
    """A snapshot note is appended to the generated reason, never substituted for it.

    A hand-written note can only name the region its author had in mind; the generated half names
    the one the caller actually requested.
    """
    snap = load_snapshot(snapshot(candidate(disabled_reason="a product note")))
    with pytest.raises(ModelUnavailableError) as error:
        snap.resolve("Model One", role=ModelRole.PARSING, region="region-nine")
    assert "region-nine" in error.value.reason
    assert "a product note" in error.value.reason


def test_a_text_only_model_cannot_fill_the_image_role() -> None:
    snap = load_snapshot(snapshot())
    with pytest.raises(ModelUnavailableError) as error:
        snap.resolve("Model One", role=ModelRole.IMAGE, region="region-one")
    assert "image" in error.value.reason.lower()


def test_every_role_other_than_image_needs_only_text_input() -> None:
    snap = load_snapshot(snapshot())
    for role in (ModelRole.PARSING, ModelRole.SUMMARY, ModelRole.ANALYSIS):
        assert snap.resolve("Model One", role=role, region="region-one").invocation_id


def test_the_four_roles_are_distinct_and_none_inherits_another() -> None:
    """rules.md section 21 rule 8."""
    assert len({r.value for r in ModelRole}) == 4
    assert {r.value for r in ModelRole} == {"parsing", "image", "summary", "analysis"}


# --- inference profiles ------------------------------------------------------------------------


def test_a_profile_only_model_is_invoked_through_its_profile() -> None:
    """The bare model id of a profile-only model is not invocable at all."""
    snap = load_snapshot(
        snapshot(
            candidate(
                inference_profile_required=True,
                inference_profile_id="geo.provider.model-one",
            )
        )
    )
    resolved = snap.resolve("Model One", role=ModelRole.PARSING, region="region-one")
    assert resolved.invocation_id == "geo.provider.model-one"
    assert resolved.capability.model_id == "provider.model-one"


def test_a_profile_requirement_with_no_profile_id_is_a_contradiction() -> None:
    with pytest.raises(CapabilityContradictionError, match="names none"):
        load_snapshot(snapshot(candidate(inference_profile_required=True)))


# --- multimodal state --------------------------------------------------------------------------


def test_multimodal_requires_a_verified_image_invocation() -> None:
    """A published modality flag is not a verified capability.

    The instruction is explicit: a model is not labelled Multimodal in the selector until an actual
    image invocation works. This is the guard that stops a marketing claim reaching a dropdown.
    """
    with pytest.raises(CapabilityContradictionError, match="not verified"):
        load_snapshot(snapshot(candidate(image_input=True, multimodal=True, image_verified=False)))


def test_a_verified_image_model_is_multimodal_and_fills_the_image_role() -> None:
    snap = load_snapshot(
        snapshot(candidate(image_input=True, multimodal=True, image_verified=True))
    )
    resolved = snap.resolve("Model One", role=ModelRole.IMAGE, region="region-one")
    assert resolved.multimodal is True


def test_an_image_capable_but_unverified_model_cannot_fill_the_image_role() -> None:
    """image_input alone is a claim; image_verified is the evidence."""
    snap = load_snapshot(
        snapshot(candidate(image_input=True, multimodal=False, image_verified=False))
    )
    with pytest.raises(ModelUnavailableError):
        snap.resolve("Model One", role=ModelRole.IMAGE, region="region-one")


# --- selector surface --------------------------------------------------------------------------


def test_a_disabled_candidate_is_returned_with_a_reason_not_filtered_away() -> None:
    """A candidate that silently vanishes is indistinguishable from one never approved."""
    snap = load_snapshot(
        snapshot(candidate(), candidate(label="Model Two", model_id="provider.model-two"))
    )
    enabled = snap.selectable(role=ModelRole.IMAGE, region="region-one")
    disabled = snap.disabled(role=ModelRole.IMAGE, region="region-one")
    assert enabled == ()
    assert {label for label, _ in disabled} == {"Model One", "Model Two"}
    assert all(reason.strip() for _, reason in disabled), "every disabled state needs a reason"


def test_enabled_and_disabled_partition_the_candidate_set() -> None:
    snap = load_snapshot(
        snapshot(
            candidate(),
            candidate(label="Model Two", model_id="provider.model-two", availability="UNAVAILABLE"),
        )
    )
    enabled = set(snap.selectable(role=ModelRole.PARSING, region="region-one"))
    disabled = {label for label, _ in snap.disabled(role=ModelRole.PARSING, region="region-one")}
    assert enabled | disabled == set(snap.labels)
    assert not enabled & disabled


# --- snapshot format ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "missing",
    ["snapshot_version", "verified_on", "price_source", "price_effective_date", "price_currency"],
)
def test_a_snapshot_missing_provenance_fails_at_load(missing: str) -> None:
    """A price without a source and a date is a number somebody typed."""
    text = "\n".join(line for line in snapshot().splitlines() if not line.startswith(f"{missing}:"))
    with pytest.raises(SnapshotFormatError, match=missing):
        load_snapshot(text)


@pytest.mark.parametrize("missing", ["price_input_per_1k", "context_tokens", "verified_regions"])
def test_a_candidate_missing_a_required_field_fails_at_load(missing: str) -> None:
    text = "\n".join(
        line for line in snapshot().splitlines() if not line.strip().startswith(f"{missing}:")
    )
    with pytest.raises(SnapshotFormatError, match=missing):
        load_snapshot(text)


@pytest.mark.parametrize("empty", ["candidates: []", "candidates:"])
def test_an_empty_candidate_list_is_rejected(empty: str) -> None:
    """An empty catalog would offer nothing and report success.

    Both spellings are checked: an explicit empty sequence, and a key with no value at all, which
    YAML resolves to null rather than to a list.
    """
    text = HEADER.replace("candidates:\n", empty + "\n")
    with pytest.raises(SnapshotFormatError, match="non-empty"):
        load_snapshot(text)


def test_prices_survive_the_snapshot_without_binary_rounding() -> None:
    """Decimal through str, never through float.

    Decimal(0.00015) is 0.000149999999999999993145..., which is what the binary double holds.
    Over a corpus that difference stops being invisible.
    """
    snap = load_snapshot(snapshot(candidate(price_input_per_1k=0.00015)))
    assert snap.get("Model One").price.input_per_1k == Decimal("0.00015")


def test_price_provenance_is_carried_onto_every_record() -> None:
    """A price can never be read without the source and the date it was true."""
    snap = load_snapshot(snapshot())
    price = snap.get("Model One").price
    assert price.currency == "USD"
    assert price.source == "a published price list"
    assert price.effective_date == "2026-01-01"


def test_context_and_output_limits_are_carried_verbatim() -> None:
    snap = load_snapshot(snapshot(candidate(context_tokens=256000, max_output_tokens=8000)))
    capability = snap.get("Model One")
    assert capability.context_tokens == 256000
    assert capability.max_output_tokens == 8000


def test_smoke_transport_and_instruction_are_recorded_separately() -> None:
    """They answer different questions, and conflating them loses the more important one."""
    snap = load_snapshot(
        snapshot(candidate(smoke_transport="ACCEPTED", smoke_instruction="NONCOMPLIANT"))
    )
    capability = snap.get("Model One")
    assert capability.smoke_transport is SmokeTransport.ACCEPTED
    assert capability.smoke_instruction is SmokeInstruction.NONCOMPLIANT
    # A model that answered is reachable even when the answer was not the one requested.
    assert snap.resolve("Model One", role=ModelRole.PARSING, region="region-one")


def test_an_unrecognised_enum_value_names_the_permitted_ones() -> None:
    with pytest.raises(SnapshotFormatError, match="permitted values"):
        load_snapshot(snapshot(candidate(availability="PROBABLY")))


# --- cost ceiling ------------------------------------------------------------------------------


def price(input_per_1k: str = "0.001", output_per_1k: str = "0.004") -> PriceInputs:
    return PriceInputs(
        input_per_1k=Decimal(input_per_1k),
        output_per_1k=Decimal(output_per_1k),
        currency="USD",
        source="test",
        effective_date="2026-01-01",
    )


def test_the_bound_is_a_worst_case_not_an_average() -> None:
    ledger = SpendLedger("1.00")
    bound = ledger.bound(price(), max_input_tokens=1000, max_output_tokens=1000)
    assert bound == Decimal("0.005")
    assert ledger.spent_usd == 0, "computing a bound must not spend anything"


def test_an_invocation_past_the_ceiling_is_refused_before_it_is_made() -> None:
    """rules.md section 21 rule 11: previewed and authorized before, never reconciled after."""
    ledger = SpendLedger("0.001")
    with pytest.raises(CostCeilingExceededError) as error:
        ledger.authorize(price(), max_input_tokens=1000, max_output_tokens=1000)
    assert error.value.ceiling_usd == "0.001"
    assert ledger.spent_usd == 0


def test_the_reservation_is_charged_immediately_and_settled_afterwards() -> None:
    """Charging only on success would let billable rejections walk past the ceiling."""
    ledger = SpendLedger("1.00")
    reserved = ledger.authorize(price(), max_input_tokens=1000, max_output_tokens=1000)
    assert ledger.spent_usd == reserved
    actual = ledger.settle(price(), reserved=reserved, input_tokens=10, output_tokens=2)
    assert actual == Decimal("0.000018")
    assert ledger.spent_usd == actual


def test_the_ceiling_holds_across_a_sequence_of_invocations() -> None:
    ledger = SpendLedger("0.010")
    for _ in range(2):
        ledger.authorize(price(), max_input_tokens=1000, max_output_tokens=1000)
    assert ledger.remaining_usd == Decimal("0.000")
    with pytest.raises(CostCeilingExceededError):
        ledger.authorize(price(), max_input_tokens=1, max_output_tokens=1)


def test_a_zero_or_negative_ceiling_is_rejected() -> None:
    for value in ("0", "-1"):
        with pytest.raises(ValueError):
            SpendLedger(value)


def test_negative_token_counts_are_rejected() -> None:
    with pytest.raises(ValueError):
        price().cost(-1, 0)


# --- retry ceiling -----------------------------------------------------------------------------


def test_one_retry_is_permitted_and_a_second_is_not() -> None:
    budget = RetryBudget(max_retries=1)
    budget.consume(retryable=True)
    assert budget.remaining == 0
    with pytest.raises(RetryBudgetExceededError, match="exhausted"):
        budget.consume(retryable=True)


def test_a_non_transient_failure_is_never_retried() -> None:
    """Retrying until a model says what you wanted is prompt tuning with the measurement removed."""
    budget = RetryBudget(max_retries=1)
    with pytest.raises(RetryBudgetExceededError, match="not a transient"):
        budget.consume(retryable=False)
    assert budget.used == 0


# --- the committed snapshot, as a contract -----------------------------------------------------


def test_the_committed_snapshot_loads() -> None:
    """The file the product is supplied with must satisfy its own loader."""
    snap = load_snapshot(COMMITTED_SNAPSHOT.read_text(encoding="utf-8"))
    assert snap.candidates, "the committed snapshot has no candidates"
    assert snap.price_effective_date, "the committed snapshot has no price effective date"


def test_every_committed_candidate_carries_complete_provenance() -> None:
    """No half-recorded candidate: a blank field here is a claim nobody verified."""
    snap = load_snapshot(COMMITTED_SNAPSHOT.read_text(encoding="utf-8"))
    for capability in snap.candidates:
        assert capability.provider, f"{capability.label} has no provider"
        assert capability.model_id, f"{capability.label} has no model id"
        assert capability.verified_regions, f"{capability.label} names no verified region"
        assert capability.context_tokens > 0, f"{capability.label} has no context limit"
        assert capability.max_output_tokens > 0, f"{capability.label} has no output limit"
        assert capability.invocation_apis, f"{capability.label} names no invocation API"
        assert capability.price.input_per_1k > 0, f"{capability.label} has no input price"
        assert capability.price.output_per_1k > 0, f"{capability.label} has no output price"
        assert capability.price.source and capability.price.effective_date


def test_no_committed_candidate_claims_multimodal_without_a_verified_image_invocation() -> None:
    """Enforced by construction; asserted here so the intent is visible in the suite."""
    snap = load_snapshot(COMMITTED_SNAPSHOT.read_text(encoding="utf-8"))
    for capability in snap.candidates:
        if capability.multimodal:
            assert capability.image_verified, f"{capability.label} is multimodal but unverified"
            assert capability.smoke_transport is SmokeTransport.ACCEPTED


def test_every_committed_candidate_was_actually_reached() -> None:
    """Phase 1's exit criterion: one real response from every required available model."""
    snap = load_snapshot(COMMITTED_SNAPSHOT.read_text(encoding="utf-8"))
    for capability in snap.candidates:
        if capability.availability is Availability.AVAILABLE:
            assert capability.smoke_transport is SmokeTransport.ACCEPTED, (
                f"{capability.label} is recorded available but was never reached"
            )


def test_a_committed_candidate_that_is_unavailable_carries_a_blocker() -> None:
    snap = load_snapshot(COMMITTED_SNAPSHOT.read_text(encoding="utf-8"))
    for capability in snap.candidates:
        if capability.availability is not Availability.AVAILABLE:
            assert capability.blocker, f"{capability.label} is unavailable with no stated blocker"


def test_the_committed_snapshot_maps_every_candidate_uniquely_or_says_why_not() -> None:
    snap = load_snapshot(COMMITTED_SNAPSHOT.read_text(encoding="utf-8"))
    for capability in snap.candidates:
        assert capability.mapping in (Mapping.UNIQUE, Mapping.AMBIGUOUS, Mapping.MISSING)
        if capability.mapping is not Mapping.UNIQUE:
            assert capability.blocker or capability.disabled_reason


def test_the_committed_snapshot_has_something_to_check() -> None:
    """Anti-vacuity. A snapshot trimmed to one candidate would pass every test above."""
    snap = load_snapshot(COMMITTED_SNAPSHOT.read_text(encoding="utf-8"))
    assert len(snap.candidates) >= 5, "fewer candidates than the approved beta list"
    assert any(c.multimodal for c in snap.candidates), "no verified multimodal candidate"
    assert any(not c.multimodal for c in snap.candidates), "no text-only candidate"
    assert any(c.inference_profile_required for c in snap.candidates), "no profile-only candidate"


def test_capability_record_construction_is_validated_directly() -> None:
    """The dataclass refuses a contradiction even when nothing parsed a snapshot."""
    with pytest.raises(CapabilityContradictionError):
        ModelCapability(
            label="X",
            provider="P",
            model_id="p.x",
            model_name="X",
            version_qualifier="",
            mapping=Mapping.UNIQUE,
            availability=Availability.AVAILABLE,
            access_status="",
            verified_regions=frozenset({"region-one"}),
            inference_profile_required=False,
            inference_profile_id=None,
            text_input=True,
            image_input=False,
            multimodal=True,
            image_verified=False,
            context_tokens=1,
            max_output_tokens=1,
            invocation_apis=("Converse",),
            streaming_supported=True,
            price=price(),
            smoke_transport=SmokeTransport.ACCEPTED,
            smoke_instruction=SmokeInstruction.EXACT,
            blocker=None,
            disabled_reason=None,
        )
