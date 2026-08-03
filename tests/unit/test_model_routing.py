"""Four-role routing: which model, in which region, and what the user is told before it is billed.

HERMETIC AND SYNTHETIC. Every snapshot below is built in this file out of invented labels and
invented region names. Nothing reaches a provider, reads a credential or touches the network, and
nothing here depends on the committed snapshot naming any particular model — the tests that hold
the committed file to its contract live in `tests/unit/test_model_catalog.py` and are deliberately
not repeated. The candidate builder is a near-twin of the one in that file on purpose: a test
helper shared across modules through an import would make one file's edit silently rewrite the
other file's fixtures.

WHAT IS ACTUALLY BEING TESTED. Not that a router returns a region; that is a dictionary lookup. The
subject is the four promises `packages/model_catalog/routing.py` makes and could break without
anything failing: a cross-region route is DISCLOSED before the invocation rather than discovered in
a bill afterwards, the region it picks is DETERMINISTIC because `verified_regions` is an ordered
tuple and not a set, a blank optional role runs NO stage rather than borrowing the parsing model,
and a candidate that cannot be used comes back DISABLED WITH A REASON rather than filtered away.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from packages.model_catalog import (
    ModelRole,
    ModelUnavailableError,
    RoleSelection,
    UnknownModelLabelError,
    load_snapshot,
    route,
    route_selection,
    selector_entries,
)

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


def second(**overrides: object) -> str:
    """A second candidate, distinct in label and identifier so a substitution would be visible."""
    return candidate(label="Model Two", model_id="provider.model-two", **overrides)


def third(**overrides: object) -> str:
    return candidate(label="Model Three", model_id="provider.model-three", **overrides)


# --- routing to the preferred region -------------------------------------------------------------


def test_a_verified_preferred_region_is_used_and_carries_no_cross_region_disclosure() -> None:
    """The ordinary case must stay silent, or the disclosure means nothing.

    A `cross_region_reason` attached to every decision would be a banner rather than a warning, and
    a reviewer scanning a run plan for the routes that move content between regions would have
    nothing to scan for.
    """
    snap = load_snapshot(snapshot())
    decision = route(snap, "Model One", role=ModelRole.PARSING, preferred_region="region-one")
    assert decision.region == "region-one"
    assert decision.preferred_region == "region-one"
    assert decision.in_preferred_region is True
    assert decision.cross_region_reason is None
    assert decision.label == "Model One"
    assert decision.role is ModelRole.PARSING
    assert decision.invocation_id == "provider.model-one"


def test_the_preferred_region_wins_even_when_it_is_not_first_in_the_snapshot() -> None:
    """Anti-vacuity for the fallback rule below.

    A router that always took `verified_regions[0]` would pass every cross-region test in this file
    and quietly move content out of the preferred region on every single invocation. The regions
    here are ordered so that the first one is NOT the preferred one.
    """
    snap = load_snapshot(snapshot(candidate(verified_regions=["region-two", "region-one"])))
    decision = route(snap, "Model One", role=ModelRole.PARSING, preferred_region="region-one")
    assert decision.region == "region-one"
    assert decision.in_preferred_region is True
    assert decision.cross_region_reason is None


# --- routing across regions, and disclosing it ---------------------------------------------------


def test_an_unverified_preferred_region_falls_to_the_first_verified_one_and_names_both() -> None:
    """rules.md section 21: the product is not one-region, and no route is silent.

    The reason is the sentence a user reads before authorizing the run, so it has to name the region
    that was preferred, the region that will actually be invoked, and the model in question. A
    reason naming only one of them cannot be acted on.
    """
    snap = load_snapshot(snapshot(candidate(verified_regions=["region-two"])))
    decision = route(snap, "Model One", role=ModelRole.PARSING, preferred_region="region-one")

    assert decision.region == "region-two", "the invocation goes where the snapshot verified it"
    assert decision.preferred_region == "region-one", "the preference is preserved, not overwritten"
    assert decision.in_preferred_region is False

    reason = decision.cross_region_reason
    assert reason is not None, "a cross-region route with no explanation is an undisclosed one"
    assert "region-one" in reason, "the reason must name the region that was preferred"
    assert "region-two" in reason, "the reason must name the region that will be invoked"
    assert "Model One" in reason, "the reason must name the model being routed"
    assert "cross-region" in reason.lower()


def test_the_region_a_cross_region_route_picks_is_snapshot_order_not_sorted_order() -> None:
    """`verified_regions` is an ordered tuple and the order is the reviewed document's.

    A set — or a sort applied for tidiness — makes the chosen region depend on something no human
    reviewed, and the same snapshot could bill a different region on a different interpreter run.
    The regions here are listed in an order that sorting would invert, so a router that sorted or
    hashed them fails this and nothing else.
    """
    snap = load_snapshot(snapshot(candidate(verified_regions=["region-two", "region-one"])))
    capability = snap.get("Model One")
    assert isinstance(capability.verified_regions, tuple), "an ordered tuple, never a set"
    assert capability.verified_regions == ("region-two", "region-one")

    decisions = [
        route(snap, "Model One", role=ModelRole.PARSING, preferred_region="region-nine")
        for _ in range(10)
    ]
    assert {d.region for d in decisions} == {"region-two"}, "the first snapshot region, every time"
    assert all(d.cross_region_reason is not None for d in decisions)
    reason = decisions[0].cross_region_reason
    assert reason is not None
    assert "region-two, region-one" in reason, "the disclosure lists them in snapshot order too"


def test_a_cross_region_route_discloses_itself_in_the_record_it_hands_on() -> None:
    """The disclosure has to survive the hand-off, or it stops at the router.

    `to_mapping` is what travels into the run plan, the request evidence, the cost record and the
    artifact lineage. A decision that knows it is cross-region but does not say so in the mapping is
    a decision nothing downstream can show a user.
    """
    snap = load_snapshot(snapshot(candidate(verified_regions=["region-two"])))
    record = route(
        snap, "Model One", role=ModelRole.SUMMARY, preferred_region="region-one"
    ).to_mapping()

    assert record["region"] == "region-two"
    assert record["preferred_region"] == "region-one"
    assert record["in_preferred_region"] is False
    assert record["cross_region_reason"], "the sentence must reach the record, not just the object"
    assert record["role"] == "summary"
    assert record["model_id"] == "provider.model-one"


def test_a_same_region_record_states_the_absence_rather_than_omitting_the_field() -> None:
    """A missing key and a null one read differently to a reviewer diffing two run plans."""
    snap = load_snapshot(snapshot())
    record = route(
        snap, "Model One", role=ModelRole.PARSING, preferred_region="region-one"
    ).to_mapping()
    assert "cross_region_reason" in record
    assert record["cross_region_reason"] is None
    assert record["in_preferred_region"] is True


# --- what routing refuses to do ------------------------------------------------------------------


def test_routing_refuses_to_run_without_a_configured_preferred_region() -> None:
    """There is deliberately no default region, because a default is how a guess survives review."""
    snap = load_snapshot(snapshot())
    with pytest.raises(ModelUnavailableError) as error:
        route(snap, "Model One", role=ModelRole.PARSING, preferred_region="")
    assert error.value.label == "Model One"
    assert "no preferred region" in error.value.reason


def test_an_unavailable_model_is_refused_rather_than_substituted() -> None:
    """rules.md section 21 rule 9. The router has no substitute to offer and must not invent one.

    A usable second candidate sits in the snapshot precisely so a substitution would be possible;
    the failure must still name only the model the user selected.
    """
    snap = load_snapshot(
        snapshot(
            candidate(availability="ACCESS_NOT_GRANTED", blocker="access has not been granted"),
            second(),
        )
    )
    with pytest.raises(ModelUnavailableError) as error:
        route(snap, "Model One", role=ModelRole.PARSING, preferred_region="region-one")
    assert error.value.label == "Model One"
    assert "Model Two" not in str(error.value), "the router offered a substitute"


def test_the_substitute_the_router_refused_to_pick_was_genuinely_available() -> None:
    """Anti-vacuity for the refusal above.

    If the second candidate were unusable too, the previous test would prove only that an empty
    catalog raises. It has to be a model the router COULD have fallen back to.
    """
    snap = load_snapshot(
        snapshot(
            candidate(availability="ACCESS_NOT_GRANTED", blocker="access has not been granted"),
            second(),
        )
    )
    decision = route(snap, "Model Two", role=ModelRole.PARSING, preferred_region="region-one")
    assert decision.invocation_id == "provider.model-two"


def test_a_candidate_the_snapshot_verified_nowhere_is_refused_not_routed_anywhere() -> None:
    """An empty region list is not an invitation to pick one. Nothing can invoke it."""
    snap = load_snapshot(snapshot(candidate(verified_regions=[])))
    with pytest.raises(ModelUnavailableError) as error:
        route(snap, "Model One", role=ModelRole.PARSING, preferred_region="region-one")
    assert "no verified region" in error.value.reason


def test_an_unknown_label_is_not_routed_to_something_that_does_exist() -> None:
    """The nearest match is still a substitution, and the error names what is actually offered."""
    snap = load_snapshot(snapshot(candidate(), second()))
    with pytest.raises(UnknownModelLabelError) as error:
        route(snap, "Model Won", role=ModelRole.PARSING, preferred_region="region-one")
    assert "Model One" in str(error.value)
    assert "Model Two" in str(error.value)


def test_a_text_only_model_is_refused_for_the_image_role_rather_than_downgraded() -> None:
    """No role is quietly filled by a model that cannot perform it.

    The same model routes fine for parsing in the same region, so the refusal is about the ROLE and
    not about availability.
    """
    snap = load_snapshot(snapshot())
    assert route(snap, "Model One", role=ModelRole.PARSING, preferred_region="region-one")
    with pytest.raises(ModelUnavailableError) as error:
        route(snap, "Model One", role=ModelRole.IMAGE, preferred_region="region-one")
    assert "image" in error.value.reason.lower()


def test_a_profile_only_model_is_routed_through_its_profile_identifier() -> None:
    """The bare model id of a profile-only model is not invocable, so the decision cannot carry it."""
    snap = load_snapshot(
        snapshot(
            candidate(
                inference_profile_required=True, inference_profile_id="geo.provider.model-one"
            )
        )
    )
    decision = route(snap, "Model One", role=ModelRole.PARSING, preferred_region="region-one")
    assert decision.uses_inference_profile is True
    assert decision.invocation_id == "geo.provider.model-one"
    assert decision.capability.model_id == "provider.model-one", "the real id is still recorded"
    assert decision.to_mapping()["inference_profile_id"] == "geo.provider.model-one"


# --- the four roles, and the three that may be blank ---------------------------------------------


@pytest.mark.parametrize("blank", ["", " ", "   ", "\t"])
def test_a_blank_parsing_label_is_refused_at_construction(blank: str) -> None:
    """Only PARSING is required, and a whitespace label is a blank one.

    A selection object that could hold "no parsing model" would push the failure to whatever tried
    to invoke it, which is after the run was already accepted.
    """
    with pytest.raises(ValueError, match="parsing model is required"):
        RoleSelection(parsing=blank)


def test_three_blank_optional_roles_run_no_stage_and_borrow_no_model() -> None:
    """rules.md section 21 rule 8. A parser-only run is a complete, valid run.

    The parsing model here is multimodal, so it COULD have filled the blank image role. That is the
    whole point: the router must decline to use it rather than notice that it would fit.
    """
    snap = load_snapshot(
        snapshot(candidate(image_input=True, multimodal=True, image_verified=True))
    )
    selection = RoleSelection(parsing="Model One")

    assert selection.selected_roles == (ModelRole.PARSING,)
    routed = route_selection(snap, selection, preferred_region="region-one")
    assert len(routed) == 1, "a blank role produced an entry, so a stage nobody selected would run"
    assert list(routed) == [ModelRole.PARSING]
    assert ModelRole.IMAGE not in routed
    assert ModelRole.SUMMARY not in routed
    assert ModelRole.ANALYSIS not in routed


def test_a_blank_role_maps_to_none_rather_than_to_the_parsing_label() -> None:
    """The borrowing this forbids would be invisible one layer up: the mapping is where it starts."""
    selection = RoleSelection(parsing="Model One")
    assert selection.label_for(ModelRole.PARSING) == "Model One"
    assert selection.label_for(ModelRole.IMAGE) is None
    assert selection.label_for(ModelRole.SUMMARY) is None
    assert selection.label_for(ModelRole.ANALYSIS) is None


def test_every_selected_role_is_routed_to_the_model_that_role_selected() -> None:
    """Anti-vacuity for the parser-only case, and the independence rule in one assertion.

    If `route_selection` returned one entry regardless, the test above would pass while the product
    silently ran a single model for everything. Four filled roles must produce four entries, each
    resolved to the label chosen for that role and carrying that role.
    """
    snap = load_snapshot(
        snapshot(candidate(), second(image_input=True, multimodal=True, image_verified=True))
    )
    selection = RoleSelection(
        parsing="Model One", image="Model Two", summary="Model Two", analysis="Model One"
    )
    assert selection.selected_roles == (
        ModelRole.PARSING,
        ModelRole.IMAGE,
        ModelRole.SUMMARY,
        ModelRole.ANALYSIS,
    )

    routed = route_selection(snap, selection, preferred_region="region-one")
    assert len(routed) == 4
    assert routed[ModelRole.PARSING].label == "Model One"
    assert routed[ModelRole.IMAGE].label == "Model Two"
    assert routed[ModelRole.SUMMARY].label == "Model Two"
    assert routed[ModelRole.ANALYSIS].label == "Model One"
    assert all(decision.role is role for role, decision in routed.items())


def test_one_unusable_role_fails_the_selection_rather_than_dropping_that_stage() -> None:
    """A stage the user selected is never silently omitted from the plan.

    Dropping it would be indistinguishable, in the returned mapping, from a stage the user left
    blank — and the difference is the whole contract of `route_selection`.
    """
    snap = load_snapshot(snapshot(candidate(), second()))
    selection = RoleSelection(parsing="Model One", image="Model Two")
    with pytest.raises(ModelUnavailableError) as error:
        route_selection(snap, selection, preferred_region="region-one")
    assert error.value.label == "Model Two"


def test_a_selection_routed_across_regions_keeps_the_disclosure_per_role() -> None:
    """Each role is routed on its own evidence; one model's region says nothing about another's."""
    snap = load_snapshot(snapshot(candidate(), second(verified_regions=["region-two"])))
    routed = route_selection(
        snap,
        RoleSelection(parsing="Model One", summary="Model Two"),
        preferred_region="region-one",
    )
    assert routed[ModelRole.PARSING].in_preferred_region is True
    assert routed[ModelRole.PARSING].cross_region_reason is None
    assert routed[ModelRole.SUMMARY].in_preferred_region is False
    assert routed[ModelRole.SUMMARY].region == "region-two"


# --- the selector surface ------------------------------------------------------------------------


def test_selector_entries_return_every_candidate_including_the_unusable_ones() -> None:
    """A candidate that silently vanishes is indistinguishable from one that was never approved.

    Every disabled row therefore carries a concrete reason. A greyed control with no explanation
    sends a user to a support channel instead of to the fact that access was never granted.
    """
    snap = load_snapshot(
        snapshot(
            candidate(),
            second(availability="UNAVAILABLE", blocker="the provider does not offer it here"),
            third(mapping="MISSING"),
        )
    )
    entries = selector_entries(snap, role=ModelRole.PARSING, preferred_region="region-one")

    assert [e.label for e in entries] == ["Model One", "Model Two", "Model Three"], "snapshot order"
    unusable = [e for e in entries if not e.available]
    assert {e.label for e in unusable} == {"Model Two", "Model Three"}, "a candidate was filtered"
    for entry in unusable:
        assert entry.disabled_reason is not None, f"{entry.label} is disabled with no reason"
        assert entry.disabled_reason.strip(), f"{entry.label} carries a blank reason"


def test_an_available_candidate_carries_no_disabled_reason() -> None:
    """Anti-vacuity. If every row carried a reason, the assertion above would prove nothing.

    `disabled_reason` has to track the actual state, so the usable row's reason must be None and not
    an empty string standing in for it.
    """
    snap = load_snapshot(
        snapshot(candidate(), second(availability="UNAVAILABLE", blocker="not offered here"))
    )
    entries = {
        e.label: e
        for e in selector_entries(snap, role=ModelRole.PARSING, preferred_region="region-one")
    }
    assert entries["Model One"].available is True
    assert entries["Model One"].disabled_reason is None
    assert entries["Model Two"].available is False
    assert entries["Model Two"].disabled_reason == "not offered here"


def test_the_multimodal_badge_requires_a_verified_image_invocation() -> None:
    """A published modality flag is not a verified capability.

    Three rows: one whose image path was actually exercised, one that merely claims image input, and
    one that claims nothing. Only the first may wear the badge — a model is labelled Multimodal
    after a real image invocation succeeds, never from a specification sheet.
    """
    snap = load_snapshot(
        snapshot(
            candidate(image_input=True, multimodal=True, image_verified=True),
            second(image_input=True, multimodal=False, image_verified=False),
            third(),
        )
    )
    entries = selector_entries(snap, role=ModelRole.PARSING, preferred_region="region-one")
    badges = {e.label: e.capability_badge for e in entries}

    assert badges["Model One"] == "Multimodal"
    assert badges["Model Two"] == "Text only", "an unverified image claim earned a badge"
    assert badges["Model Three"] == "Text only"
    assert entries[0].to_mapping()["badge"] == "Multimodal", "the badge must reach the row record"


def test_a_row_shows_the_region_it_would_actually_invoke_in_and_whether_that_was_preferred() -> (
    None
):
    """The selector discloses the cross-region route before the user picks, not after.

    A candidate offered only outside the preferred region is still selectable — the product is not
    restricted to one region — but the row says so.
    """
    snap = load_snapshot(
        snapshot(candidate(), second(verified_regions=["region-three", "region-two"]))
    )
    rows = {
        e.label: e
        for e in selector_entries(snap, role=ModelRole.PARSING, preferred_region="region-one")
    }
    assert rows["Model One"].region == "region-one"
    assert rows["Model One"].in_preferred_region is True
    assert rows["Model Two"].region == "region-three", (
        "the first verified region, in snapshot order"
    )
    assert rows["Model Two"].in_preferred_region is False
    assert rows["Model Two"].available is True, "outside the preferred region is not unavailable"


def test_a_candidate_with_no_verified_region_is_disabled_and_says_which_problem_it_has() -> None:
    """An empty region column would read as 'anywhere'. It means nowhere."""
    snap = load_snapshot(snapshot(candidate(verified_regions=[])))
    (entry,) = selector_entries(snap, role=ModelRole.PARSING, preferred_region="region-one")
    assert entry.region == ""
    assert entry.available is False
    assert entry.disabled_reason is not None
    assert "no verified region" in entry.disabled_reason


def test_changing_the_role_changes_which_rows_are_offered() -> None:
    """Mutation guard: the role argument has to reach `unavailable_reason`.

    A router that ignored it would return the same enabled row for the image selector as for the
    parsing selector, and a text-only model would be offered for a job it cannot do.
    """
    snap = load_snapshot(snapshot())
    (for_parsing,) = selector_entries(snap, role=ModelRole.PARSING, preferred_region="region-one")
    (for_image,) = selector_entries(snap, role=ModelRole.IMAGE, preferred_region="region-one")

    assert for_parsing.available is True
    assert for_image.available is False
    assert for_image.disabled_reason is not None
    assert "image" in for_image.disabled_reason.lower()
    assert for_image.image_input is False, "the row states the capability, not just the verdict"


def test_an_unverified_field_reads_unverified_rather_than_blank() -> None:
    """A blank cell is read as 'nothing to say'. `unverified` is a statement about the evidence."""
    snap = load_snapshot(snapshot(candidate(version_qualifier=None)))
    (entry,) = selector_entries(snap, role=ModelRole.PARSING, preferred_region="region-one")
    assert entry.version == ""
    assert entry.to_mapping()["version"] == "unverified"


def test_selector_rows_carry_the_price_inputs_without_binary_rounding() -> None:
    """Decimal through str, never through float, all the way to the row a user is shown.

    `Decimal(0.00015)` is 0.000149999999999999993145..., which is what the binary double holds. A
    row that rounds on its way to the selector understates a quote nobody can later reconcile.
    """
    snap = load_snapshot(snapshot(candidate(price_input_per_1k=0.00015)))
    (entry,) = selector_entries(snap, role=ModelRole.PARSING, preferred_region="region-one")
    assert entry.price_input_per_1k == Decimal("0.00015")
    assert entry.price_output_per_1k == Decimal("0.004")
    assert entry.currency == "USD"
    assert entry.to_mapping()["price_input_per_1k"] == "0.00015"


def test_the_row_record_carries_the_limits_the_snapshot_verified() -> None:
    """A context limit a caller has to look up elsewhere is a limit a caller will guess at."""
    snap = load_snapshot(snapshot(candidate(context_tokens=256000, max_output_tokens=8000)))
    (entry,) = selector_entries(snap, role=ModelRole.PARSING, preferred_region="region-one")
    record = entry.to_mapping()
    assert record["context_tokens"] == 256000
    assert record["max_output_tokens"] == 8000
    assert record["uses_inference_profile"] is False
