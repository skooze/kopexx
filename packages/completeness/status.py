"""The completeness status model: SIX INDEPENDENT DIMENSIONS, never one boolean.

WHY NOT ONE VALUE. Phase 2.1 reported `AssemblyStatus` with three members and a repeated warning
that none of them meant complete. That warning was doing work a type should do. A run can have
reached every provider it needed, produced documents that will not parse, covered most of the
source, emitted no table at all, stopped because a budget ran out, and be perfectly reviewable — and
there is no single word for that. Collapsing it into one produces either a false complete or a
false failure, and this repository has now written both by accident.

    Phase 2.1's `INCOMPLETE_WORK` meant "scheduled work did not finish". Its
    `RECONCILIATION_UNRESOLVED` meant "the last reconciliation returned plan_complete false".
    Neither judged parse quality, and both were read as if they did. Six dimensions cannot be
    misread that way because none of them is a score.

WHAT IS DELIBERATELY ABSENT FROM EVERY ENUM HERE. A value meaning SEMANTICALLY COMPLETE. Nothing
mechanical establishes it. The strongest mechanical verdict is that a result carries enough
evidence to undergo human completeness review, and only a person may record the other one.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class TransportState(StrEnum):
    """Whether the provider was reached at all, and what happened if it was."""

    NOT_RUN = "NOT_RUN"
    #: Credential resolution failed before any request left this machine. Distinguished from a
    #: provider failure because the billing consequence is different and provable — see
    #: `packages/orchestrator/spend_journal.py`.
    CREDENTIAL_BLOCKED = "CREDENTIAL_BLOCKED"
    #: The filing does not fit this model's context intact. Under INTACT_SOURCE_ONLY this is a
    #: RESULT, not a failure: nothing is truncated, sliced or swapped to another model.
    INCOMPATIBLE = "INCOMPATIBLE"
    INVOKED = "INVOKED"
    PROVIDER_FAILED = "PROVIDER_FAILED"


class SerializationState(StrEnum):
    """Whether what came back can be read, and whether it took a repair to get there.

    THE THREE ARE REPORTED SEPARATELY AND NEVER COLLAPSED. A parse that needed a format repair is
    usable, and the model that produced it did not serialise correctly. Reporting only the second
    fact hides working evidence; reporting only the first credits a model with something it did
    not do.
    """

    RAW_PARSEABLE = "RAW_PARSEABLE"
    REPAIR_PARSEABLE = "REPAIR_PARSEABLE"
    UNPARSEABLE = "UNPARSEABLE"
    NOT_RUN = "NOT_RUN"


class ConvergenceState(StrEnum):
    """Why the scheduler stopped creating work."""

    CONVERGED = "CONVERGED"
    STOPPED_NO_PROGRESS = "STOPPED_NO_PROGRESS"
    STOPPED_PART_LIMIT = "STOPPED_PART_LIMIT"
    STOPPED_CYCLE_LIMIT = "STOPPED_CYCLE_LIMIT"
    STOPPED_BUDGET = "STOPPED_BUDGET"
    INTERRUPTED = "INTERRUPTED"
    NOT_RUN = "NOT_RUN"


class HumanReadiness(StrEnum):
    """Where the result sits with respect to the one judgement backend code may not make."""

    NOT_RUN = "NOT_RUN"
    REVIEW_BLOCKED = "REVIEW_BLOCKED"
    READY_FOR_REVIEW = "READY_FOR_REVIEW"
    #: The ONLY value a person may set, and the only statement of semantic completeness this
    #: repository recognises. It is scoped to one filing, one source hash, one model, one model
    #: version, one region or profile, one prompt version, one settings set and one protocol.
    HUMAN_APPROVED_COMPLETE_FOR_THIS_FILING = "HUMAN_APPROVED_COMPLETE_FOR_THIS_FILING"
    HUMAN_REJECTED_COMPLETENESS = "HUMAN_REJECTED_COMPLETENESS"


@dataclass(frozen=True)
class SourceCoverageState:
    """Exact counts, and the percentages derived from them. Third dimension.

    PERCENTAGES ARE DERIVED AND THE COUNTS ARE AUTHORITATIVE. A percentage with no denominator
    beside it is what made "352 of 364 references resolved" read as 96.7 percent coverage of a
    filing, which it never was.
    """

    members_total: int
    members_accounted: int
    spans_total: int
    spans_covered: int
    spans_unresolved: int
    spans_human_excluded: int
    characters_total: int
    characters_covered: int
    intervals_covered: int
    intervals_overlapping: int

    @property
    def members_percent(self) -> float:
        return _percent(self.members_accounted, self.members_total)

    @property
    def spans_percent(self) -> float:
        return _percent(self.spans_covered, self.spans_total)

    @property
    def characters_percent(self) -> float:
        return _percent(self.characters_covered, self.characters_total)

    @property
    def spans_silently_omitted(self) -> int:
        """Spans neither covered, nor explicitly unresolved, nor excluded by a human.

        THIS IS THE NUMBER THE WHOLE PACKAGE EXISTS TO PRODUCE. A span in this count is filing
        content the model never mentioned in any way — not cited, not declared unresolved, not
        classified. It is exactly the omission a reference rate cannot see.
        """
        return max(
            0,
            self.spans_total
            - self.spans_covered
            - self.spans_unresolved
            - self.spans_human_excluded,
        )

    def to_mapping(self) -> dict[str, Any]:
        return {
            "members_total": self.members_total,
            "members_accounted": self.members_accounted,
            "members_percent": self.members_percent,
            "spans_total": self.spans_total,
            "spans_covered": self.spans_covered,
            "spans_unresolved": self.spans_unresolved,
            "spans_human_excluded": self.spans_human_excluded,
            "spans_silently_omitted": self.spans_silently_omitted,
            "spans_percent": self.spans_percent,
            "characters_total": self.characters_total,
            "characters_covered": self.characters_covered,
            "characters_percent": self.characters_percent,
            "intervals_covered": self.intervals_covered,
            "intervals_overlapping": self.intervals_overlapping,
        }


@dataclass(frozen=True)
class TableState:
    """What happened to the mechanical table inventory. Fourth dimension.

    `elements_total` is the count of `table` elements in the preserved bytes. It is a mechanical
    fact and it is NOT a claim that every one of them is a data-bearing table — that classification
    belongs to the model, with source evidence, and to a human reviewer who may overrule it.
    """

    elements_total: int
    elements_data_bearing: int
    elements_accounted: int
    elements_human_excluded: int
    elements_unresolved: int
    structured_emitted: int
    structured_source_resolved: int
    structured_failing_validation: int
    cells_unresolved: int
    model_classified_layout: int
    model_classified_navigation: int

    @property
    def elements_silently_omitted(self) -> int:
        return max(
            0,
            self.elements_total
            - self.elements_accounted
            - self.elements_human_excluded
            - self.elements_unresolved,
        )

    @property
    def data_bearing_percent(self) -> float:
        return _percent(self.elements_accounted, self.elements_data_bearing)

    def to_mapping(self) -> dict[str, Any]:
        return {
            "elements_total": self.elements_total,
            "elements_data_bearing": self.elements_data_bearing,
            "elements_accounted": self.elements_accounted,
            "elements_human_excluded": self.elements_human_excluded,
            "elements_unresolved": self.elements_unresolved,
            "elements_silently_omitted": self.elements_silently_omitted,
            "data_bearing_percent": self.data_bearing_percent,
            "structured_emitted": self.structured_emitted,
            "structured_source_resolved": self.structured_source_resolved,
            "structured_failing_validation": self.structured_failing_validation,
            "cells_unresolved": self.cells_unresolved,
            "model_classified_layout": self.model_classified_layout,
            "model_classified_navigation": self.model_classified_navigation,
            "note": (
                "elements_total counts table ELEMENTS in the preserved bytes. It asserts nothing "
                "about which of them carry data; the model classifies with source evidence and a "
                "human reviewer may overrule it."
            ),
        }


@dataclass(frozen=True)
class ImageState:
    """What happened to every filed image. Fifth dimension.

    `not_analysed_text_only` is not a failure. A text-only parser is not penalised for lacking
    vision — but its parse may not claim image coverage either, and separating the two is the whole
    reason this is a count rather than a boolean.
    """

    images_total: int
    submitted_to_parser: int
    referenced_by_model: int
    human_excluded: int
    unresolved: int
    not_analysed_text_only: int

    @property
    def accounted(self) -> int:
        return (
            self.referenced_by_model
            + self.human_excluded
            + self.unresolved
            + self.not_analysed_text_only
        )

    @property
    def silently_omitted(self) -> int:
        return max(0, self.images_total - self.accounted)

    def to_mapping(self) -> dict[str, Any]:
        return {
            "images_total": self.images_total,
            "submitted_to_parser": self.submitted_to_parser,
            "referenced_by_model": self.referenced_by_model,
            "human_excluded": self.human_excluded,
            "unresolved": self.unresolved,
            "not_analysed_text_only": self.not_analysed_text_only,
            "accounted": self.accounted,
            "silently_omitted": self.silently_omitted,
        }


def _percent(part: int, whole: int) -> float:
    return round(part * 100.0 / whole, 2) if whole else 0.0
