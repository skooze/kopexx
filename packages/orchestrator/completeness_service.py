"""Turn a finished parse into a completeness ledger, measured against the preserved bytes.

WHAT THIS BRIDGES. `packages/completeness` knows how to account for an inventory against a parse and
knows nothing about where a parse is stored. `packages/evaluation_store` holds the parse and knows
nothing about coverage. This module reads the one and feeds the other, and it is the only place the
two meet.

ANCHORS ARE RESOLVED AGAINST THE ORIGINAL BYTES, NEVER AGAINST WHAT THE MODEL WAS SHOWN. In
projected mode the model reads a YAML document; its quotes are still checked against the filing SEC
published, through the six-level ladder that strips markup and decodes character references. That is
the entire justification for the projection being lossless and offset-anchored — if a quote from the
projection could not be found in the original, the projection would have changed the filing, and
this is where that claim is tested rather than asserted.

EVERY COUNT COMES FROM THE EFFECTIVE ARTIFACT. A part whose response would not parse and whose
format repair succeeded contributes the repair's claims and the repair's tables. Reading the
malformed original here would report a repaired part as having covered nothing, which is the false
empty commit f70c9f3 closed one level up.

NOTHING HERE JUDGES A PARSE. It counts what was claimed, checks the claims against bytes, and hands
the result to a gate whose strongest verdict means "a person can now review this".
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from packages.completeness import (
    BenchmarkTruth,
    CompletenessLedger,
    ConvergenceState,
    CoverageClaim,
    GateResult,
    HumanReadiness,
    SerializationState,
    TransportState,
    build_ledger,
    evaluate,
    validate_tables,
)
from packages.coverage_validation import ArtifactIndex, ReferenceOutcome
from packages.multipart import read_tables, resolve_effective
from packages.source_inventory import FilingInventory


def _claims_of(document: dict[str, Any], part_id: str) -> list[CoverageClaim]:
    """Read one part's coverage claims. A malformed entry is skipped, never guessed at."""
    found: list[CoverageClaim] = []
    for raw in document.get("coverage_claims") or []:
        if not isinstance(raw, dict):
            continue
        start = str(raw.get("start_anchor") or "").strip()
        end = str(raw.get("end_anchor") or "").strip()
        if not start or not end:
            # A claim with one end is not a bounded region. It is dropped from the interval
            # arithmetic and the part still gets no credit for the region, which is the honest
            # outcome — a half-open claim covers nothing.
            continue
        found.append(
            CoverageClaim(
                member=str(raw.get("member") or ""),
                start_anchor=start,
                end_anchor=end,
                intermediate_anchors=tuple(
                    str(a) for a in (raw.get("intermediate_anchors") or []) if a
                ),
                part_id=part_id,
                purpose=str(raw.get("purpose") or ""),
                unresolved=bool(raw.get("unresolved")),
            )
        )
    return found


def _references_of(
    document: dict[str, Any], index: ArtifactIndex, part_id: str
) -> list[ReferenceOutcome]:
    """Resolve every node's source references, exactly as the single-response path does."""
    outcomes: list[ReferenceOutcome] = []
    for node in document.get("nodes") or []:
        if not isinstance(node, dict):
            continue
        node_id = f"{part_id}/{node.get('id') or ''}"
        for ref in node.get("source") or []:
            if not isinstance(ref, dict):
                continue
            quote = str(ref.get("quote") or "")
            if quote:
                outcomes.append(
                    index.resolve(str(ref.get("filename") or ""), quote, node_id=node_id)
                )
    return outcomes


@dataclass(frozen=True)
class EffectiveDocument:
    """One part, the artifact that currently holds its content, and that artifact's document."""

    task: Any
    source_task: Any
    part_id: str
    document: dict[str, Any]

    @property
    def superseded(self) -> bool:
        """Whether a format repair, rather than the model's own response, supplied this content."""
        return self.task.task_id != self.source_task.task_id


@dataclass(frozen=True)
class EffectiveParse:
    """Every readable part document of one parse, plus what could not be read.

    THE COUNTS TRAVEL WITH THE DOCUMENTS BECAUSE THEY ARE THE SAME WALK. A caller that re-derived
    "how many parts were unreadable" or "how many needed a repair" from a second pass over the
    tasks would be free to disagree with the ledger about the parse the ledger measured, and that
    disagreement is invisible: both numbers look plausible.
    """

    documents: tuple[EffectiveDocument, ...]
    part_tasks: int
    unparseable: int
    repaired: int


def effective_parse(
    *,
    tasks: list[Any],
    documents: dict[str, dict[str, Any]],
    part_types: frozenset[Any],
    repair_type: Any,
    succeeded_state: Any,
) -> EffectiveParse:
    """Resolve every part task to the document that currently holds its content.

    A part with no readable artifact is not silently skipped: it contributes nothing to coverage,
    which is exactly what it did, and it is counted so the gate can see it.
    """
    effective = resolve_effective(
        list(tasks),
        part_types=part_types,
        repair_type=repair_type,
        succeeded_state=succeeded_state,
    )
    found: list[EffectiveDocument] = []
    part_tasks = unparseable = repaired = 0
    for task in tasks:
        if task.task_type not in part_types:
            continue
        part_tasks += 1
        source = effective.effective(task)
        document = documents.get(source.task_id)
        if document is None:
            if source.state is succeeded_state:
                unparseable += 1
            continue
        entry = EffectiveDocument(
            task=task,
            source_task=source,
            part_id=str(document.get("part_id") or task.part_id or source.task_id),
            document=document,
        )
        repaired += 1 if entry.superseded else 0
        found.append(entry)
    return EffectiveParse(
        documents=tuple(found),
        part_tasks=part_tasks,
        unparseable=unparseable,
        repaired=repaired,
    )


def measure(
    *,
    tasks: list[Any],
    documents: dict[str, dict[str, Any]],
    inventory: FilingInventory,
    truth: BenchmarkTruth,
    artifact_texts: dict[str, str],
    part_types: frozenset[Any],
    repair_type: Any,
    succeeded_state: Any,
    model_accepts_images: bool,
    images_submitted: frozenset[str],
    transport: TransportState,
    serialization: SerializationState,
    convergence: ConvergenceState,
    human_readiness: HumanReadiness = HumanReadiness.READY_FOR_REVIEW,
    nonterminal_required_jobs: int = 0,
    truncations_without_replacement: int = 0,
    reconciliation_created_new_work: bool = False,
    repeated_gap_fingerprints: int = 0,
    unsettled_reservations: int = 0,
    held_billing_unknown: int = 0,
    index: ArtifactIndex | None = None,
) -> tuple[CompletenessLedger, GateResult, tuple[Any, ...]]:
    """Measure one parse. Returns the ledger, the gate verdict and the table validations.

    `documents` maps a task id to the parsed response it holds. The caller reads them because it
    owns the evidence store; this module owns what they mean for coverage.

    `index` MAY BE SUPPLIED BY A CALLER MEASURING SEVERAL PARSES OF ONE FILING, and it is the same
    bytes for every one of them. Preparing the six-level anchor ladder over a 900,000-character
    filing costs seconds; doing it once per model rather than once per parse is the difference
    between a comparison page that opens and one nobody waits for. It changes no result: the index
    is a prepared search structure over the preserved artifacts and holds nothing about a parse.
    """
    parse = effective_parse(
        tasks=tasks,
        documents=documents,
        part_types=part_types,
        repair_type=repair_type,
        succeeded_state=succeeded_state,
    )
    resolved_index = ArtifactIndex(artifact_texts) if index is None else index

    claims: list[CoverageClaim] = []
    outcomes: list[ReferenceOutcome] = []
    tables: list[Any] = []
    unresolved_spans: set[str] = set()
    unresolved_tables: set[str] = set()
    image_references: set[str] = set()

    for entry in parse.documents:
        document = entry.document
        claims.extend(_claims_of(document, entry.part_id))
        outcomes.extend(_references_of(document, resolved_index, entry.part_id))
        tables.extend(read_tables(document.get("tables")))
        for item in document.get("unresolved") or []:
            if not isinstance(item, dict):
                continue
            where = str(item.get("where") or item.get("span_id") or "")
            if where.startswith(tuple(m.member for m in inventory.members)):
                unresolved_spans.add(where)
            table_id = str(item.get("table_id") or "")
            if table_id:
                unresolved_tables.add(table_id)
        for ref in document.get("image_references") or []:
            if isinstance(ref, dict) and ref.get("filename"):
                image_references.add(str(ref["filename"]))

    validations = validate_tables(
        tuple(tables), inventory=inventory, submitted_members=frozenset(artifact_texts)
    )
    failing = sum(1 for v in validations if not v.passes and v.cells_unresolved == 0)

    ledger = build_ledger(
        inventory=inventory,
        truth=truth,
        index=resolved_index,
        claims=tuple(claims),
        reference_outcomes=tuple(outcomes),
        structured_tables=tuple(tables),
        declared_unresolved_spans=frozenset(unresolved_spans),
        declared_unresolved_tables=frozenset(unresolved_tables),
        images_submitted=images_submitted,
        image_references=frozenset(image_references),
        model_accepts_images=model_accepts_images,
    )
    gate = evaluate(
        ledger,
        transport=transport,
        serialization=serialization,
        convergence=convergence,
        human_readiness=human_readiness,
        unparseable_effective_artifacts=parse.unparseable,
        nonterminal_required_jobs=nonterminal_required_jobs,
        truncations_without_replacement=truncations_without_replacement,
        reconciliation_created_new_work=reconciliation_created_new_work,
        repeated_gap_fingerprints=repeated_gap_fingerprints,
        unsettled_reservations=unsettled_reservations,
        held_billing_unknown=held_billing_unknown,
        structured_tables_failing_validation=failing,
    )
    return ledger, gate, validations
