"""Validate one parsed artifact against the preserved bytes. Evidence, never interpretation.

WHAT VALIDATION IS FOR. rules.md invariant 13: model output is never accepted on trust; it is
accepted on validation. The selected parsing model decides what a filing means. The backend proves,
against the bytes SEC published, that the citations resolve, that the reported numbers occur, that
every submitted artifact is represented, and that nothing was quietly left out.

WHAT VALIDATION IS NOT FOR. It never grades the parse against a second parse. rules.md section 21
rule 15 withdrew the deterministic Apple oracle for exactly that reason: grading a model against a
deterministic interpretation makes the deterministic interpretation authoritative again through the
back door. Everything here compares the response to the SOURCE.

    IT CANNOT PROVE COMPLETE CONTENT AND IT SAYS SO. The complete-content invariant asks whether
    every human-readable source RANGE is represented. What this module can measure today is
    whether every submitted ARTIFACT is cited, how many references resolve, and what the model
    itself declared unresolved. Those are coverage SIGNALS. `status` is therefore never COMPLETE:
    the strongest verdict it issues is REVIEW_REQUIRED, and rounding a set of signals up to a
    completeness claim is precisely the false complete the invariant forbids.

A FAILURE HERE IS A RESULT, NOT AN EXCEPTION. A response that will not parse still produces a
validation record, still reaches the review UI, and still shows its exact bytes. It was bought and
it cannot be regenerated for free.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from packages.llm_gateway import ContentFormat, validate

from . import numbers as numeric
from .errors import ResponseUnreadableError
from .reader import ParsedDocument, read
from .references import ArtifactIndex, ReferenceOutcome, Resolution


class ValidationStatus(StrEnum):
    """The verdict on one parsed artifact.

    COMPLETE IS DELIBERATELY ABSENT. Nothing this module measures can establish it, and a status
    value that exists is a status value something will eventually set.
    """

    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    PARTIAL = "PARTIAL"
    UNPARSEABLE = "UNPARSEABLE"
    EMPTY = "EMPTY"


@dataclass(frozen=True)
class ValidationResult:
    """Every signal, plus the findings a reviewer should see first."""

    status: ValidationStatus
    findings: tuple[str, ...]
    response_characters: int
    yaml_parsed: bool
    boundary_ok: bool
    boundary_violations: tuple[str, ...]
    missing_envelope_keys: tuple[str, ...]
    node_count: int
    table_count: int
    reference_count: int
    references_resolved: int
    references_ambiguous: int
    references_unresolved: int
    resolution_breakdown: dict[str, int]
    artifacts_submitted: int
    artifacts_referenced: int
    artifacts_unreferenced: tuple[str, ...]
    declared_unresolved: int
    image_dependent_nodes: int
    types_used: dict[str, int]
    numeric: dict[str, Any]
    source_characters: int
    outcomes: tuple[ReferenceOutcome, ...] = ()

    @property
    def source_to_response_ratio(self) -> float:
        return (
            self.source_characters / self.response_characters if self.response_characters else 0.0
        )

    def to_mapping(self) -> dict[str, Any]:
        return {
            "schema_version": "validation-v1",
            "status": self.status.value,
            "status_note": (
                "COMPLETE is not a value this validator can issue. It measures coverage SIGNALS "
                "against the preserved bytes; proving that every human-readable source range is "
                "represented is not something these signals establish."
            ),
            "findings": list(self.findings),
            "response_characters": self.response_characters,
            "source_characters": self.source_characters,
            "source_to_response_ratio": round(self.source_to_response_ratio, 2),
            "yaml_parsed": self.yaml_parsed,
            "boundary_ok": self.boundary_ok,
            "boundary_violations": list(self.boundary_violations),
            "missing_envelope_keys": list(self.missing_envelope_keys),
            "node_count": self.node_count,
            "table_count": self.table_count,
            "reference_count": self.reference_count,
            "references_resolved": self.references_resolved,
            "references_ambiguous": self.references_ambiguous,
            "references_unresolved": self.references_unresolved,
            "resolution_breakdown": self.resolution_breakdown,
            "artifacts_submitted": self.artifacts_submitted,
            "artifacts_referenced": self.artifacts_referenced,
            "artifacts_unreferenced": list(self.artifacts_unreferenced),
            "declared_unresolved": self.declared_unresolved,
            "image_dependent_nodes": self.image_dependent_nodes,
            "model_selected_types": self.types_used,
            "numeric": self.numeric,
            "references": [o.to_mapping() for o in self.outcomes],
        }


def validate_response(
    response_text: str,
    *,
    artifact_texts: dict[str, str],
    image_filenames: tuple[str, ...] = (),
    images_analysed: bool = False,
) -> tuple[ValidationResult, ParsedDocument | None]:
    """Validate one exact model response against the artifacts that were sent.

    `artifact_texts` is the DECODED text of each submitted artifact, keyed by the label the model
    was shown. Images have no text and are counted separately: an image is either analysed by a
    multimodal parser or reported unanalysed, and neither case is a citation target.
    """
    findings: list[str] = []
    boundary = validate(response_text, ContentFormat.YAML)
    boundary_violations = tuple(v.value for v in boundary.violations)
    if not boundary.ok:
        findings.append(
            "the response is not one unfenced YAML 1.2 document: " + ", ".join(boundary_violations)
        )

    if not response_text.strip():
        return (
            ValidationResult(
                status=ValidationStatus.EMPTY,
                findings=("the model returned no visible text at all",),
                response_characters=0,
                yaml_parsed=False,
                boundary_ok=boundary.ok,
                boundary_violations=boundary_violations,
                missing_envelope_keys=(),
                node_count=0,
                table_count=0,
                reference_count=0,
                references_resolved=0,
                references_ambiguous=0,
                references_unresolved=0,
                resolution_breakdown={},
                artifacts_submitted=len(artifact_texts) + len(image_filenames),
                artifacts_referenced=0,
                artifacts_unreferenced=tuple(artifact_texts) + image_filenames,
                declared_unresolved=0,
                image_dependent_nodes=0,
                types_used={},
                numeric=numeric.NumericSignals(0, 0, 0, 0, 0, 0).to_mapping(),
                source_characters=sum(len(t) for t in artifact_texts.values()),
            ),
            None,
        )

    try:
        document = read(response_text)
    except ResponseUnreadableError as error:
        findings.append(str(error))
        return (
            ValidationResult(
                status=ValidationStatus.UNPARSEABLE,
                findings=tuple(findings),
                response_characters=len(response_text),
                yaml_parsed=False,
                boundary_ok=boundary.ok,
                boundary_violations=boundary_violations,
                missing_envelope_keys=(),
                node_count=0,
                table_count=0,
                reference_count=0,
                references_resolved=0,
                references_ambiguous=0,
                references_unresolved=0,
                resolution_breakdown={},
                artifacts_submitted=len(artifact_texts) + len(image_filenames),
                artifacts_referenced=0,
                artifacts_unreferenced=tuple(artifact_texts) + image_filenames,
                declared_unresolved=0,
                image_dependent_nodes=0,
                types_used={},
                numeric=numeric.NumericSignals(0, 0, 0, 0, 0, 0).to_mapping(),
                source_characters=sum(len(t) for t in artifact_texts.values()),
            ),
            None,
        )

    if document.missing_envelope_keys:
        findings.append(
            "the provisional envelope is missing: " + ", ".join(document.missing_envelope_keys)
        )
    if not document.nodes:
        findings.append("the response carries no nodes, so it represents no filing content")

    index = ArtifactIndex(artifact_texts)
    outcomes: list[ReferenceOutcome] = []
    for node in document.nodes:
        for reference in node.references:
            outcomes.append(
                index.resolve(reference.filename, reference.quote, node_id=node.node_id)
            )

    breakdown: dict[str, int] = {}
    for outcome in outcomes:
        breakdown[outcome.resolution.value] = breakdown.get(outcome.resolution.value, 0) + 1
    resolved = sum(1 for o in outcomes if o.resolved)
    ambiguous = breakdown.get(Resolution.AMBIGUOUS.value, 0)
    unresolved_refs = len(outcomes) - resolved - ambiguous

    referenced = {o.filename for o in outcomes if o.resolved}
    unreferenced = tuple(name for name in artifact_texts if name not in referenced)
    if unreferenced:
        findings.append(
            f"{len(unreferenced)} submitted artifact(s) carry no resolved reference: "
            + ", ".join(unreferenced)
        )
    if image_filenames and not images_analysed:
        findings.append(
            f"{len(image_filenames)} image-bearing member(s) were NOT analysed; this run does not "
            "claim image coverage"
        )
    if document.unresolved:
        findings.append(f"the model declared {len(document.unresolved)} unresolved item(s)")
    if unresolved_refs:
        findings.append(
            f"{unresolved_refs} source reference(s) could not be located in the preserved bytes"
        )

    reported_text = "\n".join(f"{node.title}\n{node.content}" for node in document.nodes)
    signals = numeric.assess(
        reported_text=reported_text,
        tables=[table for node in document.nodes for table in node.tables],
        source_text="\n".join(artifact_texts.values()),
    )

    # PARTIAL when the model itself declared something unresolved or a reference did not land.
    # REVIEW_REQUIRED otherwise — never COMPLETE, because nothing measured here establishes it.
    status = (
        ValidationStatus.PARTIAL
        if (
            document.unresolved
            or unresolved_refs
            or unreferenced
            or image_filenames
            and not images_analysed
        )
        else ValidationStatus.REVIEW_REQUIRED
    )

    return (
        ValidationResult(
            status=status,
            findings=tuple(findings),
            response_characters=len(response_text),
            yaml_parsed=True,
            boundary_ok=boundary.ok,
            boundary_violations=boundary_violations,
            missing_envelope_keys=document.missing_envelope_keys,
            node_count=document.node_count,
            table_count=document.table_count,
            reference_count=len(outcomes),
            references_resolved=resolved,
            references_ambiguous=ambiguous,
            references_unresolved=unresolved_refs,
            resolution_breakdown=breakdown,
            artifacts_submitted=len(artifact_texts) + len(image_filenames),
            artifacts_referenced=len(referenced),
            artifacts_unreferenced=unreferenced,
            declared_unresolved=len(document.unresolved),
            image_dependent_nodes=document.image_dependent_count,
            types_used=document.types_used(),
            numeric=signals.to_mapping(),
            source_characters=sum(len(t) for t in artifact_texts.values()),
            outcomes=tuple(outcomes),
        ),
        document,
    )
