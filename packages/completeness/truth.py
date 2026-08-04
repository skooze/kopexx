"""The human benchmark truth for ONE filing: what a person says the mechanical inventory contains.

THE BACKEND CANNOT SUPPLY SEMANTIC TRUTH AND THIS MODULE DOES NOT PRETEND TO. `packages/
source_inventory` can say there are 41 table elements in Apple's 10-Q. It cannot say which of them
carry data, which are Workiva's page-layout scaffolding, and which are the same rendering twice. A
completeness ledger that treated all 41 as required content would report every parse as incomplete
forever; one that guessed which eight are layout would be a backend deciding what filing content
means, which `rules.md` invariant 14 and section 21 rule 1 both forbid.

    SO A PERSON DECIDES, AND THE DECISION IS DATA. Every classification here is recorded with who
    made it and when, is versioned, is reviewable, and is scoped to ONE filing. It is evidence
    about Apple's 10-Q for accession 0000320193-25-000008, not a rule about filings.

NOTHING IS PREFILLED WITH A SEMANTIC CONCLUSION. The default classification of every item is
`REQUIRES_REVIEW`. A default of "material" would silently make every layout table a required parse
target; a default of "layout" would silently excuse a model from a real financial statement.
`REQUIRES_REVIEW` is honest about the state of the evidence and it blocks the mechanical gate,
which is the correct pressure.

    THE ONE MECHANICAL PREFILL, AND WHY IT IS NOT A JUDGEMENT. `suggest` proposes
    `MECHANICALLY_EMPTY` for a table element in which no cell carries a single non-whitespace
    character, and `MECHANICALLY_DUPLICATE` for one whose source slice is byte-identical to an
    earlier element's. Both are observations about bytes that a reviewer can check in one glance,
    both are recorded as SUGGESTIONS with the evidence attached, and neither is applied until a
    person accepts it.

GENERALISING ANY OF THIS IS THE FAILURE MODE. `rules.md` section 21 rule 14: a claim about what
filings contain requires measurement across multiple issuers, industries and eras. One issuer is a
fixture, never a specification. Apple's layout tables are Workiva's layout tables, and a rule
derived from them would be a rule about one filing agent.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from .errors import BenchmarkTruthError


class SpanClassification(StrEnum):
    """What a reviewer says one mechanical text span is."""

    REQUIRES_REVIEW = "REQUIRES_REVIEW"
    MATERIAL_FILING_CONTENT = "MATERIAL_FILING_CONTENT"
    REPEATED_CONTENT = "REPEATED_CONTENT"
    NAVIGATION = "NAVIGATION"
    PURE_TRANSPORT_MARKUP = "PURE_TRANSPORT_MARKUP"
    NOT_HUMAN_READABLE = "NOT_HUMAN_READABLE"


class TableClassification(StrEnum):
    """What a reviewer says one mechanical table element is."""

    REQUIRES_REVIEW = "REQUIRES_REVIEW"
    DATA_BEARING = "DATA_BEARING"
    LAYOUT = "LAYOUT"
    NAVIGATION = "NAVIGATION"
    DUPLICATE_RENDERING = "DUPLICATE_RENDERING"
    EMPTY = "EMPTY"


class ImageClassification(StrEnum):
    """What a reviewer says one filed image is."""

    REQUIRES_REVIEW = "REQUIRES_REVIEW"
    DATA_BEARING = "DATA_BEARING"
    LOGO = "LOGO"
    DECORATIVE = "DECORATIVE"
    DUPLICATE_RENDERING = "DUPLICATE_RENDERING"


#: Classifications under which an item is REQUIRED to be represented in an accepted parse.
REQUIRED_SPAN = frozenset({SpanClassification.MATERIAL_FILING_CONTENT})
REQUIRED_TABLE = frozenset({TableClassification.DATA_BEARING})
REQUIRED_IMAGE = frozenset({ImageClassification.DATA_BEARING})

#: Classifications that EXCLUDE an item from the required set, with the reviewer's reason attached.
#: `REQUIRES_REVIEW` is in NEITHER set, deliberately: an unreviewed item is not excused and is not
#: demanded, it simply blocks the gate until a person looks at it.
EXCLUDED_SPAN = frozenset(
    {
        SpanClassification.REPEATED_CONTENT,
        SpanClassification.NAVIGATION,
        SpanClassification.PURE_TRANSPORT_MARKUP,
        SpanClassification.NOT_HUMAN_READABLE,
    }
)
EXCLUDED_TABLE = frozenset(
    {
        TableClassification.LAYOUT,
        TableClassification.NAVIGATION,
        TableClassification.DUPLICATE_RENDERING,
        TableClassification.EMPTY,
    }
)
EXCLUDED_IMAGE = frozenset(
    {
        ImageClassification.LOGO,
        ImageClassification.DECORATIVE,
        ImageClassification.DUPLICATE_RENDERING,
    }
)


@dataclass(frozen=True)
class Judgement:
    """One reviewer's classification of one inventory item, with its provenance."""

    item_id: str
    classification: str
    reviewer: str
    at: str
    note: str = ""
    suggested: bool = False
    evidence: str = ""

    def to_mapping(self) -> dict[str, Any]:
        return {
            "item_id": self.item_id,
            "classification": self.classification,
            "reviewer": self.reviewer,
            "at": self.at,
            "note": self.note,
            "is_unaccepted_suggestion": self.suggested,
            "evidence": self.evidence,
        }


@dataclass(frozen=True)
class BenchmarkTruth:
    """Every human judgement about one filing's mechanical inventory, at one version.

    IT IS SUPERSEDED, NEVER OVERWRITTEN. `version` increments and the previous document stays on
    disk, exactly as an accepted artifact is superseded rather than rewritten — `rules.md`
    invariant 7. A completeness figure computed against version 3 is meaningless if version 3 can
    be edited into version 4 under the same name.
    """

    cik: str
    accession: str
    source_set_sha256: str
    version: int
    spans: dict[str, Judgement] = field(default_factory=dict)
    tables: dict[str, Judgement] = field(default_factory=dict)
    images: dict[str, Judgement] = field(default_factory=dict)

    def span(self, span_id: str) -> SpanClassification:
        judgement = self.spans.get(span_id)
        return (
            _as(SpanClassification, judgement.classification)
            if judgement is not None and not judgement.suggested
            else SpanClassification.REQUIRES_REVIEW
        )

    def table(self, table_id: str) -> TableClassification:
        judgement = self.tables.get(table_id)
        return (
            _as(TableClassification, judgement.classification)
            if judgement is not None and not judgement.suggested
            else TableClassification.REQUIRES_REVIEW
        )

    def image(self, filename: str) -> ImageClassification:
        judgement = self.images.get(filename)
        return (
            _as(ImageClassification, judgement.classification)
            if judgement is not None and not judgement.suggested
            else ImageClassification.REQUIRES_REVIEW
        )

    @property
    def reviewed_count(self) -> int:
        return sum(
            1
            for group in (self.spans, self.tables, self.images)
            for judgement in group.values()
            if not judgement.suggested
        )

    @property
    def suggestion_count(self) -> int:
        return sum(
            1
            for group in (self.spans, self.tables, self.images)
            for judgement in group.values()
            if judgement.suggested
        )

    def with_judgement(self, kind: str, judgement: Judgement) -> BenchmarkTruth:
        """A NEW truth document carrying one more judgement, at the next version."""
        groups = {
            "span": dict(self.spans),
            "table": dict(self.tables),
            "image": dict(self.images),
        }
        if kind not in groups:
            raise BenchmarkTruthError(
                f"{kind!r} is not one of span, table or image; a judgement about anything else "
                "has no inventory item to attach to"
            )
        _validate(kind, judgement.classification)
        groups[kind][judgement.item_id] = judgement
        return BenchmarkTruth(
            cik=self.cik,
            accession=self.accession,
            source_set_sha256=self.source_set_sha256,
            version=self.version + 1,
            spans=groups["span"],
            tables=groups["table"],
            images=groups["image"],
        )

    def to_mapping(self) -> dict[str, Any]:
        return {
            "schema_version": "benchmark-truth-v1",
            "cik": self.cik,
            "accession": self.accession,
            "source_set_sha256": self.source_set_sha256,
            "version": self.version,
            "reviewed_count": self.reviewed_count,
            "suggestion_count": self.suggestion_count,
            "spans": {k: v.to_mapping() for k, v in sorted(self.spans.items())},
            "tables": {k: v.to_mapping() for k, v in sorted(self.tables.items())},
            "images": {k: v.to_mapping() for k, v in sorted(self.images.items())},
            "scope_note": (
                "Every judgement here is about ONE filing at ONE source hash. It is evidence about "
                "this accession and is never a rule about filings — rules.md section 21 rule 14."
            ),
        }

    @classmethod
    def from_mapping(cls, document: dict[str, Any]) -> BenchmarkTruth:
        def group(name: str) -> dict[str, Judgement]:
            raw = document.get(name)
            if not isinstance(raw, dict):
                return {}
            return {
                str(key): Judgement(
                    item_id=str(value.get("item_id") or key),
                    classification=str(value.get("classification") or ""),
                    reviewer=str(value.get("reviewer") or ""),
                    at=str(value.get("at") or ""),
                    note=str(value.get("note") or ""),
                    suggested=bool(value.get("is_unaccepted_suggestion")),
                    evidence=str(value.get("evidence") or ""),
                )
                for key, value in raw.items()
                if isinstance(value, dict)
            }

        return cls(
            cik=str(document.get("cik") or ""),
            accession=str(document.get("accession") or ""),
            source_set_sha256=str(document.get("source_set_sha256") or ""),
            version=int(document.get("version") or 0),
            spans=group("spans"),
            tables=group("tables"),
            images=group("images"),
        )

    @classmethod
    def empty(cls, *, cik: str, accession: str, source_set_sha256: str) -> BenchmarkTruth:
        return cls(cik=cik, accession=accession, source_set_sha256=source_set_sha256, version=0)


def suggest(inventory: Any, *, at: str) -> BenchmarkTruth:
    """A truth document carrying only the two BYTE-LEVEL suggestions, none of them accepted.

    `at` is passed in rather than read from the clock, so the same inventory produces the same
    document twice. A record that changes every time it is derived cannot be compared against
    itself, and this one is the denominator of a benchmark.
    """
    truth = BenchmarkTruth.empty(
        cik=inventory.cik,
        accession=inventory.accession,
        source_set_sha256=inventory.source_set_sha256,
    )
    tables: dict[str, Judgement] = {}
    for element in inventory.tables:
        if element.duplicate_of:
            tables[element.table_id] = Judgement(
                item_id=element.table_id,
                classification=TableClassification.DUPLICATE_RENDERING.value,
                reviewer="",
                at=at,
                suggested=True,
                evidence=(
                    f"the source slice is byte-identical to {element.duplicate_of}; "
                    f"sha256 {element.sha256}"
                ),
            )
        elif element.is_empty:
            tables[element.table_id] = Judgement(
                item_id=element.table_id,
                classification=TableClassification.EMPTY.value,
                reviewer="",
                at=at,
                suggested=True,
                evidence=(
                    f"none of its {element.cell_count} cells carries a non-whitespace character"
                ),
            )
    spans: dict[str, Judgement] = {
        span.span_id: Judgement(
            item_id=span.span_id,
            classification=SpanClassification.REPEATED_CONTENT.value,
            reviewer="",
            at=at,
            suggested=True,
            evidence=f"its normalised characters are identical to {span.duplicate_of}",
        )
        for span in inventory.spans
        if span.duplicate_of
    }
    return BenchmarkTruth(
        cik=truth.cik,
        accession=truth.accession,
        source_set_sha256=truth.source_set_sha256,
        version=0,
        spans=spans,
        tables=tables,
    )


def _as(enum: Any, value: str) -> Any:
    try:
        return enum(value)
    except ValueError:
        return enum.REQUIRES_REVIEW


def _validate(kind: str, classification: str) -> None:
    enums = {
        "span": SpanClassification,
        "table": TableClassification,
        "image": ImageClassification,
    }
    try:
        enums[kind](classification)
    except ValueError as error:
        allowed = ", ".join(member.value for member in enums[kind])
        raise BenchmarkTruthError(
            f"{classification!r} is not a {kind} classification. Allowed: {allowed}"
        ) from error
