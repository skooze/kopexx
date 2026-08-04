"""The completeness ledger: what a model's parse actually accounted for, measured against the bytes.

THE QUESTION THIS ANSWERS, AND THE ONE IT REFUSES TO. It answers: of every human-readable span,
every table element and every image in the preserved filing, which did this parse cover, which did
it explicitly mark unresolved, which did a reviewer exclude, and WHICH DID IT NEVER MENTION AT ALL.
That last count is the whole point, and no reference rate can produce it.

It refuses to answer whether the parse is correct. A covered span is a span whose bounding anchors
resolve in the preserved bytes; the model may still have said something wrong about what is between
them. `rules.md` invariant 13 and section 21 rule 4 place proof in the backend and interpretation in
the model, and this module is entirely on the proof side of that line.

FOUR DISPOSITIONS PER ITEM, AND SILENCE IS NOT ONE OF THEM.

    COVERED             a coverage claim's resolved anchors bound it, or a structured table maps to
                        it, or a model reference resolves inside it
    UNRESOLVED          the model explicitly said it could not resolve this
    HUMAN_EXCLUDED      a reviewer classified it as repeated, navigation, layout, transport markup,
                        decorative or not human-readable, with a reason on the record
    SILENTLY_OMITTED    none of the above. The parse never mentioned it in any form.

`SILENTLY_OMITTED` is what fails the gate. `rules.md` section 3: "no human-readable disclosure may
be silently omitted", and "uncertainty produces PARTIAL or REVIEW_REQUIRED, never a false complete".
An item nobody has reviewed yet is `REQUIRES_REVIEW` in the truth document and counts as neither
covered nor excluded — it blocks the gate rather than being quietly resolved in either direction.

WHY A CLAIM HAS TWO ANCHORS AND NOT AN OFFSET. A model handed an artifact as text cannot count
characters in it. It CAN quote the first sentence of a region and the last one, and both quotes
either occur in the preserved bytes or they do not. Two resolved quotes bound an interval; a
fabricated offset resolves to the wrong place while looking exactly like a real one.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from packages.coverage_validation import ArtifactIndex, ReferenceOutcome
from packages.source_inventory import FilingInventory

from .errors import LedgerInputError
from .intervals import Interval, covered_length, gaps, merge, overlaps
from .status import ImageState, SourceCoverageState, TableState
from .truth import (
    EXCLUDED_IMAGE,
    EXCLUDED_SPAN,
    EXCLUDED_TABLE,
    REQUIRED_SPAN,
    REQUIRED_TABLE,
    BenchmarkTruth,
)


class Disposition(StrEnum):
    """What became of one inventory item in one parse."""

    COVERED = "COVERED"
    UNRESOLVED = "UNRESOLVED"
    HUMAN_EXCLUDED = "HUMAN_EXCLUDED"
    SILENTLY_OMITTED = "SILENTLY_OMITTED"


@dataclass(frozen=True)
class CoverageClaim:
    """One model claim that a stretch of one source member is represented by one part.

    `purpose` is the model's own words for what it did with the region and is never checked.
    `unresolved` is the model saying it could not finish this region — recorded as the model's
    claim, and the reason it produces `UNRESOLVED` rather than `SILENTLY_OMITTED`.
    """

    member: str
    start_anchor: str
    end_anchor: str
    intermediate_anchors: tuple[str, ...]
    part_id: str
    purpose: str
    unresolved: bool

    def to_mapping(self) -> dict[str, Any]:
        return {
            "member": self.member,
            "start_anchor": self.start_anchor[:200],
            "end_anchor": self.end_anchor[:200],
            "intermediate_anchor_count": len(self.intermediate_anchors),
            "part_id": self.part_id,
            "purpose": self.purpose,
            "model_declared_unresolved": self.unresolved,
        }


@dataclass(frozen=True)
class ResolvedClaim:
    """One coverage claim after both its anchors were looked for in the preserved bytes."""

    claim: CoverageClaim
    start: ReferenceOutcome
    end: ReferenceOutcome
    interval: Interval | None
    finding: str = ""

    @property
    def bounded(self) -> bool:
        return self.interval is not None

    def to_mapping(self) -> dict[str, Any]:
        return {
            **self.claim.to_mapping(),
            "start_resolution": self.start.to_mapping(),
            "end_resolution": self.end.to_mapping(),
            "interval": self.interval.to_mapping() if self.interval else None,
            "finding": self.finding,
        }


def resolve_claims(
    claims: tuple[CoverageClaim, ...], index: ArtifactIndex
) -> tuple[ResolvedClaim, ...]:
    """Turn every coverage claim into an interval, or into a finding saying why it is not one."""
    resolved: list[ResolvedClaim] = []
    for position, claim in enumerate(claims):
        node = f"claim-{position}"
        start = index.resolve(claim.member, claim.start_anchor, node_id=node)
        end = index.resolve(claim.member, claim.end_anchor, node_id=node)
        interval: Interval | None = None
        finding = ""
        if not start.resolved and not end.resolved:
            finding = "neither anchor resolves in the preserved bytes"
        elif not start.resolved:
            finding = "the start anchor does not resolve in the preserved bytes"
        elif not end.resolved:
            finding = "the end anchor does not resolve in the preserved bytes"
        elif start.filename != end.filename:
            finding = (
                f"the anchors resolve in different members, {start.filename} and {end.filename}; "
                "a claim spanning two documents bounds no single region"
            )
        elif start.offset is None or end.offset is None:
            finding = "an anchor resolved without an offset"
        elif end.offset + end.match_length < start.offset:
            finding = (
                "the end anchor resolves BEFORE the start anchor. Recorded rather than swapped: a "
                "reversed pair usually means one of the two matched the wrong occurrence, and "
                "silently reordering it would manufacture an interval nobody claimed"
            )
        else:
            interval = Interval(start.offset, max(start.offset, end.offset + end.match_length))
        resolved.append(ResolvedClaim(claim, start, end, interval, finding))
    return tuple(resolved)


@dataclass(frozen=True)
class ItemLedger:
    """The disposition of every item of one kind, with the reason for each."""

    dispositions: dict[str, Disposition]
    reasons: dict[str, str] = field(default_factory=dict)

    def count(self, disposition: Disposition) -> int:
        return sum(1 for value in self.dispositions.values() if value is disposition)

    def ids(self, disposition: Disposition) -> tuple[str, ...]:
        return tuple(
            key for key, value in sorted(self.dispositions.items()) if value is disposition
        )

    def to_mapping(self) -> dict[str, Any]:
        return {
            "counts": {d.value: self.count(d) for d in Disposition},
            "silently_omitted": list(self.ids(Disposition.SILENTLY_OMITTED))[:200],
            "unresolved": list(self.ids(Disposition.UNRESOLVED))[:200],
            "reasons": dict(sorted(self.reasons.items())[:200]),
        }


@dataclass(frozen=True)
class CompletenessLedger:
    """Every accounting this phase can make mechanically, for one model's parse of one filing."""

    cik: str
    accession: str
    source_set_sha256: str
    truth_version: int
    resolved_claims: tuple[ResolvedClaim, ...]
    intervals_by_member: dict[str, tuple[Interval, ...]]
    gaps_by_member: dict[str, tuple[Interval, ...]]
    overlaps_by_member: dict[str, tuple[Interval, ...]]
    spans: ItemLedger
    tables: ItemLedger
    images: ItemLedger
    members: ItemLedger
    coverage: SourceCoverageState
    table_state: TableState
    image_state: ImageState
    findings: tuple[str, ...]

    def to_mapping(self) -> dict[str, Any]:
        return {
            "schema_version": "completeness-ledger-v1",
            "cik": self.cik,
            "accession": self.accession,
            "source_set_sha256": self.source_set_sha256,
            "benchmark_truth_version": self.truth_version,
            "coverage": self.coverage.to_mapping(),
            "tables": self.table_state.to_mapping(),
            "images": self.image_state.to_mapping(),
            "member_ledger": self.members.to_mapping(),
            "span_ledger": self.spans.to_mapping(),
            "table_ledger": self.tables.to_mapping(),
            "image_ledger": self.images.to_mapping(),
            "claims": [c.to_mapping() for c in self.resolved_claims],
            "intervals": {
                member: [i.to_mapping() for i in intervals]
                for member, intervals in sorted(self.intervals_by_member.items())
            },
            "gaps": {
                member: [i.to_mapping() for i in intervals]
                for member, intervals in sorted(self.gaps_by_member.items())
            },
            "overlaps": {
                member: [i.to_mapping() for i in intervals]
                for member, intervals in sorted(self.overlaps_by_member.items())
            },
            "findings": list(self.findings),
            "verdict_note": (
                "Nothing here is a completeness verdict. Every figure is a mechanical accounting "
                "against the preserved bytes and against a human's classification of this one "
                "filing. Semantic completeness is a person's judgement and is recorded separately."
            ),
        }


def build_ledger(
    *,
    inventory: FilingInventory,
    truth: BenchmarkTruth,
    index: ArtifactIndex,
    claims: tuple[CoverageClaim, ...],
    reference_outcomes: tuple[ReferenceOutcome, ...],
    structured_tables: tuple[Any, ...],
    declared_unresolved_spans: frozenset[str] = frozenset(),
    declared_unresolved_tables: frozenset[str] = frozenset(),
    images_submitted: frozenset[str] = frozenset(),
    image_references: frozenset[str] = frozenset(),
    model_accepts_images: bool = False,
) -> CompletenessLedger:
    """Account for every inventory item of one filing against one parse."""
    if truth.source_set_sha256 and truth.source_set_sha256 != inventory.source_set_sha256:
        raise LedgerInputError(
            f"the benchmark truth describes source set {truth.source_set_sha256} and the inventory "
            f"describes {inventory.source_set_sha256}. Coverage of one filing computed against "
            "another filing's denominator is precisely, confidently wrong."
        )

    findings: list[str] = []
    resolved = resolve_claims(claims, index)
    for claim in resolved:
        if claim.finding:
            findings.append(f"{claim.claim.part_id}: {claim.finding}")

    # --- intervals, per member -----------------------------------------------------------------
    by_member: dict[str, list[Interval]] = {}
    for claim in resolved:
        if claim.interval is not None:
            by_member.setdefault(claim.start.filename, []).append(claim.interval)

    intervals = {member: merge(found) for member, found in by_member.items()}
    member_overlaps = {member: overlaps(found) for member, found in by_member.items()}
    member_gaps: dict[str, tuple[Interval, ...]] = {}
    for member in inventory.human_readable_members:
        whole = Interval(0, member.character_count)
        member_gaps[member.member] = gaps(intervals.get(member.member, ()), within=whole)

    # A resolved model reference also LOCATES content, even without a bounding claim. It is a
    # weaker signal than an interval and is recorded as covering only the characters it matched.
    reference_points: dict[str, list[Interval]] = {}
    for outcome in reference_outcomes:
        if outcome.resolved and outcome.offset is not None:
            reference_points.setdefault(outcome.filename, []).append(
                Interval(outcome.offset, outcome.offset + max(1, outcome.match_length))
            )

    # --- spans ---------------------------------------------------------------------------------
    span_dispositions: dict[str, Disposition] = {}
    span_reasons: dict[str, str] = {}
    for span in inventory.spans:
        if not span.visible:
            span_dispositions[span.span_id] = Disposition.HUMAN_EXCLUDED
            span_reasons[span.span_id] = (
                f"the source's own markup hides it: {span.hidden_reason.value}"
            )
            continue
        classification = truth.span(span.span_id)
        if classification in EXCLUDED_SPAN:
            span_dispositions[span.span_id] = Disposition.HUMAN_EXCLUDED
            span_reasons[span.span_id] = f"a reviewer classified it {classification.value}"
            continue
        if span.span_id in declared_unresolved_spans:
            span_dispositions[span.span_id] = Disposition.UNRESOLVED
            span_reasons[span.span_id] = "the model declared this region unresolved"
            continue
        window = Interval(span.start, span.end)
        if _touched(window, intervals.get(span.member, ())) or _touched(
            window, merge(reference_points.get(span.member, []))
        ):
            span_dispositions[span.span_id] = Disposition.COVERED
            continue
        span_dispositions[span.span_id] = Disposition.SILENTLY_OMITTED
        span_reasons[span.span_id] = (
            "no coverage claim bounds it, no resolved reference lands in it, the model did not "
            "declare it unresolved, and no reviewer excluded it"
            + ("" if classification.value != "REQUIRES_REVIEW" else " — and it is unreviewed")
        )

    required_spans = tuple(
        span
        for span in inventory.spans
        if span.visible and truth.span(span.span_id) in REQUIRED_SPAN
    )

    # --- tables --------------------------------------------------------------------------------
    mapped_source_tables = {
        str(getattr(table, "source_table_id", "") or "") for table in structured_tables
    }
    table_dispositions: dict[str, Disposition] = {}
    table_reasons: dict[str, str] = {}
    for element in inventory.tables:
        table_class = truth.table(element.table_id)
        if table_class in EXCLUDED_TABLE:
            table_dispositions[element.table_id] = Disposition.HUMAN_EXCLUDED
            table_reasons[element.table_id] = f"a reviewer classified it {table_class.value}"
            continue
        if element.table_id in declared_unresolved_tables:
            table_dispositions[element.table_id] = Disposition.UNRESOLVED
            table_reasons[element.table_id] = "the model declared this table unresolved"
            continue
        if element.table_id in mapped_source_tables:
            table_dispositions[element.table_id] = Disposition.COVERED
            continue
        table_dispositions[element.table_id] = Disposition.SILENTLY_OMITTED
        table_reasons[element.table_id] = (
            "no structured table artifact maps to this element and the model did not classify it. "
            "Silence is not coverage"
        )

    # --- images --------------------------------------------------------------------------------
    image_dispositions: dict[str, Disposition] = {}
    image_reasons: dict[str, str] = {}
    for image in inventory.images:
        image_class = truth.image(image.filename)
        if image_class in EXCLUDED_IMAGE:
            image_dispositions[image.filename] = Disposition.HUMAN_EXCLUDED
            image_reasons[image.filename] = f"a reviewer classified it {image_class.value}"
            continue
        if image.filename in image_references:
            image_dispositions[image.filename] = Disposition.COVERED
            continue
        if not model_accepts_images:
            image_dispositions[image.filename] = Disposition.UNRESOLVED
            image_reasons[image.filename] = (
                "the selected parsing model is text-only, so this image was not analysed. That is "
                "not a defect and this parse simply does not claim image coverage"
            )
            continue
        image_dispositions[image.filename] = Disposition.SILENTLY_OMITTED
        image_reasons[image.filename] = (
            "the image was submitted to a multimodal parser and no part referenced it"
        )

    # --- members -------------------------------------------------------------------------------
    member_dispositions: dict[str, Disposition] = {}
    member_reasons: dict[str, str] = {}
    for member in inventory.members:
        if not member.human_readable and not member.image:
            member_dispositions[member.member] = Disposition.HUMAN_EXCLUDED
            member_reasons[member.member] = (
                f"transport role {member.transport_role}: its content never reaches the parsing "
                "model, so it is not a coverage target"
            )
            continue
        if member.image:
            member_dispositions[member.member] = image_dispositions.get(
                member.filename, Disposition.SILENTLY_OMITTED
            )
            continue
        member_spans = [s for s in inventory.spans_for(member.member) if s.visible]
        if not member_spans:
            member_dispositions[member.member] = Disposition.HUMAN_EXCLUDED
            member_reasons[member.member] = "the member carries no visible text span at all"
            continue
        if any(span_dispositions[s.span_id] is Disposition.COVERED for s in member_spans):
            member_dispositions[member.member] = Disposition.COVERED
            continue
        member_dispositions[member.member] = Disposition.SILENTLY_OMITTED
        member_reasons[member.member] = (
            "not one visible span of this member is covered by any claim or resolved reference"
        )

    spans_ledger = ItemLedger(span_dispositions, span_reasons)
    tables_ledger = ItemLedger(table_dispositions, table_reasons)
    images_ledger = ItemLedger(image_dispositions, image_reasons)
    members_ledger = ItemLedger(member_dispositions, member_reasons)

    characters_total = sum(s.character_count for s in inventory.visible_spans)
    characters_covered = sum(covered_length(intervals.get(member, ())) for member in intervals)

    coverage = SourceCoverageState(
        members_total=len([m for m in inventory.members if m.human_readable or m.image]),
        members_accounted=members_ledger.count(Disposition.COVERED)
        + members_ledger.count(Disposition.UNRESOLVED)
        + sum(
            1
            for m in inventory.members
            if (m.human_readable or m.image)
            and member_dispositions.get(m.member) is Disposition.HUMAN_EXCLUDED
        ),
        spans_total=len(inventory.visible_spans),
        spans_covered=spans_ledger.count(Disposition.COVERED),
        spans_unresolved=spans_ledger.count(Disposition.UNRESOLVED),
        spans_human_excluded=sum(
            1
            for s in inventory.visible_spans
            if span_dispositions[s.span_id] is Disposition.HUMAN_EXCLUDED
        ),
        characters_total=characters_total,
        characters_covered=min(characters_covered, characters_total)
        if characters_total
        else characters_covered,
        intervals_covered=sum(len(v) for v in intervals.values()),
        intervals_overlapping=sum(len(v) for v in member_overlaps.values()),
    )

    data_bearing = [
        element for element in inventory.tables if truth.table(element.table_id) in REQUIRED_TABLE
    ]
    table_state = TableState(
        elements_total=len(inventory.tables),
        elements_data_bearing=len(data_bearing),
        elements_accounted=sum(
            1
            for element in data_bearing
            if table_dispositions[element.table_id] is Disposition.COVERED
        ),
        elements_human_excluded=tables_ledger.count(Disposition.HUMAN_EXCLUDED),
        elements_unresolved=tables_ledger.count(Disposition.UNRESOLVED),
        structured_emitted=len(structured_tables),
        structured_source_resolved=sum(
            1
            for table in structured_tables
            if str(getattr(table, "source_table_id", "") or "")
            and inventory.table(str(table.source_table_id)) is not None
        ),
        structured_failing_validation=0,
        cells_unresolved=sum(
            int(getattr(table, "unresolved_cell_count", 0)) for table in structured_tables
        ),
        model_classified_layout=sum(
            1
            for table in structured_tables
            if "layout" in str(getattr(table, "classification", "")).lower()
        ),
        model_classified_navigation=sum(
            1
            for table in structured_tables
            if "navigation" in str(getattr(table, "classification", "")).lower()
        ),
    )

    image_state = ImageState(
        images_total=len(inventory.images),
        submitted_to_parser=len(images_submitted),
        referenced_by_model=images_ledger.count(Disposition.COVERED),
        human_excluded=images_ledger.count(Disposition.HUMAN_EXCLUDED),
        unresolved=0 if model_accepts_images else images_ledger.count(Disposition.UNRESOLVED),
        not_analysed_text_only=(
            0 if model_accepts_images else images_ledger.count(Disposition.UNRESOLVED)
        ),
    )

    if coverage.spans_silently_omitted:
        findings.append(
            f"{coverage.spans_silently_omitted} visible source span(s) are neither covered, nor "
            "declared unresolved, nor excluded by a reviewer"
        )
    if table_state.elements_silently_omitted:
        findings.append(
            f"{table_state.elements_silently_omitted} table element(s) are unaccounted for"
        )
    unreviewed = sum(
        1 for span in inventory.visible_spans if truth.span(span.span_id).value == "REQUIRES_REVIEW"
    )
    if unreviewed:
        findings.append(
            f"{unreviewed} visible span(s) and "
            f"{sum(1 for t in inventory.tables if truth.table(t.table_id).value == 'REQUIRES_REVIEW')}"
            " table element(s) carry no human classification yet, so the required set is not final"
        )
    if not required_spans:
        findings.append(
            "no span has been classified MATERIAL_FILING_CONTENT, so there is no reviewed required "
            "set to measure against and every percentage below is provisional"
        )

    return CompletenessLedger(
        cik=inventory.cik,
        accession=inventory.accession,
        source_set_sha256=inventory.source_set_sha256,
        truth_version=truth.version,
        resolved_claims=resolved,
        intervals_by_member=intervals,
        gaps_by_member=member_gaps,
        overlaps_by_member=member_overlaps,
        spans=spans_ledger,
        tables=tables_ledger,
        images=images_ledger,
        members=members_ledger,
        coverage=coverage,
        table_state=table_state,
        image_state=image_state,
        findings=tuple(findings),
    )


def _touched(window: Interval, intervals: tuple[Interval, ...]) -> bool:
    """Whether any covering interval overlaps this span at all.

    OVERLAP, NOT CONTAINMENT, AND THE CHOICE MATTERS. A model bounding a region by quoting its
    first and last sentence produces an interval that starts inside the first span and ends inside
    the last one, so demanding containment would report both end spans as omitted on every
    correctly bounded claim. Overlap is the weaker test and it is the honest one: it says the claim
    reaches this span, and it never says the model represented what is in it.
    """
    return any(window.overlaps(interval) for interval in intervals)
