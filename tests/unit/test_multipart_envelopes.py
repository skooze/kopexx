"""Reading the multipart envelopes, and refusing to require anything the model did not choose.

WHAT THESE TESTS ARE REALLY ABOUT. Not that a reader returns a dataclass; that is arithmetic. The
subject is the LINE the whole phase turns on: which parts of a response this repository is allowed
to depend on, and which it must carry untouched however strange they look.

    a part identifier is the MODEL's and is never rewritten, normalised or shortened
    a part TYPE is whatever the model called it, and no vocabulary is checked
    an unknown key survives, because finding out what models emit is the point
    a status the protocol does not define is preserved and treated as unfinished, never as complete
    a truncated attempt is never read as a finished part
"""

from __future__ import annotations

import pytest

from packages.multipart import (
    MAX_PART_IDENTIFIER_CHARACTERS,
    EnvelopeUnreadableError,
    PartStatus,
    UnsafePartIdentifierError,
    read_amendment,
    read_part,
    read_plan,
    read_replan,
    require_part_identifier,
    storage_token,
)

PLAN = """parse_plan_id: "plan-1"
parts:
  - part_id: "a"
    order: 2
    title: Something The Filing Calls It
    type: a kind no backend has heard of
    purpose: the opening
    expected_output_tokens: 2000
    a_key_nobody_declared: kept
  - part_id: "b"
    order: 1
    title: Another Thing
    type: another model-chosen kind
    depends_on: ["a"]
    may_require_subparts: true
unassigned:
  - where: near the end
    what: something
    why: not yet assigned
uncertainty:
  - note: unsure about the division
metadata:
  anything: at all
surprising_top_level_key: also kept
"""


def test_a_plan_carries_the_models_identifiers_titles_and_types_untouched() -> None:
    plan = read_plan(PLAN)
    assert plan.plan_id == "plan-1"
    first = plan.part("a")
    assert first is not None
    assert first.part_id == "a"
    assert first.title == "Something The Filing Calls It"
    assert first.type_label == "a kind no backend has heard of"
    assert first.depends_on == ()
    assert plan.part("b") is not None and plan.part("b").depends_on == ("a",)  # type: ignore[union-attr]


def test_a_plan_is_ordered_by_the_models_own_order_not_by_the_order_it_was_written() -> None:
    """`b` declares order 1 and is written second. The model's number wins."""
    assert [p.part_id for p in read_plan(PLAN).ordered()] == ["b", "a"]


def test_every_key_the_reader_does_not_know_about_survives() -> None:
    plan = read_plan(PLAN)
    assert plan.extra["surprising_top_level_key"] == "also kept"
    assert plan.part("a").extra["a_key_nobody_declared"] == "kept"  # type: ignore[union-attr]


def test_a_missing_envelope_key_is_a_finding_and_never_a_refusal() -> None:
    plan = read_plan('parts:\n  - part_id: "x"\n    order: 1\n    title: t\n')
    assert plan.missing_envelope_keys == ("parse_plan_id",)
    assert plan.part_ids == ("x",), "a usable plan was thrown away over a missing key"


def test_a_response_that_is_not_one_yaml_mapping_raises_with_the_reason() -> None:
    with pytest.raises(EnvelopeUnreadableError, match="not one YAML 1.2 document"):
        read_plan("key: [unclosed\n")
    with pytest.raises(EnvelopeUnreadableError, match="rather than a mapping"):
        read_plan("- just\n- a\n- list\n")


# --- parts ---------------------------------------------------------------------------------------

PART = """parse_plan_id: "plan-1"
part_id: "a"
parent_part_id: "root"
status: complete
title: Something The Filing Calls It
type: a kind no backend has heard of
nodes:
  - id: "n1"
    order: 1
    type: whatever
    title: whatever
tables:
  - caption: a table
unresolved:
  - what: a thing
    where: somewhere
    why: could not tell
coverage_summary: covers the opening
image_references:
  - filename: chart.png
metadata: {}
another_unknown_key: kept
"""


def test_a_part_carries_its_plan_its_identity_and_the_models_words() -> None:
    part = read_part(PART)
    assert part.plan_id == "plan-1"
    assert part.part_id == "a"
    assert part.parent_part_id == "root"
    assert part.status is PartStatus.COMPLETE
    assert part.title == "Something The Filing Calls It"
    assert part.node_count == 1
    assert len(part.tables) == 1
    assert len(part.unresolved) == 1
    assert part.extra["another_unknown_key"] == "kept"


@pytest.mark.parametrize(
    "declared",
    [
        "complete",
        "needs_subparts",
        "source_ambiguity",
        "image_dependency_unavailable",
        "unable_to_complete",
    ],
)
def test_every_workflow_status_the_protocol_defines_is_recognised(declared: str) -> None:
    part = read_part(f'parse_plan_id: "p"\npart_id: "a"\nstatus: {declared}\nnodes: []\n')
    assert part.status is not PartStatus.UNRECOGNISED
    assert part.declared_status == declared


def test_a_status_the_protocol_does_not_define_is_preserved_and_is_not_complete() -> None:
    """A model that invents a word has told us something real. It is kept, not rounded up."""
    part = read_part('parse_plan_id: "p"\npart_id: "a"\nstatus: mostly_done\nnodes: []\n')
    assert part.status is PartStatus.UNRECOGNISED
    assert part.declared_status == "mostly_done"
    assert part.status is not PartStatus.COMPLETE


def test_proposed_subparts_imply_subparts_are_required_even_without_the_flag() -> None:
    part = read_part(
        'parse_plan_id: "p"\npart_id: "a"\nstatus: needs_subparts\n'
        'proposed_subparts:\n  - part_id: "a-1"\n    title: half\n'
    )
    assert part.subparts_required is True
    assert [s.part_id for s in part.proposed_subparts] == ["a-1"]


def test_a_part_with_no_nodes_key_is_read_rather_than_refused() -> None:
    part = read_part('parse_plan_id: "p"\npart_id: "a"\nstatus: needs_subparts\n')
    assert part.node_count == 0
    assert "nodes" in part.missing_envelope_keys


# --- amendments and replans ------------------------------------------------------------------------


def test_a_reconciliation_response_is_read_as_a_claim_and_labelled_as_one() -> None:
    amendment = read_amendment(
        'parse_plan_id: "p"\ncycle: 2\nplan_complete: true\n'
        'additional_parts:\n  - part_id: "extra"\n    title: more\n',
        cycle=1,
    )
    assert amendment.plan_complete is True
    assert amendment.cycle == 2, "the model's own declared cycle is what is displayed"
    assert amendment.creates_work is True
    assert "MODEL's account" in amendment.to_mapping()["claim_note"]


def test_a_reconciliation_that_declares_no_cycle_takes_the_one_it_was_given() -> None:
    amendment = read_amendment('parse_plan_id: "p"\nplan_complete: false\n', cycle=3)
    assert amendment.cycle == 3


def test_a_replan_records_the_models_coverage_claim_and_says_it_is_not_believed() -> None:
    outcome = read_replan(
        'parse_plan_id: "p"\npart_id: "a"\n'
        "covered_before_truncation:\n  - what: the first half\n"
        'proposed_subparts:\n  - part_id: "a-1"\n    title: first\n'
        '  - part_id: "a-2"\n    title: second\n'
    )
    assert outcome.part_id == "a"
    assert len(outcome.covered_before_truncation) == 1
    assert [s.part_id for s in outcome.proposed_subparts] == ["a-1", "a-2"]
    assert "never believed" in outcome.to_mapping()["coverage_claim_note"]


# --- identifiers -----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "identifier",
    ["a", "Note 3", "Item 7A", "partie un", "第一部分", "a-very-ordinary-identifier"],
)
def test_an_identifier_a_model_chose_is_returned_exactly_as_written(identifier: str) -> None:
    assert require_part_identifier(identifier) == identifier


@pytest.mark.parametrize("identifier", ["", "   ", "\t\n"])
def test_an_empty_identifier_is_refused(identifier: str) -> None:
    with pytest.raises(UnsafePartIdentifierError, match="empty"):
        require_part_identifier(identifier)


def test_an_identifier_longer_than_the_bound_is_refused_as_content() -> None:
    with pytest.raises(UnsafePartIdentifierError, match="exceeds"):
        require_part_identifier("x" * (MAX_PART_IDENTIFIER_CHARACTERS + 1))


def test_an_identifier_carrying_a_control_character_is_refused() -> None:
    with pytest.raises(UnsafePartIdentifierError, match="control"):
        require_part_identifier("part\x00one")


def test_two_identifiers_that_sanitise_alike_still_get_different_storage_tokens() -> None:
    """The digest is not decoration: without it the second parse would overwrite the first."""
    assert storage_token("Note 3") != storage_token("note-3")
    assert storage_token("Note 3") == storage_token("Note 3")


def test_a_storage_token_can_never_traverse_a_path() -> None:
    for hostile in ("../../etc/passwd", "..", ".", "a/b/c", "C:\\windows"):
        token = storage_token(hostile)
        assert "/" not in token and "\\" not in token and ".." not in token
        assert token.replace("-", "").isalnum()


def test_a_storage_token_for_an_identifier_with_no_safe_characters_is_still_usable() -> None:
    token = storage_token("！！！")
    assert token.startswith("part-")
    assert len(token) > len("part-")
