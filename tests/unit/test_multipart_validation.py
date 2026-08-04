"""Structural validation of a plan, a part and an assembly — and what it refuses to judge.

THE DIVIDING LINE, RESTATED AS TESTS. Three conditions stop work, because each makes the QUEUE
impossible: no schedulable part, a duplicate identifier, a dependency cycle. Everything else — a
thin plan, an odd title, an unfamiliar status, material the model could not place — is a FINDING on
a result that is still scheduled, still stored and still reviewed.

The tests that matter most here are the ones asserting what does NOT fail. A validator that quietly
grew a taste for well-formed plans would be a filing taxonomy arriving through the back door.
"""

from __future__ import annotations

from decimal import Decimal

from packages.multipart import (
    AssembledPart,
    AssemblyInputs,
    AssemblyStatus,
    ProposedPart,
    acceptable_new_parts,
    assemble,
    read_part,
    read_plan,
    storage_token,
    validate_assembly,
    validate_part,
    validate_plan,
)


def _plan(body: str) -> object:
    return read_plan(body)


GOOD_PLAN = """parse_plan_id: "p"
parts:
  - part_id: "a"
    order: 1
    title: first
  - part_id: "b"
    order: 2
    title: second
    depends_on: ["a"]
"""


def test_a_well_formed_plan_is_schedulable_and_reports_nothing_alarming() -> None:
    result = validate_plan(read_plan(GOOD_PLAN))
    assert result.schedulable is True
    assert result.findings == ()
    assert result.schedulable_part_count == 2


def test_a_duplicate_part_identifier_stops_the_queue_and_names_the_identifier() -> None:
    result = validate_plan(
        read_plan(
            'parse_plan_id: "p"\nparts:\n'
            '  - part_id: "a"\n    order: 1\n    title: one\n'
            '  - part_id: "a"\n    order: 2\n    title: two\n'
        )
    )
    assert result.schedulable is False
    assert result.duplicate_part_ids == ("a",)
    assert any("more than once" in f for f in result.findings)


def test_a_dependency_cycle_is_reported_as_the_path_that_closes_it() -> None:
    result = validate_plan(
        read_plan(
            'parse_plan_id: "p"\nparts:\n'
            '  - part_id: "a"\n    order: 1\n    title: one\n    depends_on: ["b"]\n'
            '  - part_id: "b"\n    order: 2\n    title: two\n    depends_on: ["a"]\n'
        )
    )
    assert result.schedulable is False
    assert set(result.dependency_cycle) == {"a", "b"}
    assert any("cycle" in f for f in result.findings)


def test_a_dependency_naming_no_part_is_a_finding_and_not_a_refusal() -> None:
    result = validate_plan(
        read_plan(
            'parse_plan_id: "p"\nparts:\n'
            '  - part_id: "a"\n    order: 1\n    title: one\n    depends_on: ["nowhere"]\n'
        )
    )
    assert result.schedulable is True, "a dangling dependency must not make the plan unrunnable"
    assert result.unresolved_dependencies == ("nowhere",)


def test_a_part_with_no_identifier_is_dropped_and_the_drop_is_reported() -> None:
    result = validate_plan(
        read_plan(
            'parse_plan_id: "p"\nparts:\n'
            "  - order: 1\n    title: an unnamed part\n"
            '  - part_id: "a"\n    order: 2\n    title: a named one\n'
        )
    )
    assert result.declared_part_count == 2
    assert result.schedulable_part_count == 1
    assert any("carry no part_id" in f for f in result.findings)


def test_a_plan_with_no_schedulable_part_is_refused_with_the_reason() -> None:
    result = validate_plan(read_plan('parse_plan_id: "p"\nparts: []\n'))
    assert result.schedulable is False
    assert any("nothing to queue" in f for f in result.findings)


def test_an_unfamiliar_part_type_is_never_a_finding() -> None:
    """MUTATION PROOF FOR THE WHOLE PACKAGE. There is no vocabulary and there must never be one."""
    result = validate_plan(
        read_plan(
            'parse_plan_id: "p"\nparts:\n'
            '  - part_id: "a"\n    order: 1\n    title: "Skedule Eye Eye"\n'
            "    type: a kind invented on the spot\n"
        )
    )
    assert result.schedulable is True
    assert result.findings == (), f"a model-chosen label produced a finding: {result.findings}"


def test_model_declared_uncertainty_is_surfaced_rather_than_swallowed() -> None:
    result = validate_plan(
        read_plan(
            'parse_plan_id: "p"\nparts:\n  - part_id: "a"\n    order: 1\n    title: one\n'
            "unassigned:\n  - what: something\n"
            "uncertainty:\n  - note: unsure\n"
        )
    )
    assert result.schedulable is True
    assert result.unassigned_count == 1
    assert result.uncertainty_count == 1
    assert len(result.findings) == 2


# --- parts -----------------------------------------------------------------------------------------


def test_a_part_that_names_the_right_plan_and_part_is_usable() -> None:
    part = read_part(
        'parse_plan_id: "p"\npart_id: "a"\nstatus: complete\nnodes:\n  - id: "n"\nunresolved: []\n'
    )
    result = validate_part(part, expected_plan_id="p", expected_part_id="a", known_part_ids=set())
    assert result.usable is True
    assert result.findings == ()


def test_a_part_that_names_a_different_part_is_reported_and_is_not_usable() -> None:
    part = read_part('parse_plan_id: "p"\npart_id: "somewhere-else"\nstatus: complete\nnodes: []\n')
    result = validate_part(part, expected_plan_id="p", expected_part_id="a", known_part_ids=set())
    assert result.usable is False
    assert any("this task asked for" in f for f in result.findings)


def test_a_part_declaring_completion_with_no_nodes_is_reported() -> None:
    part = read_part('parse_plan_id: "p"\npart_id: "a"\nstatus: complete\nnodes: []\n')
    result = validate_part(part, expected_plan_id="p", expected_part_id="a", known_part_ids=set())
    assert any("no nodes" in f for f in result.findings)


def test_a_proposed_subpart_reusing_an_existing_identifier_is_reported() -> None:
    part = read_part(
        'parse_plan_id: "p"\npart_id: "a"\nstatus: needs_subparts\n'
        'proposed_subparts:\n  - part_id: "b"\n    title: taken\n'
    )
    result = validate_part(
        part, expected_plan_id="p", expected_part_id="a", known_part_ids={"a", "b"}
    )
    assert result.colliding_subpart_ids == ("b",)


def test_a_colliding_proposal_is_rejected_and_never_renamed() -> None:
    """Renaming would put a backend-invented identifier into the model's own plan."""
    proposed = (
        ProposedPart("b", storage_token("b"), 1, "taken", "", ""),
        ProposedPart("c", storage_token("c"), 2, "free", "", ""),
    )
    accepted, rejected = acceptable_new_parts(proposed, known_part_ids={"a", "b"})
    assert [p.part_id for p in accepted] == ["c"]
    assert rejected == ("b",)


def test_two_proposals_sharing_an_identifier_keep_only_the_first() -> None:
    proposed = (
        ProposedPart("d", storage_token("d"), 1, "first", "", ""),
        ProposedPart("d", storage_token("d"), 2, "second", "", ""),
    )
    accepted, rejected = acceptable_new_parts(proposed, known_part_ids=set())
    assert [p.title for p in accepted] == ["first"]
    assert rejected == ("d",)


# --- assemblies --------------------------------------------------------------------------------------


def _assembly(**overrides: object) -> dict:
    base = {
        "parts_expected": 2,
        "parts": [
            {
                "part_id": "a",
                "parent_part_id": None,
                "terminal": True,
                "unresolved_count": 0,
                "reference_filenames": ["primary.htm"],
            },
            {
                "part_id": "b",
                "parent_part_id": "a",
                "terminal": True,
                "unresolved_count": 0,
                "reference_filenames": [],
            },
        ],
        "tasks": [
            {"task_id": "t1", "state": "SUCCEEDED", "actual_cost_usd": "0.01", "surfaced": True},
            {"task_id": "t2", "state": "SUCCEEDED", "actual_cost_usd": "0.02", "surfaced": True},
        ],
        "total_cost_usd": "0.03",
        "reconciliation_cycles": 1,
        "unresolved_item_count": 0,
    }
    base.update(overrides)
    return base


def test_a_consistent_assembly_reports_nothing_and_claims_no_completeness() -> None:
    result = validate_assembly(_assembly(), source_filenames={"primary.htm"})
    assert result.consistent is True
    assert result.findings == ()
    assert "NOT a completeness verdict" in result.to_mapping()["verdict_note"]


def test_a_part_with_no_terminal_result_is_reported_as_incomplete_work() -> None:
    """INCOMPLETE WORK AND AN INCONSISTENT INDEX ARE DIFFERENT THINGS, REPORTED SEPARATELY.

    `consistent` asks whether the index describes itself correctly: no duplicate identifier, no
    orphan, no reference to an artifact nobody sent, no hidden failure, totals that add up. An index
    can be perfectly consistent about a parse that has not finished — and the ASSEMBLY STATUS is
    what carries that, as INCOMPLETE_WORK. Collapsing both into one boolean would leave a reviewer
    unable to tell "the parse is unfinished" from "the index is wrong about itself", which need
    different actions.
    """
    parts = _assembly()["parts"]
    parts[1]["terminal"] = False
    result = validate_assembly(_assembly(parts=parts), source_filenames={"primary.htm"})
    assert result.parts_with_a_terminal_result == 1
    assert result.parts_expected == 2
    assert any("reached no terminal result" in f for f in result.findings)
    assert result.consistent is True, "the index itself is coherent; the PARSE is unfinished"


def test_an_orphan_subpart_is_reported_rather_than_dropped() -> None:
    parts = _assembly()["parts"]
    parts[1]["parent_part_id"] = "a-part-that-is-not-here"
    result = validate_assembly(_assembly(parts=parts), source_filenames={"primary.htm"})
    assert result.orphan_subpart_ids == ("b",)


def test_a_reference_naming_an_artifact_that_was_never_submitted_is_reported() -> None:
    parts = _assembly()["parts"]
    parts[0]["reference_filenames"] = ["a-file-nobody-sent.htm"]
    result = validate_assembly(_assembly(parts=parts), source_filenames={"primary.htm"})
    assert result.unknown_reference_filenames == ("a-file-nobody-sent.htm",)


def test_a_failed_task_that_is_not_surfaced_is_reported() -> None:
    tasks = _assembly()["tasks"]
    tasks.append({"task_id": "t3", "state": "FAILED", "actual_cost_usd": "0", "surfaced": False})
    result = validate_assembly(_assembly(tasks=tasks), source_filenames={"primary.htm"})
    assert result.hidden_failed_tasks == ("t3",)


def test_a_total_that_does_not_add_up_means_a_task_was_dropped_or_double_counted() -> None:
    result = validate_assembly(_assembly(total_cost_usd="0.99"), source_filenames={"primary.htm"})
    assert result.cost_reconciles is False
    assert Decimal(result.recomputed_cost_usd) == Decimal("0.03")
    assert any("does not equal" in f for f in result.findings)


def test_unresolved_items_are_carried_into_review_rather_than_hidden() -> None:
    result = validate_assembly(_assembly(unresolved_item_count=4), source_filenames={"primary.htm"})
    assert result.unresolved_items == 4
    assert any("carried into review" in f for f in result.findings)


# --- the empty-parse defect, found by a real run and fixed ---------------------------------------
#
# A planning call failed against a live provider. The parse then had zero parts and zero expected
# parts, `terminal < parts_expected` was `0 < 0`, and a filing nothing had been produced for
# reported MECHANICALLY_ASSEMBLED. An emptiness that satisfies every count is the most dangerous
# shape a status check can have, so both conditions are now checked explicitly.


def _inputs(**overrides: object) -> AssemblyInputs:
    fields: dict = {
        "filing": {},
        "source_set": {},
        "routing": {},
        "prompts": [],
        "plan": {},
        "parts": [],
        "tasks": [],
        "reconciliations": [],
        "gap_repairs": [],
        "replans": [],
        "image_coverage": {},
        "reconciliation_cycles": 0,
        "reconciliation_cycle_limit": 3,
        "recursion_depth_limit": 4,
        "parts_expected": 0,
        "model_declared_complete": False,
    }
    fields.update(overrides)
    return AssemblyInputs(**fields)  # type: ignore[arg-type]


def _part(part_id: str, *, terminal: bool = True) -> AssembledPart:
    return AssembledPart(
        part_id=part_id,
        storage_token=storage_token(part_id),
        task_id="tsk_" + "a" * 26,
        parent_part_id=None,
        order=1,
        title="a title",
        type_label="a kind",
        declared_status="complete",
        task_state="SUCCEEDED" if terminal else "TRUNCATED",
        terminal=terminal,
        truncated=not terminal,
        node_count=1,
        table_count=0,
        unresolved_count=0,
        reference_count=0,
        references_resolved=0,
        reference_filenames=(),
        image_reference_count=0,
        input_tokens=0,
        output_tokens=0,
        latency_ms=0,
        actual_cost_usd=Decimal(0),
        stop_reason="end_turn",
        prompt_identity="p@1",
    )


def test_a_parse_whose_plan_never_returned_is_incomplete_work() -> None:
    assembly = assemble(_inputs(plan_available=False))
    assert assembly["status"] == AssemblyStatus.INCOMPLETE_WORK.value
    assert assembly["mechanically_assembled"] is False
    assert assembly["plan_available"] is False


def test_a_parse_with_no_parts_is_incomplete_work_even_when_a_plan_exists() -> None:
    assembly = assemble(_inputs(plan_available=True, parts=[], parts_expected=0))
    assert assembly["status"] == AssemblyStatus.INCOMPLETE_WORK.value


def test_a_parse_with_every_planned_part_terminal_is_mechanically_assembled() -> None:
    """MUTATION PROOF. The guard above must not have made every parse incomplete."""
    assembly = assemble(
        _inputs(parts=[_part("a"), _part("b")], parts_expected=2, plan_available=True)
    )
    assert assembly["status"] == AssemblyStatus.MECHANICALLY_ASSEMBLED.value
    assert assembly["mechanically_assembled"] is True
    assert assembly["human_review_required"] is True


def test_a_truncated_part_leaves_the_parse_incomplete() -> None:
    assembly = assemble(_inputs(parts=[_part("a"), _part("b", terminal=False)], parts_expected=2))
    assert assembly["status"] == AssemblyStatus.INCOMPLETE_WORK.value
    assert assembly["truncation_events"] == 1
