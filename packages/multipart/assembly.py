"""Mechanical assembly of one filing's multipart parse. An INDEX, never a rewritten parse.

WHAT ASSEMBLY IS PERMITTED TO DO. Order parts using the model's own `order`. Nest them using the
model's own `parent_part_id`. Link stable identifiers. Count nodes, tables, references and
unresolved items. Add up cost, tokens and latency. Present.

WHAT IT IS FORBIDDEN TO DO, LISTED BECAUSE EVERY ONE OF THEM WOULD LOOK LIKE AN IMPROVEMENT.
Rename a part title. Rename a node type. Merge two parts whose titles resemble each other. Rewrite
model prose. Move a table from one part to another. Reassign anything. Drop a part as redundant.
Deduplicate content. Impose a canonical vocabulary. Each of those is the backend deciding what
filing content MEANS, which rules.md section 21 rule 1 forbids and which this project has already
built twice and deleted twice.

    The exact individual model responses remain the authoritative artifacts. This index tells a
    reviewer where they are and how they relate, using only relations the model itself declared.

WHY THE RESULT IS FLAT WITH A DEPTH COLUMN RATHER THAN NESTED. A nested document has to be walked
to be validated, walked again to be rendered, and walked a third time to be counted — and each walk
is a chance to lose a branch. A flat list in depth-first order carries the same information, is
checkable in one pass, and makes an orphaned subpart visible instead of unreachable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum
from typing import Any


class AssemblyStatus(StrEnum):
    """The headline state of one assembled parse.

    THERE IS NO `COMPLETE`. The strongest thing this project can say about a multipart parse is
    that every planned part reached a terminal result, that reconciliation ran to a conclusion, and
    that a person can now look at it. Proving that every human-readable source range is represented
    is not something any of these signals establishes, and a status value that existed would
    eventually be set.
    """

    INCOMPLETE_WORK = "INCOMPLETE_WORK"
    RECONCILIATION_UNRESOLVED = "RECONCILIATION_UNRESOLVED"
    MECHANICALLY_ASSEMBLED = "MECHANICALLY_ASSEMBLED"


@dataclass(frozen=True)
class AssembledPart:
    """One part's place in the index, built from the task that produced it.

    `title` and `type_label` are the MODEL's words, copied. `nodes` is the model's own node list,
    untouched — not re-keyed, not re-ordered, not merged with any other part's.
    """

    part_id: str
    storage_token: str
    task_id: str
    parent_part_id: str | None
    order: int
    title: str
    type_label: str
    declared_status: str
    task_state: str
    terminal: bool
    truncated: bool
    node_count: int
    table_count: int
    unresolved_count: int
    reference_count: int
    references_resolved: int
    reference_filenames: tuple[str, ...]
    image_reference_count: int
    input_tokens: int
    output_tokens: int
    latency_ms: int
    actual_cost_usd: Decimal
    stop_reason: str
    prompt_identity: str
    nodes: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    unresolved: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    coverage_summary: str = ""
    depth: int = 0

    def to_mapping(self) -> dict[str, Any]:
        return {
            "part_id": self.part_id,
            "storage_token": self.storage_token,
            "task_id": self.task_id,
            "parent_part_id": self.parent_part_id,
            "order": self.order,
            "depth": self.depth,
            "title": self.title,
            "type": self.type_label,
            "declared_status": self.declared_status,
            "task_state": self.task_state,
            "terminal": self.terminal,
            "truncated": self.truncated,
            "node_count": self.node_count,
            "table_count": self.table_count,
            "unresolved_count": self.unresolved_count,
            "reference_count": self.reference_count,
            "references_resolved": self.references_resolved,
            "reference_filenames": list(self.reference_filenames),
            "image_reference_count": self.image_reference_count,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "latency_ms": self.latency_ms,
            "actual_cost_usd": str(self.actual_cost_usd),
            "stop_reason": self.stop_reason,
            "prompt": self.prompt_identity,
            "coverage_summary": self.coverage_summary,
            "nodes": list(self.nodes),
            "unresolved": list(self.unresolved),
        }


def order_parts(parts: list[AssembledPart]) -> list[AssembledPart]:
    """Depth-first over the model's declared parent/child relations, in the model's declared order.

    A part naming a parent that is not present keeps its own place at the top level rather than
    disappearing. That is deliberate: an orphan is a finding `validate_assembly` reports, and a
    tree-builder that silently dropped unreachable nodes would delete the evidence for it.
    """
    by_parent: dict[str | None, list[AssembledPart]] = {}
    present = {p.part_id for p in parts}
    for part in parts:
        parent = part.parent_part_id if part.parent_part_id in present else None
        by_parent.setdefault(parent, []).append(part)
    for siblings in by_parent.values():
        siblings.sort(key=lambda p: (p.order, p.part_id))

    ordered: list[AssembledPart] = []
    seen: set[str] = set()

    def walk(parent: str | None, depth: int) -> None:
        for part in by_parent.get(parent, ()):
            if part.part_id in seen:
                continue
            seen.add(part.part_id)
            ordered.append(
                AssembledPart(
                    **{**part.__dict__, "depth": depth},
                )
            )
            walk(part.part_id, depth + 1)

    walk(None, 0)
    # Anything a cycle among declared parents made unreachable is appended rather than lost.
    for part in parts:
        if part.part_id not in seen:
            seen.add(part.part_id)
            ordered.append(part)
    return ordered


@dataclass(frozen=True)
class AssemblyInputs:
    """Everything the index is built from, gathered by the orchestrator that owns each piece.

    Passed as mappings rather than as records from other packages on purpose: this module knows
    nothing about the evaluation store, the source-transport layer or the model catalog, and would
    be a dependency cycle waiting to happen if it did.
    """

    filing: dict[str, Any]
    source_set: dict[str, Any]
    routing: dict[str, Any]
    prompts: list[dict[str, Any]]
    plan: dict[str, Any]
    parts: list[AssembledPart]
    tasks: list[dict[str, Any]]
    reconciliations: list[dict[str, Any]]
    gap_repairs: list[dict[str, Any]]
    replans: list[dict[str, Any]]
    image_coverage: dict[str, Any]
    reconciliation_cycles: int
    reconciliation_cycle_limit: int
    recursion_depth_limit: int
    parts_expected: int
    model_declared_complete: bool
    #: Whether a READABLE plan exists at all.
    #:
    #: THIS FIELD EXISTS BECAUSE ITS ABSENCE WAS A DEFECT, FOUND BY A REAL RUN. When a planning
    #: call failed, the parse had zero parts and zero expected parts, `terminal < parts_expected`
    #: was `0 < 0`, and a filing nothing had been produced for reported MECHANICALLY_ASSEMBLED. An
    #: emptiness that satisfies every count is the most dangerous shape a status check can have.
    plan_available: bool = True
    budget_ceiling_usd: Decimal | None = None


def assemble(inputs: AssemblyInputs) -> dict[str, Any]:
    """Build the mechanical index for one filing's multipart parse."""
    ordered = order_parts(list(inputs.parts))
    terminal = sum(1 for p in ordered if p.terminal)
    unresolved_items = sum(p.unresolved_count for p in ordered)

    outstanding_reconciliation = bool(inputs.reconciliations) and not inputs.model_declared_complete
    # A PARSE WITH NO READABLE PLAN, OR NO PARTS AT ALL, IS INCOMPLETE WORK — NEVER ASSEMBLED.
    # Both conditions are checked explicitly rather than left to the arithmetic below, because
    # `0 < 0` is false and an empty parse would otherwise satisfy every count it was measured
    # against. A real planning failure produced exactly that.
    if not inputs.plan_available or not ordered or terminal < inputs.parts_expected:
        status = AssemblyStatus.INCOMPLETE_WORK
    elif outstanding_reconciliation:
        status = AssemblyStatus.RECONCILIATION_UNRESOLVED
    else:
        status = AssemblyStatus.MECHANICALLY_ASSEMBLED

    total_cost = sum(
        (Decimal(str(t.get("actual_cost_usd") or "0")) for t in inputs.tasks), Decimal(0)
    )
    return {
        "schema_version": "multipart-assembly-v1",
        "protocol": "model-directed multipart",
        "status": status.value,
        "status_note": (
            "MECHANICALLY_ASSEMBLED means every planned part reached a terminal result and the "
            "index is internally consistent. It is NOT a completeness verdict and never becomes "
            "one: proving that every human-readable source range is represented is not something "
            "these signals establish."
        ),
        # FOUR DISTINCT CLAIMS, NEVER COLLAPSED INTO ONE. Section 12.2 of the Phase 2.1 brief and
        # rules.md section 21 rule 5 both require it: mechanical completion, model-declared
        # completion, reference coverage and human approval answer different questions, and a
        # single boolean would answer the easiest one and imply the rest.
        "mechanically_assembled": status is not AssemblyStatus.INCOMPLETE_WORK,
        "plan_available": inputs.plan_available,
        "model_declared_complete": inputs.model_declared_complete,
        "reconciliation_unresolved": outstanding_reconciliation,
        "human_review_required": True,
        "filing": inputs.filing,
        "source_set": inputs.source_set,
        "model_routing": inputs.routing,
        "prompt_versions": list(inputs.prompts),
        "plan": inputs.plan,
        "parts_expected": inputs.parts_expected,
        "parts_with_a_terminal_result": terminal,
        "part_count": len(ordered),
        "parts": [p.to_mapping() for p in ordered],
        "tasks": list(inputs.tasks),
        "reconciliations": list(inputs.reconciliations),
        "reconciliation_cycles": inputs.reconciliation_cycles,
        "reconciliation_cycle_limit": inputs.reconciliation_cycle_limit,
        "recursion_depth_limit": inputs.recursion_depth_limit,
        "gap_repairs": list(inputs.gap_repairs),
        "replans": list(inputs.replans),
        "image_coverage": inputs.image_coverage,
        "unresolved_item_count": unresolved_items,
        "node_count": sum(p.node_count for p in ordered),
        "table_count": sum(p.table_count for p in ordered),
        "reference_count": sum(p.reference_count for p in ordered),
        "references_resolved": sum(p.references_resolved for p in ordered),
        "truncation_events": sum(1 for p in ordered if p.truncated),
        "total_input_tokens": sum(int(t.get("input_tokens") or 0) for t in inputs.tasks),
        "total_output_tokens": sum(int(t.get("output_tokens") or 0) for t in inputs.tasks),
        "total_latency_ms": sum(int(t.get("latency_ms") or 0) for t in inputs.tasks),
        "total_cost_usd": str(total_cost),
        "budget_ceiling_usd": (
            None if inputs.budget_ceiling_usd is None else str(inputs.budget_ceiling_usd)
        ),
        "maximum_single_response_output_tokens": max(
            (int(t.get("output_tokens") or 0) for t in inputs.tasks), default=0
        ),
        "assembly_note": (
            "an INDEX over the exact model responses, built only from relations the model itself "
            "declared. No title was renamed, no content merged, no table moved, no part dropped."
        ),
    }
