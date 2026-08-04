"""Reading the multipart envelopes. GENERIC, ELASTIC, and structurally minimal on purpose.

WHAT THIS MODULE IS ALLOWED TO REQUIRE. That a response is one YAML 1.2 mapping; that it names the
plan it belongs to; that a part names itself; that identifiers are unique and safe; that declared
dependencies resolve. Structure, scheduling and provenance — nothing else.

WHAT IT IS FORBIDDEN TO REQUIRE, AND WHY IT WOULD BE EASY TO. Not a vocabulary of part types. Not a
required hierarchy. Not a minimum number of parts. Not a fixed set of node types, table shapes,
relationship names or reasons for leaving something unresolved. rules.md section 21 rule 2 forbids
a universal filing taxonomy without explicit user approval, and a "required" field list is exactly
how one arrives: first it is a validation convenience, then it is what every model is prompted
toward, then it is what the product believes a filing is.

    The single-response envelope this extends went through the same discipline and is still
    labelled PROVISIONAL after thirty real invocations. The multipart envelope is one day old.

EVERY UNKNOWN KEY SURVIVES. `extra` on every record carries whatever the model returned that this
module does not name. That is not politeness: the whole point of running five candidates through a
new protocol is to find out what they actually emit, and a reader that dropped the surprising half
would guarantee the surprise was never seen.

THE EXACT RESPONSE REMAINS AUTHORITATIVE. These records are a convenience view for scheduling and
for the review UI. The bytes the model returned are preserved separately and are what a reviewer is
shown whenever the two could disagree.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Final

from packages.llm_gateway import parse_yaml

from .errors import EnvelopeUnreadableError
from .identity import require_part_identifier, storage_token

#: The provisional minimum envelope of a PART response. Its ABSENCE is a finding, never a refusal.
#: Named separately from the single-response envelope in `packages/coverage_validation` because a
#: part is not a whole filing and must not be asked to look like one.
PART_ENVELOPE_KEYS: Final[tuple[str, ...]] = (
    "parse_plan_id",
    "part_id",
    "status",
    "nodes",
    "unresolved",
)

#: The provisional minimum envelope of a PLAN response.
PLAN_ENVELOPE_KEYS: Final[tuple[str, ...]] = ("parse_plan_id", "parts")

_KNOWN_PLAN_KEYS = frozenset({"parse_plan_id", "parts", "unassigned", "uncertainty", "metadata"})
_KNOWN_PLANNED_PART_KEYS = frozenset(
    {
        "part_id",
        "order",
        "title",
        "type",
        "purpose",
        "depends_on",
        "may_require_subparts",
        "image_dependency",
        "expected_sources",
        "expected_output_tokens",
    }
)
_KNOWN_PART_KEYS = frozenset(
    {
        "parse_plan_id",
        "part_id",
        "parent_part_id",
        "status",
        "title",
        "type",
        "nodes",
        "tables",
        "source_references",
        "image_references",
        "unresolved",
        "coverage_summary",
        "subparts_required",
        "proposed_subparts",
        "metadata",
    }
)


class PartStatus(StrEnum):
    """What the MODEL said about its own part. A workflow status, never a filing taxonomy.

    UNRECOGNISED is not an error state. A model that invents a sixth word has told us something
    real about the protocol, and the exact string it used is kept beside this value. Refusing the
    response would destroy the measurement; treating the word as `complete` would invent one.
    """

    COMPLETE = "complete"
    NEEDS_SUBPARTS = "needs_subparts"
    SOURCE_AMBIGUITY = "source_ambiguity"
    IMAGE_DEPENDENCY_UNAVAILABLE = "image_dependency_unavailable"
    UNABLE_TO_COMPLETE = "unable_to_complete"
    UNRECOGNISED = "unrecognised"


#: Statuses under which a part's content is treated as a finished contribution to the assembly.
#: Everything else contributes EVIDENCE and leaves work behind for reconciliation.
SETTLED_PART_STATUSES: Final[frozenset[PartStatus]] = frozenset({PartStatus.COMPLETE})


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _listing(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _mappings(value: Any) -> tuple[dict[str, Any], ...]:
    return tuple(item for item in _listing(value) if isinstance(item, dict))


def _strings(value: Any) -> tuple[str, ...]:
    return tuple(str(item) for item in _listing(value) if item is not None)


def _int_or_none(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _document(text: str, *, what: str) -> dict[str, Any]:
    try:
        parsed = parse_yaml(text)
    except Exception as error:
        raise EnvelopeUnreadableError(
            f"the {what} is not one YAML 1.2 document: {error}"
        ) from error
    if not isinstance(parsed, dict):
        raise EnvelopeUnreadableError(
            f"the {what} parsed to {type(parsed).__name__} rather than a mapping"
        )
    return parsed


@dataclass(frozen=True)
class PlannedPart:
    """One part the MODEL decided this filing has, as it described it.

    `title` and `type_label` are the model's words. They are displayed, ordered and echoed back in
    the request for that part, and they are never checked against anything.
    """

    part_id: str
    storage_token: str
    order: int
    title: str
    type_label: str
    purpose: str
    depends_on: tuple[str, ...]
    may_require_subparts: bool
    image_dependency: bool
    expected_sources: tuple[str, ...]
    expected_output_tokens: int | None
    extra: dict[str, Any] = field(default_factory=dict)

    def to_mapping(self) -> dict[str, Any]:
        return {
            "part_id": self.part_id,
            "storage_token": self.storage_token,
            "order": self.order,
            "title": self.title,
            "type": self.type_label,
            "purpose": self.purpose,
            "depends_on": list(self.depends_on),
            "may_require_subparts": self.may_require_subparts,
            "image_dependency": self.image_dependency,
            "expected_sources": list(self.expected_sources),
            "expected_output_tokens": self.expected_output_tokens,
            "model_supplied_extra": self.extra,
        }


@dataclass(frozen=True)
class ParsePlan:
    """The model's decomposition of one filing into parts it will produce separately."""

    plan_id: str
    parts: tuple[PlannedPart, ...]
    unassigned: tuple[dict[str, Any], ...]
    uncertainty: tuple[dict[str, Any], ...]
    metadata: dict[str, Any]
    missing_envelope_keys: tuple[str, ...]
    extra: dict[str, Any]
    raw: dict[str, Any]

    @property
    def part_ids(self) -> tuple[str, ...]:
        return tuple(p.part_id for p in self.parts)

    def part(self, part_id: str) -> PlannedPart | None:
        for candidate in self.parts:
            if candidate.part_id == part_id:
                return candidate
        return None

    def ordered(self) -> tuple[PlannedPart, ...]:
        """Parts in the MODEL's declared order, ties broken by the order they were returned in."""
        return tuple(sorted(self.parts, key=lambda p: (p.order, self.parts.index(p))))

    def to_mapping(self) -> dict[str, Any]:
        return {
            "parse_plan_id": self.plan_id,
            "part_count": len(self.parts),
            "parts": [p.to_mapping() for p in self.ordered()],
            "unassigned": list(self.unassigned),
            "uncertainty": list(self.uncertainty),
            "metadata": self.metadata,
            "missing_envelope_keys": list(self.missing_envelope_keys),
            "model_supplied_extra": self.extra,
        }


@dataclass(frozen=True)
class ProposedPart:
    """A part the model proposed mid-flight: a subpart, a gap part, or a replacement."""

    part_id: str
    storage_token: str
    order: int
    title: str
    type_label: str
    purpose: str
    extra: dict[str, Any] = field(default_factory=dict)

    def to_mapping(self) -> dict[str, Any]:
        return {
            "part_id": self.part_id,
            "storage_token": self.storage_token,
            "order": self.order,
            "title": self.title,
            "type": self.type_label,
            "purpose": self.purpose,
            "model_supplied_extra": self.extra,
        }


@dataclass(frozen=True)
class PartArtifact:
    """One part response, read for scheduling and provenance only.

    `nodes` are DELIBERATELY not re-read here. `packages/coverage_validation` is the single home for
    reading a parsed artifact and resolving its citations against the preserved bytes, and a second
    reader would be a second thing to keep honest. This record carries the node list untouched, so
    the assembly can present it, and the count so the hierarchy can show it.
    """

    plan_id: str
    part_id: str
    parent_part_id: str | None
    status: PartStatus
    declared_status: str
    title: str
    type_label: str
    nodes: tuple[dict[str, Any], ...]
    tables: tuple[dict[str, Any], ...]
    source_references: tuple[dict[str, Any], ...]
    image_references: tuple[dict[str, Any], ...]
    unresolved: tuple[dict[str, Any], ...]
    coverage_summary: str
    subparts_required: bool
    proposed_subparts: tuple[ProposedPart, ...]
    metadata: dict[str, Any]
    missing_envelope_keys: tuple[str, ...]
    extra: dict[str, Any]
    raw: dict[str, Any]

    @property
    def node_count(self) -> int:
        return len(self.nodes)

    def to_mapping(self) -> dict[str, Any]:
        return {
            "parse_plan_id": self.plan_id,
            "part_id": self.part_id,
            "parent_part_id": self.parent_part_id,
            "status": self.status.value,
            "declared_status": self.declared_status,
            "title": self.title,
            "type": self.type_label,
            "node_count": self.node_count,
            "table_count": len(self.tables),
            "unresolved_count": len(self.unresolved),
            "image_reference_count": len(self.image_references),
            "coverage_summary": self.coverage_summary,
            "subparts_required": self.subparts_required,
            "proposed_subparts": [s.to_mapping() for s in self.proposed_subparts],
            "metadata": self.metadata,
            "missing_envelope_keys": list(self.missing_envelope_keys),
            "model_supplied_extra": self.extra,
        }


@dataclass(frozen=True)
class PlanAmendment:
    """What reconciliation or gap repair asked for. One shape, because both amend the same plan.

    `plan_complete` and `model_declared_coverage` are the MODEL's claim about its own work. They
    are recorded and displayed as a claim. Nothing in this repository converts either into an
    objective completeness verdict — rules.md section 21 rule 5, and section 12.2 of the brief.
    """

    plan_id: str
    cycle: int
    plan_complete: bool
    missing: tuple[dict[str, Any], ...]
    duplicated: tuple[dict[str, Any], ...]
    conflicting: tuple[dict[str, Any], ...]
    additional_parts: tuple[ProposedPart, ...]
    replacement_parts: tuple[ProposedPart, ...]
    unresolvable: tuple[dict[str, Any], ...]
    model_declared_coverage: str
    metadata: dict[str, Any]
    extra: dict[str, Any]
    raw: dict[str, Any]

    @property
    def creates_work(self) -> bool:
        return bool(self.additional_parts or self.replacement_parts)

    def to_mapping(self) -> dict[str, Any]:
        return {
            "parse_plan_id": self.plan_id,
            "cycle": self.cycle,
            "model_declared_plan_complete": self.plan_complete,
            "missing": list(self.missing),
            "duplicated": list(self.duplicated),
            "conflicting": list(self.conflicting),
            "additional_parts": [p.to_mapping() for p in self.additional_parts],
            "replacement_parts": [p.to_mapping() for p in self.replacement_parts],
            "unresolvable": list(self.unresolvable),
            "model_declared_coverage": self.model_declared_coverage,
            "creates_work": self.creates_work,
            "metadata": self.metadata,
            "model_supplied_extra": self.extra,
            "claim_note": (
                "every field above is the MODEL's account of its own work. The backend records it "
                "and proves coverage separately, against the preserved bytes."
            ),
        }


@dataclass(frozen=True)
class ReplanOutcome:
    """The model's own reading of a truncated attempt, and how it proposes to finish the part.

    `covered_before_truncation` IS NOT TRUSTED. Section 10.1 of the brief says so plainly, and this
    package does not check it: the source references the truncated attempt produced are resolved
    against the preserved bytes by `packages/coverage_validation`, exactly as any other reference.
    """

    plan_id: str
    part_id: str
    covered_before_truncation: tuple[dict[str, Any], ...]
    remaining: tuple[dict[str, Any], ...]
    proposed_subparts: tuple[ProposedPart, ...]
    overlap_risk: str
    uncertainty: tuple[dict[str, Any], ...]
    metadata: dict[str, Any]
    extra: dict[str, Any]
    raw: dict[str, Any]

    def to_mapping(self) -> dict[str, Any]:
        return {
            "parse_plan_id": self.plan_id,
            "part_id": self.part_id,
            "covered_before_truncation": list(self.covered_before_truncation),
            "remaining": list(self.remaining),
            "proposed_subparts": [p.to_mapping() for p in self.proposed_subparts],
            "overlap_risk": self.overlap_risk,
            "uncertainty": list(self.uncertainty),
            "metadata": self.metadata,
            "model_supplied_extra": self.extra,
            "coverage_claim_note": (
                "covered_before_truncation is the model's claim about a response that ran out of "
                "room. It is displayed and never believed; only references resolved against the "
                "preserved bytes count as coverage."
            ),
        }


# --- readers -------------------------------------------------------------------------------------


def _proposed(raw: Any, fallback_order: int) -> ProposedPart | None:
    mapping = _mapping(raw)
    identifier = str(mapping.get("part_id") or "").strip()
    if not identifier:
        return None
    require_part_identifier(identifier)
    order = _int_or_none(mapping.get("order"))
    return ProposedPart(
        part_id=identifier,
        storage_token=storage_token(identifier),
        order=fallback_order if order is None else order,
        title=str(mapping.get("title") or ""),
        type_label=str(mapping.get("type") or ""),
        purpose=str(mapping.get("purpose") or ""),
        extra={k: v for k, v in mapping.items() if k not in _KNOWN_PLANNED_PART_KEYS},
    )


def _proposed_list(value: Any) -> tuple[ProposedPart, ...]:
    found = []
    for index, raw in enumerate(_listing(value)):
        proposed = _proposed(raw, index)
        if proposed is not None:
            found.append(proposed)
    return tuple(found)


def read_plan(text: str) -> ParsePlan:
    """Read one planning response. Raises only when it is not one YAML mapping at all."""
    document = _document(text, what="planning response")
    parts: list[PlannedPart] = []
    for index, raw in enumerate(_listing(document.get("parts"))):
        mapping = _mapping(raw)
        identifier = str(mapping.get("part_id") or "").strip()
        if not identifier:
            # A part with no identifier cannot be scheduled, cited or rerun. It is DROPPED from the
            # schedulable plan and REPORTED by `validate_plan`, which reads the raw list — rather
            # than raising here, which would throw away a plan whose other nine parts are fine.
            continue
        require_part_identifier(identifier)
        order = _int_or_none(mapping.get("order"))
        parts.append(
            PlannedPart(
                part_id=identifier,
                storage_token=storage_token(identifier),
                order=index if order is None else order,
                title=str(mapping.get("title") or ""),
                type_label=str(mapping.get("type") or ""),
                purpose=str(mapping.get("purpose") or ""),
                depends_on=_strings(mapping.get("depends_on")),
                may_require_subparts=bool(mapping.get("may_require_subparts")),
                image_dependency=bool(mapping.get("image_dependency")),
                expected_sources=_strings(mapping.get("expected_sources")),
                expected_output_tokens=_int_or_none(mapping.get("expected_output_tokens")),
                extra={k: v for k, v in mapping.items() if k not in _KNOWN_PLANNED_PART_KEYS},
            )
        )
    return ParsePlan(
        plan_id=str(document.get("parse_plan_id") or ""),
        parts=tuple(parts),
        unassigned=_mappings(document.get("unassigned")),
        uncertainty=_mappings(document.get("uncertainty")),
        metadata=_mapping(document.get("metadata")),
        missing_envelope_keys=tuple(k for k in PLAN_ENVELOPE_KEYS if k not in document),
        extra={k: v for k, v in document.items() if k not in _KNOWN_PLAN_KEYS},
        raw=document,
    )


def read_part(text: str) -> PartArtifact:
    """Read one part response. Raises only when it is not one YAML mapping at all."""
    document = _document(text, what="part response")
    declared = str(document.get("status") or "").strip()
    try:
        status = PartStatus(declared.lower())
    except ValueError:
        status = PartStatus.UNRECOGNISED
    proposed = _proposed_list(document.get("proposed_subparts"))
    parent = document.get("parent_part_id")
    return PartArtifact(
        plan_id=str(document.get("parse_plan_id") or ""),
        part_id=str(document.get("part_id") or ""),
        parent_part_id=str(parent) if parent not in (None, "") else None,
        status=status,
        declared_status=declared,
        title=str(document.get("title") or ""),
        type_label=str(document.get("type") or ""),
        nodes=_mappings(document.get("nodes")),
        tables=_mappings(document.get("tables")),
        source_references=_mappings(document.get("source_references")),
        image_references=_mappings(document.get("image_references")),
        unresolved=_mappings(document.get("unresolved")),
        coverage_summary=str(document.get("coverage_summary") or ""),
        # A model that proposed subparts and forgot the boolean has still proposed subparts.
        subparts_required=bool(document.get("subparts_required")) or bool(proposed),
        proposed_subparts=proposed,
        metadata=_mapping(document.get("metadata")),
        missing_envelope_keys=tuple(k for k in PART_ENVELOPE_KEYS if k not in document),
        extra={k: v for k, v in document.items() if k not in _KNOWN_PART_KEYS},
        raw=document,
    )


def read_amendment(text: str, *, cycle: int) -> PlanAmendment:
    """Read one reconciliation or gap-repair response."""
    document = _document(text, what="reconciliation response")
    known = {
        "parse_plan_id",
        "cycle",
        "plan_complete",
        "missing",
        "duplicated",
        "conflicting",
        "additional_parts",
        "replacement_parts",
        "unresolvable",
        "model_declared_coverage",
        "metadata",
    }
    declared_cycle = _int_or_none(document.get("cycle"))
    return PlanAmendment(
        plan_id=str(document.get("parse_plan_id") or ""),
        cycle=cycle if declared_cycle is None else declared_cycle,
        plan_complete=bool(document.get("plan_complete")),
        missing=_mappings(document.get("missing")),
        duplicated=_mappings(document.get("duplicated")),
        conflicting=_mappings(document.get("conflicting")),
        additional_parts=_proposed_list(document.get("additional_parts")),
        replacement_parts=_proposed_list(document.get("replacement_parts")),
        unresolvable=_mappings(document.get("unresolvable")),
        model_declared_coverage=str(document.get("model_declared_coverage") or ""),
        metadata=_mapping(document.get("metadata")),
        extra={k: v for k, v in document.items() if k not in known},
        raw=document,
    )


def read_replan(text: str) -> ReplanOutcome:
    """Read one replanning response produced after a truncated part attempt."""
    document = _document(text, what="replanning response")
    known = {
        "parse_plan_id",
        "part_id",
        "covered_before_truncation",
        "remaining",
        "proposed_subparts",
        "overlap_risk",
        "uncertainty",
        "metadata",
    }
    return ReplanOutcome(
        plan_id=str(document.get("parse_plan_id") or ""),
        part_id=str(document.get("part_id") or ""),
        covered_before_truncation=_mappings(document.get("covered_before_truncation")),
        remaining=_mappings(document.get("remaining")),
        proposed_subparts=_proposed_list(document.get("proposed_subparts")),
        overlap_risk=str(document.get("overlap_risk") or ""),
        uncertainty=_mappings(document.get("uncertainty")),
        metadata=_mapping(document.get("metadata")),
        extra={k: v for k, v in document.items() if k not in known},
        raw=document,
    )
