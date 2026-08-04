"""The SYNTHETIC half of every multipart request: one unfenced YAML 1.2 document per call.

WHAT A BRIEF IS. Mechanical labelling and the model's own prior output, handed back so the model
knows which piece of its own plan it is being asked for. Filing identity, source-artifact
filenames and hashes, the plan the model wrote, the part specification the model wrote, measured
sizing numbers, and — for reconciliation and gap repair — a deterministic inventory of what has
been produced.

WHAT A BRIEF IS NOT, AND THIS IS THE LINE THE WHOLE PHASE TURNS ON. It never names a filing
section. It never says which part should contain what. It never describes the filing's structure,
suggests a division, supplies a vocabulary, or tells the model what a heading means. Every
semantic word in a brief was written by the model on an earlier call. Search this module for a
filing-domain noun and there is none, and an architecture test fails the build if one appears.

WHY YAML AND NOT PROSE. rules.md section 3 permits exactly two synthetic forms: unmarked plain
text, or one unfenced YAML 1.2 document. A plan with ten parts, each with an identifier, an order,
a title and a purpose, is a structure; rendering it as prose would either lose the structure or
reinvent a markup for it. The briefs are therefore YAML, compiled through
`packages/llm_gateway.compile_yaml`, which validates the boundary on the way out.

WHY THE SIZING NUMBERS ARE IN THE BRIEF AND NOT IN THE PROMPT. A prompt version is immutable and
shared across five candidates with output caps from 8,000 to 32,000 tokens, one of which spends
part of its allowance on reasoning. Writing a number into the prompt would either be wrong for four
models or would need five prompts, and five prompts is five different questions.
"""

from __future__ import annotations

from typing import Any

from packages.multipart import ParsePlan, PlannedPart

from .sizing import OutputSizing

#: How each brief announces what it is. A short machine-readable label, never an instruction: the
#: instruction is the immutable prompt, and a brief that started giving instructions would be a
#: prompt that was not versioned.
PLANNING = "planning"
PART = "part"
REPLAN = "replan"
RECONCILE = "reconcile"
GAP = "gap"
REPAIR = "format_repair"


def _artifact_manifest(
    members: list[dict[str, Any]], *, images_submitted: bool
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Submitted artifacts and, separately, image-bearing members that were not analysed.

    The second list is why a text-only parser's run can never claim image coverage: the members
    are NAMED in every request, so the model is told what it was not shown, rather than the
    omission being invisible to it and to the reviewer.
    """
    submitted: list[dict[str, Any]] = []
    unanalysed: list[dict[str, Any]] = []
    for member in members:
        if not member.get("submitted"):
            continue
        entry = {
            "filename": member.get("filename") or "",
            "sha256": member.get("sha256") or "",
            "byte_count": member.get("byte_count") or 0,
        }
        is_image = str(member.get("disposition") or "").endswith("IMAGE")
        if is_image and not images_submitted:
            unanalysed.append(entry)
            continue
        submitted.append(entry)
    return submitted, unanalysed


def filing_brief(
    *,
    cik: str,
    accession: str,
    form_as_filed: str,
    filing_date: str,
    issuer_label: str,
    source_set_id: str,
    members: list[dict[str, Any]],
    images_submitted: bool,
) -> dict[str, Any]:
    """The mechanical identity of the filing and of the exact source set in front of the model."""
    submitted, unanalysed = _artifact_manifest(members, images_submitted=images_submitted)
    brief: dict[str, Any] = {
        "cik": cik,
        "accession": accession,
        "form_as_filed": form_as_filed,
        "filing_date": filing_date,
        "issuer_label": issuer_label,
        "source_set_id": source_set_id,
        "source_artifacts_in_filed_order": submitted,
        "artifact_labels_are": (
            "transport identifiers only. They carry no meaning and neither does their order beyond "
            "being the order in which they were filed."
        ),
    }
    if unanalysed:
        brief["image_members_filed_and_not_included"] = unanalysed
        brief["image_limitation"] = (
            "the selected parsing model has no verified image path, so these filed members were "
            "not included in this request. Anything that depends on them is unresolved."
        )
    return brief


def _plan_summary(plan: ParsePlan) -> dict[str, Any]:
    """The model's own plan, echoed back unchanged."""
    return {
        "parse_plan_id": plan.plan_id,
        "parts": [
            {
                "part_id": part.part_id,
                "order": part.order,
                "title": part.title,
                "type": part.type_label,
                "purpose": part.purpose,
                "depends_on": list(part.depends_on),
            }
            for part in plan.ordered()
        ],
    }


def mechanical_inventory(inventory: Any) -> dict[str, Any]:
    """The TABLE and IMAGE inventory the completeness prompts ask a model to account for.

    WHY THIS IS IN THE BRIEF AT ALL, GIVEN THAT THE BACKEND OWNS NO SEMANTIC DECISION. A model
    cannot account for something it was never told exists. Phase 2.1 asked for a complete parse and
    got `table_count` zero from all five candidates on both proof filings — and could not tell a
    model that had considered the tables and left them as prose from one that never noticed them,
    because nothing named them. Naming a `table` element is naming a syntactic construct the FILER
    put in the bytes, in the same sense as naming a member's declared media type.

    WHAT IS DELIBERATELY NOT IN IT. No title, no type, no classification, no statement that any of
    these tables matters. `first_cells` carries a handful of the element's own cell texts so a model
    can tell which table is being named without hunting for a byte offset; it is quotation, not
    description. Which elements carry data is the MODEL's judgement with source evidence, and a
    human reviewer's after it — `rules.md` section 21 rules 1 and 2.

    IT IS NOT AN INPUT FILTER. The complete compatible source set still goes to the model intact on
    this call and on every other one. This is a list of identifiers for material the model already
    has in front of it.
    """
    tables = [
        {
            "table_element_id": element.table_id,
            "member": element.member,
            "rows": element.row_count,
            "columns": element.max_columns,
            "cells": element.cell_count,
            "first_cells": [c.text for c in element.cells if c.text.strip()][:6],
        }
        for element in inventory.tables
    ]
    images = [
        {
            "image_id": image.filename,
            "member": image.member,
            "media_type": image.media_type,
            "width": image.width,
            "height": image.height,
        }
        for image in inventory.images
    ]
    return {
        "table_elements": tables,
        "table_element_count": len(tables),
        "images": images,
        "image_count": len(images),
        "visible_text_span_count": len(inventory.visible_spans),
        "visible_character_count": inventory.visible_character_count,
        "how_this_was_produced": (
            "by walking the preserved markup and recording where each table element and each "
            "filed image sits. Nothing that produced this list knows what a filing contains, and "
            "no entry here is a claim that the material matters."
        ),
        "what_is_asked_of_you": (
            "account for every table_element_id and every image_id: map it to a structured table "
            "or an image reference, classify it with source evidence, or declare it unresolved. "
            "Silence is not coverage."
        ),
    }


def planning_brief(
    *,
    filing: dict[str, Any],
    sizing: OutputSizing,
    inventory: Any = None,
) -> dict[str, Any]:
    """The brief for the first billable call of a multipart parse."""
    return {
        "brief": PLANNING,
        "filing": filing,
        **(
            {"mechanical_inventory": mechanical_inventory(inventory)}
            if inventory is not None
            else {}
        ),
        "sizing": {
            **sizing.to_mapping(),
            "this_call_returns": "a plan only",
            "later_part_calls_should_aim_for": sizing.visible_target_tokens,
        },
        "protocol": _protocol_note(),
    }


def part_brief(
    *,
    filing: dict[str, Any],
    plan: ParsePlan,
    requested: PlannedPart | dict[str, Any],
    parent_part_id: str | None,
    sizing: OutputSizing,
    inventory: Any = None,
) -> dict[str, Any]:
    """The brief for one part or subpart. `requested` is the model's own specification of it."""
    spec = requested.to_mapping() if isinstance(requested, PlannedPart) else dict(requested)
    return {
        "brief": PART,
        "filing": filing,
        **(
            {"mechanical_inventory": mechanical_inventory(inventory)}
            if inventory is not None
            else {}
        ),
        "plan": _plan_summary(plan),
        "requested_part": {
            "part_id": spec.get("part_id"),
            "parent_part_id": parent_part_id,
            "order": spec.get("order"),
            "title": spec.get("title"),
            "type": spec.get("type"),
            "purpose": spec.get("purpose"),
        },
        "sizing": {
            **sizing.to_mapping(),
            "this_call_returns": "one part, complete, as one standalone document",
        },
        "protocol": _protocol_note(),
    }


def replan_brief(
    *,
    filing: dict[str, Any],
    plan: ParsePlan,
    part_id: str,
    part_spec: dict[str, Any],
    truncated_response: str,
    truncated_output_tokens: int,
    truncated_cap: int,
    stop_reason: str,
    sizing: OutputSizing,
) -> dict[str, Any]:
    """The brief for a replanning call after a part attempt hit the output limit.

    THE TRUNCATED TEXT TRAVELS VERBATIM AND IS LABELLED AS EVIDENCE. It is not a prefix to continue
    and it is not joined to anything. Sending a summary of it instead would ask the model to trust
    a description of its own output written by code that does not know what the output means.
    """
    return {
        "brief": REPLAN,
        "filing": filing,
        "plan": _plan_summary(plan),
        "truncated_part": {
            "part_id": part_id,
            "order": part_spec.get("order"),
            "title": part_spec.get("title"),
            "type": part_spec.get("type"),
            "purpose": part_spec.get("purpose"),
        },
        "truncated_attempt": {
            "stop_reason": stop_reason,
            "output_tokens": truncated_output_tokens,
            "output_cap": truncated_cap,
            "status": "EVIDENCE ONLY. It is not being continued and nothing will be joined to it.",
            "exact_partial_response": truncated_response,
        },
        "sizing": {
            **sizing.to_mapping(),
            "this_call_returns": "a division of the whole original part into subparts",
            "each_subpart_should_aim_for": sizing.visible_target_tokens,
        },
        "protocol": _protocol_note(),
    }


def part_inventory(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """A COMPACT DETERMINISTIC inventory of what has been produced, derived by counting.

    Nothing in an entry required reading a response for meaning: identifiers and titles are copied
    from what the model returned, and every number is a count. Section 12.1 of the Phase 2.1 brief
    asks for exactly this rather than the full artifacts, so that reconciliation has room to think
    about the whole filing instead of re-reading every part.
    """
    return [
        {
            "part_id": entry.get("part_id"),
            "parent_part_id": entry.get("parent_part_id"),
            "order": entry.get("order"),
            "title": entry.get("title"),
            "type": entry.get("type"),
            "declared_status": entry.get("declared_status"),
            "task_state": entry.get("task_state"),
            "truncated": bool(entry.get("truncated")),
            "node_count": entry.get("node_count") or 0,
            "table_count": entry.get("table_count") or 0,
            "source_references": entry.get("reference_count") or 0,
            "source_references_located_in_the_filing": entry.get("references_resolved") or 0,
            "source_references_not_located": (entry.get("reference_count") or 0)
            - (entry.get("references_resolved") or 0),
            "model_declared_unresolved": entry.get("unresolved_count") or 0,
            "coverage_summary": entry.get("coverage_summary") or "",
        }
        for entry in entries
    ]


def reconcile_brief(
    *,
    filing: dict[str, Any],
    plan: ParsePlan,
    inventory: list[dict[str, Any]],
    source_inventory: Any = None,
    cycle: int,
    cycle_limit: int,
    sizing: OutputSizing,
) -> dict[str, Any]:
    """The brief for one reconciliation cycle."""
    return {
        "brief": RECONCILE,
        "filing": filing,
        "plan": _plan_summary(plan),
        "produced_parts": part_inventory(inventory),
        **(
            {"mechanical_inventory": mechanical_inventory(source_inventory)}
            if source_inventory is not None
            else {}
        ),
        "inventory_note": (
            "counts, not parses. Every number was produced by counting or by searching the filing "
            "for a quote; nothing that produced them read a response for meaning."
        ),
        "cycle": cycle,
        "cycle_limit": cycle_limit,
        "sizing": {
            **sizing.to_mapping(),
            "this_call_returns": "a coverage judgement and a list of work",
        },
        "protocol": _protocol_note(),
    }


def gap_brief(
    *,
    filing: dict[str, Any],
    plan: ParsePlan,
    inventory: list[dict[str, Any]],
    source_inventory: Any = None,
    findings: list[dict[str, Any]],
    cycle: int,
    sizing: OutputSizing,
) -> dict[str, Any]:
    """The brief for a gap-repair call. `findings` are MECHANICAL and name nothing semantic."""
    return {
        "brief": GAP,
        "filing": filing,
        "plan": _plan_summary(plan),
        "produced_parts": part_inventory(inventory),
        "mechanical_findings": findings,
        "findings_note": (
            "produced by counting and searching. Nothing that produced them knows what a filing "
            "contains or what any section means, so a finding is evidence and not an instruction."
        ),
        "cycle": cycle,
        "sizing": {
            **sizing.to_mapping(),
            "this_call_returns": "a judgement about the findings and a list of work",
        },
        "protocol": _protocol_note(),
    }


def repair_brief(*, malformed_response: str, parse_error: str) -> dict[str, Any]:
    """The brief for a format repair. Deliberately carries NO filing and no plan.

    There is nothing to look up, because the call is forbidden to change meaning. Sending the
    filing would offer the model the material to improve an answer with, which is the one thing
    section 17 of the Phase 2.1 brief says a repair must never do.
    """
    return {
        "brief": REPAIR,
        "parse_error": parse_error,
        "instruction": (
            "return the same content as one valid unfenced YAML 1.2 document. Preserve meaning "
            "exactly: no field added, none removed, nothing merged, renamed, tidied, shortened, "
            "corrected or filled in."
        ),
        "malformed_response": malformed_response,
    }


def _protocol_note() -> dict[str, Any]:
    """The three facts a model needs about this protocol on every semantic call.

    Repeated on every call rather than stated once, because every call is independent by design:
    there is no conversation carrying it forward, and a model that inferred it was continuing
    something would produce the half-documents this protocol exists to prevent.
    """
    return {
        "each_call_is_independent": (
            "the complete filing is in front of you again on every call. No previous response is, "
            "and none is expected to be."
        ),
        "responses_are_never_joined": (
            "nothing you return is concatenated with another response. Each must be a whole valid "
            "document by itself."
        ),
        "identifiers_are_yours": (
            "identifiers you choose are stored exactly as you wrote them and are never renamed, "
            "translated or interpreted."
        ),
    }
