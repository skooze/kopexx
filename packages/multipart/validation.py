"""Generic structural validation of a model-directed plan, its parts, and the assembly.

WHAT THESE CHECKS ANSWER. Can this be scheduled? Can this be stored? Does it refer to things that
exist? Do the totals add up? Every one is a question about STRUCTURE, and every one has an answer
a machine can produce without knowing what a filing is.

WHAT THEY REFUSE TO ANSWER. Whether the model divided the filing sensibly. Whether a part is thin.
Whether two parts are really the same section. Whether the plan covers the disclosure. Those need
either a semantic parser — forbidden — or a person, and a person is what the review UI is for.

A FINDING IS NOT A REFUSAL. Almost everything here produces a finding on a result that still gets
scheduled, stored and reviewed. Only three conditions stop work: a plan with no schedulable part, a
duplicate part identifier, and a dependency cycle. Each of those makes the queue itself impossible
rather than the parse unconvincing.

    A duplicate identifier is fatal for a concrete reason, not a stylistic one: two parts sharing
    an identifier cannot be told apart in the assembly, in a citation, in a rerun or in a comment,
    and the second would silently replace the first.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from .envelopes import ParsePlan, PartArtifact, PartStatus, ProposedPart


@dataclass(frozen=True)
class PlanValidation:
    """Whether a plan can be scheduled, and everything a reviewer should know about it."""

    schedulable: bool
    findings: tuple[str, ...]
    plan_id: str
    declared_part_count: int
    schedulable_part_count: int
    duplicate_part_ids: tuple[str, ...]
    unresolved_dependencies: tuple[str, ...]
    dependency_cycle: tuple[str, ...]
    missing_envelope_keys: tuple[str, ...]
    unassigned_count: int
    uncertainty_count: int
    expected_output_tokens_total: int

    def to_mapping(self) -> dict[str, Any]:
        return {
            "schema_version": "multipart-plan-validation-v1",
            "schedulable": self.schedulable,
            "findings": list(self.findings),
            "parse_plan_id": self.plan_id,
            "declared_part_count": self.declared_part_count,
            "schedulable_part_count": self.schedulable_part_count,
            "duplicate_part_ids": list(self.duplicate_part_ids),
            "unresolved_dependencies": list(self.unresolved_dependencies),
            "dependency_cycle": list(self.dependency_cycle),
            "missing_envelope_keys": list(self.missing_envelope_keys),
            "model_declared_unassigned": self.unassigned_count,
            "model_declared_uncertainty": self.uncertainty_count,
            "model_expected_output_tokens_total": self.expected_output_tokens_total,
            "scope_note": (
                "structure and schedulability only. Nothing here judges whether the model divided "
                "the filing well; that is a human judgement made in the review UI."
            ),
        }


def _find_cycle(edges: dict[str, tuple[str, ...]]) -> tuple[str, ...]:
    """One dependency cycle, as the path that closes it, or an empty tuple.

    Returned as a PATH rather than a boolean because "the plan has a cycle" sends a reviewer
    looking through every part, and `a -> b -> c -> a` sends them to three.
    """
    visiting: set[str] = set()
    done: set[str] = set()
    trail: list[str] = []

    def walk(node: str) -> tuple[str, ...]:
        if node in done:
            return ()
        if node in visiting:
            start = trail.index(node)
            return tuple(trail[start:] + [node])
        visiting.add(node)
        trail.append(node)
        for nxt in edges.get(node, ()):
            if nxt not in edges:
                continue
            found = walk(nxt)
            if found:
                return found
        trail.pop()
        visiting.discard(node)
        done.add(node)
        return ()

    for node in edges:
        found = walk(node)
        if found:
            return found
    return ()


def validate_plan(plan: ParsePlan) -> PlanValidation:
    """Check one plan for everything that would stop it being queued."""
    findings: list[str] = []
    declared = len(plan.raw.get("parts") or []) if isinstance(plan.raw.get("parts"), list) else 0

    if not plan.plan_id:
        findings.append(
            "the plan declares no parse_plan_id, so nothing produced from it can be attributed "
            "to it"
        )
    if plan.missing_envelope_keys:
        findings.append(
            "the provisional plan envelope is missing: " + ", ".join(plan.missing_envelope_keys)
        )
    if declared > len(plan.parts):
        findings.append(
            f"{declared - len(plan.parts)} declared part(s) carry no part_id and cannot be "
            "scheduled, cited or rerun; they were dropped from the schedulable plan and the exact "
            "response is preserved"
        )

    seen: dict[str, int] = {}
    for part in plan.parts:
        seen[part.part_id] = seen.get(part.part_id, 0) + 1
    duplicates = tuple(sorted(identifier for identifier, count in seen.items() if count > 1))
    if duplicates:
        findings.append(
            f"{len(duplicates)} part identifier(s) appear more than once: {', '.join(duplicates)}. "
            "Two parts sharing an identifier cannot be told apart in the assembly, in a citation "
            "or in a rerun."
        )

    known = set(plan.part_ids)
    unresolved = tuple(
        sorted(
            {
                dependency
                for part in plan.parts
                for dependency in part.depends_on
                if dependency not in known
            }
        )
    )
    if unresolved:
        findings.append(
            f"{len(unresolved)} declared dependency target(s) name no part in this plan: "
            + ", ".join(unresolved)
        )

    cycle = _find_cycle({p.part_id: p.depends_on for p in plan.parts})
    if cycle:
        findings.append("the declared dependencies contain a cycle: " + " -> ".join(cycle))

    bad_sizing = [
        part.part_id
        for part in plan.parts
        if part.expected_output_tokens is not None and part.expected_output_tokens <= 0
    ]
    if bad_sizing:
        findings.append(
            "expected_output_tokens is not a positive integer on: " + ", ".join(sorted(bad_sizing))
        )

    if not plan.parts:
        findings.append(
            "the plan proposes no part with an identifier, so there is nothing to queue"
        )
    if plan.unassigned:
        findings.append(
            f"the model declared {len(plan.unassigned)} piece(s) of filing material it could not "
            "yet assign to a part"
        )
    if plan.uncertainty:
        findings.append(
            f"the model declared {len(plan.uncertainty)} uncertainty item(s) in the plan"
        )

    return PlanValidation(
        schedulable=bool(plan.parts) and not duplicates and not cycle,
        findings=tuple(findings),
        plan_id=plan.plan_id,
        declared_part_count=declared,
        schedulable_part_count=len(plan.parts),
        duplicate_part_ids=duplicates,
        unresolved_dependencies=unresolved,
        dependency_cycle=cycle,
        missing_envelope_keys=plan.missing_envelope_keys,
        unassigned_count=len(plan.unassigned),
        uncertainty_count=len(plan.uncertainty),
        expected_output_tokens_total=sum(
            p.expected_output_tokens or 0 for p in plan.parts if (p.expected_output_tokens or 0) > 0
        ),
    )


@dataclass(frozen=True)
class PartValidation:
    """Whether one part response is the part that was asked for, structurally."""

    findings: tuple[str, ...]
    plan_id_matches: bool
    part_id_matches: bool
    status_recognised: bool
    declared_status: str
    proposed_subpart_count: int
    colliding_subpart_ids: tuple[str, ...]
    duplicate_subpart_ids: tuple[str, ...]
    missing_envelope_keys: tuple[str, ...]
    node_count: int
    unresolved_count: int

    @property
    def usable(self) -> bool:
        """Whether the artifact can be attributed to its plan and part at all.

        NOT a quality verdict. A part that matches its identifiers is usable in the assembly even
        when it declares itself unable to complete — the declaration is the useful part.
        """
        return self.plan_id_matches and self.part_id_matches

    def to_mapping(self) -> dict[str, Any]:
        return {
            "schema_version": "multipart-part-validation-v1",
            "findings": list(self.findings),
            "plan_id_matches": self.plan_id_matches,
            "part_id_matches": self.part_id_matches,
            "status_recognised": self.status_recognised,
            "declared_status": self.declared_status,
            "proposed_subpart_count": self.proposed_subpart_count,
            "colliding_subpart_ids": list(self.colliding_subpart_ids),
            "duplicate_subpart_ids": list(self.duplicate_subpart_ids),
            "missing_envelope_keys": list(self.missing_envelope_keys),
            "node_count": self.node_count,
            "unresolved_count": self.unresolved_count,
            "usable": self.usable,
        }


def validate_part(
    part: PartArtifact, *, expected_plan_id: str, expected_part_id: str, known_part_ids: set[str]
) -> PartValidation:
    """Check one part response against the plan and the part it was asked to produce."""
    findings: list[str] = []
    plan_ok = bool(part.plan_id) and part.plan_id == expected_plan_id
    part_ok = bool(part.part_id) and part.part_id == expected_part_id

    if not plan_ok:
        findings.append(
            f"the response names plan {part.plan_id!r} and this task belongs to "
            f"{expected_plan_id!r}"
        )
    if not part_ok:
        findings.append(
            f"the response names part {part.part_id!r} and this task asked for {expected_part_id!r}"
        )
    if part.status is PartStatus.UNRECOGNISED:
        findings.append(
            f"the declared status {part.declared_status!r} is not one of the workflow statuses "
            "this protocol defines. It is preserved exactly and treated as unfinished."
        )
    if part.missing_envelope_keys:
        findings.append(
            "the provisional part envelope is missing: " + ", ".join(part.missing_envelope_keys)
        )
    if not part.nodes and part.status is PartStatus.COMPLETE:
        findings.append(
            "the part declares itself complete and carries no nodes, so it represents no filing "
            "content"
        )
    if part.unresolved:
        findings.append(
            f"the model declared {len(part.unresolved)} unresolved item(s) in this part"
        )

    proposed_ids = [s.part_id for s in part.proposed_subparts]
    duplicates = tuple(sorted({i for i in proposed_ids if proposed_ids.count(i) > 1}))
    collisions = tuple(sorted({i for i in proposed_ids if i in known_part_ids}))
    if duplicates:
        findings.append("proposed subparts repeat an identifier: " + ", ".join(duplicates))
    if collisions:
        findings.append(
            "proposed subparts reuse an identifier the plan already carries: "
            + ", ".join(collisions)
        )

    return PartValidation(
        findings=tuple(findings),
        plan_id_matches=plan_ok,
        part_id_matches=part_ok,
        status_recognised=part.status is not PartStatus.UNRECOGNISED,
        declared_status=part.declared_status,
        proposed_subpart_count=len(part.proposed_subparts),
        colliding_subpart_ids=collisions,
        duplicate_subpart_ids=duplicates,
        missing_envelope_keys=part.missing_envelope_keys,
        node_count=part.node_count,
        unresolved_count=len(part.unresolved),
    )


def acceptable_new_parts(
    proposed: tuple[ProposedPart, ...], *, known_part_ids: set[str]
) -> tuple[tuple[ProposedPart, ...], tuple[str, ...]]:
    """Split proposed parts into the ones that can be queued and the identifiers that cannot.

    A proposal that reuses an existing identifier is REJECTED rather than renamed. Renaming it
    would put a backend-invented identifier into the model's own plan, and the next request would
    then ask the model for a part it never proposed.
    """
    accepted: list[ProposedPart] = []
    rejected: list[str] = []
    seen = set(known_part_ids)
    for candidate in proposed:
        if candidate.part_id in seen:
            rejected.append(candidate.part_id)
            continue
        seen.add(candidate.part_id)
        accepted.append(candidate)
    return tuple(accepted), tuple(rejected)


@dataclass(frozen=True)
class AssemblyValidation:
    """Whether the mechanically assembled index is internally consistent."""

    findings: tuple[str, ...]
    consistent: bool
    parts_expected: int
    parts_with_a_terminal_result: int
    duplicate_part_ids: tuple[str, ...]
    orphan_subpart_ids: tuple[str, ...]
    unknown_reference_filenames: tuple[str, ...]
    hidden_failed_tasks: tuple[str, ...]
    cost_reconciles: bool
    declared_cost_usd: str
    recomputed_cost_usd: str
    reconciliation_cycles: int
    unresolved_items: int
    checks: tuple[str, ...] = field(default_factory=tuple)

    def to_mapping(self) -> dict[str, Any]:
        return {
            "schema_version": "multipart-assembly-validation-v1",
            "findings": list(self.findings),
            "consistent": self.consistent,
            "parts_expected": self.parts_expected,
            "parts_with_a_terminal_result": self.parts_with_a_terminal_result,
            "duplicate_part_ids": list(self.duplicate_part_ids),
            "orphan_subpart_ids": list(self.orphan_subpart_ids),
            "unknown_reference_filenames": list(self.unknown_reference_filenames),
            "hidden_failed_tasks": list(self.hidden_failed_tasks),
            "cost_reconciles": self.cost_reconciles,
            "declared_cost_usd": self.declared_cost_usd,
            "recomputed_cost_usd": self.recomputed_cost_usd,
            "reconciliation_cycles": self.reconciliation_cycles,
            "unresolved_items": self.unresolved_items,
            "checks_run": list(self.checks),
            "verdict_note": (
                "internal consistency of the index only. It is NOT a completeness verdict: nothing "
                "measured here establishes that every human-readable source range is represented."
            ),
        }


_ASSEMBLY_CHECKS: tuple[str, ...] = (
    "every planned terminal part has a terminal result",
    "no duplicate part identifier",
    "no orphan subpart",
    "every source reference names a submitted source member",
    "reconciliation cycles recorded",
    "unresolved items surfaced",
    "no hidden failed task",
    "cost totals reconcile",
)


def validate_assembly(
    assembly: dict[str, Any], *, source_filenames: set[str]
) -> AssemblyValidation:
    """Check the assembled index against itself and against the source set it claims to cover."""
    findings: list[str] = []
    parts = list(assembly.get("parts") or [])
    identifiers = [str(p.get("part_id") or "") for p in parts]
    duplicates = tuple(sorted({i for i in identifiers if i and identifiers.count(i) > 1}))
    if duplicates:
        findings.append("the assembly carries duplicate part identifiers: " + ", ".join(duplicates))

    expected = int(assembly.get("parts_expected") or len(parts))
    terminal = sum(1 for p in parts if p.get("terminal"))
    if terminal < expected:
        findings.append(
            f"{expected - terminal} planned part(s) reached no terminal result. The parse is "
            "incomplete work, not a partial answer."
        )

    known = set(identifiers)
    orphans = tuple(
        sorted(
            {
                str(p.get("part_id") or "")
                for p in parts
                if p.get("parent_part_id") and str(p["parent_part_id"]) not in known
            }
        )
    )
    if orphans:
        findings.append(
            "subpart(s) name a parent that is not in the assembly: " + ", ".join(orphans)
        )

    unknown_files = tuple(
        sorted(
            {
                str(name)
                for p in parts
                for name in (p.get("reference_filenames") or ())
                if name and str(name) not in source_filenames
            }
        )
    )
    if unknown_files:
        findings.append(
            "source reference(s) name an artifact that was never submitted: "
            + ", ".join(unknown_files)
        )

    hidden = tuple(
        sorted(
            str(t.get("task_id") or "")
            for t in (assembly.get("tasks") or [])
            if t.get("state") in {"FAILED", "INTERRUPTED"} and not t.get("surfaced")
        )
    )
    if hidden:
        findings.append("failed or interrupted task(s) are not surfaced: " + ", ".join(hidden))

    declared = Decimal(str(assembly.get("total_cost_usd") or "0"))
    recomputed = sum(
        (Decimal(str(t.get("actual_cost_usd") or "0")) for t in (assembly.get("tasks") or [])),
        Decimal(0),
    )
    reconciles = declared == recomputed
    if not reconciles:
        findings.append(
            f"the declared total of USD {declared} does not equal the sum of the task costs, "
            f"USD {recomputed}. A total that does not add up means a task was dropped from the "
            "index or counted twice."
        )

    cycles = int(assembly.get("reconciliation_cycles") or 0)
    unresolved = int(assembly.get("unresolved_item_count") or 0)
    if unresolved:
        findings.append(f"{unresolved} unresolved item(s) are carried into review")

    return AssemblyValidation(
        findings=tuple(findings),
        consistent=not (duplicates or orphans or unknown_files or hidden or not reconciles),
        parts_expected=expected,
        parts_with_a_terminal_result=terminal,
        duplicate_part_ids=duplicates,
        orphan_subpart_ids=orphans,
        unknown_reference_filenames=unknown_files,
        hidden_failed_tasks=hidden,
        cost_reconciles=reconciles,
        declared_cost_usd=str(declared),
        recomputed_cost_usd=str(recomputed),
        reconciliation_cycles=cycles,
        unresolved_items=unresolved,
        checks=_ASSEMBLY_CHECKS,
    )
