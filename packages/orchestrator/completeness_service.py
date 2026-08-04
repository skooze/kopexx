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
) -> tuple[CompletenessLedger, GateResult, tuple[Any, ...]]:
    """Measure one parse. Returns the ledger, the gate verdict and the table validations.

    `documents` maps a task id to the parsed response it holds. The caller reads them because it
    owns the evidence store; this module owns what they mean for coverage.
    """
    effective = resolve_effective(
        list(tasks),
        part_types=part_types,
        repair_type=repair_type,
        succeeded_state=succeeded_state,
    )
    index = ArtifactIndex(artifact_texts)

    claims: list[CoverageClaim] = []
    outcomes: list[ReferenceOutcome] = []
    tables: list[Any] = []
    unparseable = 0
    unresolved_spans: set[str] = set()
    unresolved_tables: set[str] = set()
    image_references: set[str] = set()

    for task in tasks:
        if task.task_type not in part_types:
            continue
        source = effective.effective(task)
        document = documents.get(source.task_id)
        if document is None:
            # A part with no readable artifact is not silently skipped: it contributes nothing to
            # coverage, which is exactly what it did, and it is counted so the gate can see it.
            if source.state is succeeded_state:
                unparseable += 1
            continue
        part_id = str(document.get("part_id") or task.part_id or source.task_id)
        claims.extend(_claims_of(document, part_id))
        outcomes.extend(_references_of(document, index, part_id))
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
        index=index,
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
        unparseable_effective_artifacts=unparseable,
        nonterminal_required_jobs=nonterminal_required_jobs,
        truncations_without_replacement=truncations_without_replacement,
        reconciliation_created_new_work=reconciliation_created_new_work,
        repeated_gap_fingerprints=repeated_gap_fingerprints,
        unsettled_reservations=unsettled_reservations,
        held_billing_unknown=held_billing_unknown,
        structured_tables_failing_validation=failing,
    )
    return ledger, gate, validations
