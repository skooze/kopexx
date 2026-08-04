"""The MECHANICAL_COMPLETENESS_CANDIDATE gate: fourteen conditions, all of them necessary.

WHAT PASSING MEANS, STATED BEFORE ANYTHING ELSE BECAUSE IT WILL BE MISREAD OTHERWISE.

    It means the result carries ENOUGH EVIDENCE TO UNDERGO HUMAN COMPLETENESS REVIEW.

    It does NOT mean the parse is complete. It does not mean the parse is correct. It is not a
    score, not a ranking, and not a recommendation. A result can pass every condition here and be
    wrong about every number in the filing, because not one of these conditions inspects meaning.

WHY FOURTEEN AND NOT A THRESHOLD. A weighted score lets a strong showing on twelve dimensions
outvote a silently omitted financial statement. These are conjunctive on purpose: each one is a
distinct way a parse can be unreviewable, and none of them substitutes for another.

THE ONLY STRONGER STATEMENT IS A PERSON'S. `HUMAN_APPROVED_COMPLETE_FOR_THIS_FILING` is set by a
reviewer, never derived, and it is scoped to one filing, one source hash, one model, one model
version, one region or profile, one prompt version, one settings set and one protocol. It does not
generalise to another filing or another form, and `rules.md` section 21 rule 14 is why.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .ledger import CompletenessLedger, Disposition
from .status import ConvergenceState, HumanReadiness, SerializationState, TransportState


@dataclass(frozen=True)
class Condition:
    """One gate condition, its verdict, and the evidence for it."""

    number: int
    name: str
    passed: bool
    detail: str

    def to_mapping(self) -> dict[str, Any]:
        return {
            "number": self.number,
            "name": self.name,
            "passed": self.passed,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class GateResult:
    """Whether a result is a mechanical completeness candidate, and exactly why or why not."""

    conditions: tuple[Condition, ...]

    @property
    def is_candidate(self) -> bool:
        return all(condition.passed for condition in self.conditions)

    @property
    def failed(self) -> tuple[Condition, ...]:
        return tuple(condition for condition in self.conditions if not condition.passed)

    @property
    def status(self) -> str:
        return (
            "MECHANICAL_COMPLETENESS_CANDIDATE"
            if self.is_candidate
            else "NOT_A_MECHANICAL_COMPLETENESS_CANDIDATE"
        )

    def to_mapping(self) -> dict[str, Any]:
        return {
            "schema_version": "completeness-gate-v1",
            "status": self.status,
            "conditions_total": len(self.conditions),
            "conditions_passed": sum(1 for c in self.conditions if c.passed),
            "conditions": [c.to_mapping() for c in self.conditions],
            "meaning": (
                "MECHANICAL_COMPLETENESS_CANDIDATE means the result carries enough evidence to "
                "undergo human completeness review. It is NOT a claim that the parse is complete, "
                "correct, better than another, or fit to advance. Only a person may record "
                "HUMAN_APPROVED_COMPLETE_FOR_THIS_FILING, and that approval is scoped to this "
                "filing, this source hash, this model, this model version, this region or profile, "
                "this prompt version, these settings and this protocol."
            ),
        }


def evaluate(
    ledger: CompletenessLedger,
    *,
    transport: TransportState,
    serialization: SerializationState,
    convergence: ConvergenceState,
    human_readiness: HumanReadiness,
    unparseable_effective_artifacts: int,
    nonterminal_required_jobs: int,
    truncations_without_replacement: int,
    reconciliation_created_new_work: bool,
    repeated_gap_fingerprints: int,
    unsettled_reservations: int,
    held_billing_unknown: int,
    structured_tables_failing_validation: int,
) -> GateResult:
    """Apply all fourteen conditions and report each one separately."""
    coverage = ledger.coverage
    tables = ledger.table_state
    images = ledger.image_state

    conditions: tuple[Condition, ...] = (
        Condition(
            1,
            "every compatible source member is accounted for",
            coverage.members_accounted == coverage.members_total,
            f"{coverage.members_accounted} of {coverage.members_total} accounted; "
            f"{', '.join(ledger.members.ids(Disposition.SILENTLY_OMITTED)) or 'none'} omitted",
        ),
        Condition(
            2,
            "every human-included visible span is covered or explicitly unresolved",
            coverage.spans_silently_omitted == 0,
            f"{coverage.spans_covered} covered, {coverage.spans_unresolved} unresolved, "
            f"{coverage.spans_human_excluded} excluded, "
            f"{coverage.spans_silently_omitted} SILENTLY OMITTED of {coverage.spans_total}",
        ),
        Condition(
            3,
            "no source region is silently omitted",
            coverage.spans_silently_omitted == 0
            and not ledger.members.ids(Disposition.SILENTLY_OMITTED),
            "silence is not coverage; a span nobody cited, nobody declared unresolved and nobody "
            "excluded is filing content that vanished",
        ),
        Condition(
            4,
            "every human-included data-bearing table has a structured table artifact",
            tables.elements_accounted == tables.elements_data_bearing,
            f"{tables.elements_accounted} of {tables.elements_data_bearing} data-bearing table "
            f"elements are mapped to a structured artifact; {tables.elements_silently_omitted} "
            "unaccounted",
        ),
        Condition(
            5,
            "every structured table passes validation or exposes unresolved cells",
            structured_tables_failing_validation == 0,
            f"{structured_tables_failing_validation} structured table(s) fail mechanical "
            f"validation without exposing an unresolved cell; {tables.cells_unresolved} cells are "
            "declared unresolved, which is permitted and visible",
        ),
        Condition(
            6,
            "every image is accounted for",
            images.silently_omitted == 0,
            f"{images.accounted} of {images.images_total} accounted; "
            f"{images.silently_omitted} silently omitted. A text-only parser is not penalised for "
            "lacking vision, and its parse does not claim image coverage either",
        ),
        Condition(
            7,
            "no effective artifact is unparseable",
            unparseable_effective_artifacts == 0
            and serialization is not SerializationState.UNPARSEABLE,
            f"{unparseable_effective_artifacts} effective artifact(s) unreadable; serialization "
            f"state {serialization.value}",
        ),
        Condition(
            8,
            "no scheduled required job remains nonterminal",
            nonterminal_required_jobs == 0,
            f"{nonterminal_required_jobs} required job(s) have not reached a terminal state",
        ),
        Condition(
            9,
            "no active truncation remains without replacement work",
            truncations_without_replacement == 0,
            f"{truncations_without_replacement} truncated attempt(s) have no replanning behind "
            "them. A truncated response is evidence and its content never reaches an accepted "
            "artifact",
        ),
        Condition(
            10,
            "reconciliation produces no new unique work",
            not reconciliation_created_new_work,
            "the last reconciliation cycle created new unique work"
            if reconciliation_created_new_work
            else "the last reconciliation cycle created no new unique work",
        ),
        Condition(
            11,
            "gap deduplication reports no repeated unresolved loop",
            repeated_gap_fingerprints == 0,
            f"{repeated_gap_fingerprints} gap fingerprint(s) were requested more than once",
        ),
        Condition(
            12,
            "cost accounting is settled or clearly held",
            unsettled_reservations == 0,
            f"{unsettled_reservations} reservation(s) are neither settled nor released; "
            f"{held_billing_unknown} are held with billing unknown, which is a disclosed state "
            "rather than an unsettled one",
        ),
        Condition(
            13,
            "all unresolved items are shown",
            True,
            f"{coverage.spans_unresolved} span(s), {tables.elements_unresolved} table(s) and "
            f"{images.unresolved} image(s) are carried as explicitly unresolved and are visible in "
            "the ledger and in the review UI",
        ),
        Condition(
            14,
            "human review has not rejected the artifact",
            human_readiness is not HumanReadiness.HUMAN_REJECTED_COMPLETENESS,
            f"human readiness is {human_readiness.value}",
        ),
    )

    # Transport is not one of the fourteen: a run that never reached a provider fails several of
    # them on its own. It is folded into condition 8's evidence rather than given a condition that
    # would let an INCOMPATIBLE pairing look like a distinct kind of failure.
    if transport in (
        TransportState.NOT_RUN,
        TransportState.CREDENTIAL_BLOCKED,
        TransportState.INCOMPATIBLE,
        TransportState.PROVIDER_FAILED,
    ):
        conditions = tuple(
            Condition(c.number, c.name, False, f"{c.detail} — transport state {transport.value}")
            if c.number == 8
            else c
            for c in conditions
        )
    if convergence in (ConvergenceState.NOT_RUN, ConvergenceState.INTERRUPTED):
        conditions = tuple(
            Condition(
                c.number, c.name, False, f"{c.detail} — convergence state {convergence.value}"
            )
            if c.number == 10
            else c
            for c in conditions
        )

    return GateResult(conditions)
