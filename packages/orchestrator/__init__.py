"""Parent runs, child filing jobs, and the parser-only workflow.

The orchestrator discovers nothing about what a filing means. It resolves identity, assembles a
source set mechanically, checks compatibility, bounds cost, invokes exactly the stages the user
selected, preserves exactly what crossed the wire, validates the result against the preserved
bytes, and stops. Every semantic judgement in the pipeline belongs to the selected parsing model.

Phase 2 runs the parsing stage only. The other three roles have selectors, are routed, and are
recorded — and executing one raises, because a stage this phase did not authorize is a scope
violation rather than a missing feature.
"""

from .catalog import (
    CorpusFilingCatalog,
    EntityRecord,
    FilingCatalog,
    FilingRecord,
    PreservedFile,
)
from .errors import (
    CeilingReachedError,
    FilingNotInCatalogError,
    NoParsingModelError,
    OrchestratorError,
    StageNotAuthorizedError,
)
from .service import (
    MINIMUM_PARSE_OUTPUT_TOKENS,
    OUTPUT_RATIO_OF_INPUT,
    ParserReviewService,
    PreflightItem,
    RunPlan,
    RunRequest,
    sized_output_tokens,
)
from .spend_journal import SpendEntry, SpendJournal
from .worker import BoundedWorker, InlineWorker

__all__ = [
    "MINIMUM_PARSE_OUTPUT_TOKENS",
    "OUTPUT_RATIO_OF_INPUT",
    "BoundedWorker",
    "CeilingReachedError",
    "CorpusFilingCatalog",
    "EntityRecord",
    "FilingCatalog",
    "FilingNotInCatalogError",
    "FilingRecord",
    "InlineWorker",
    "NoParsingModelError",
    "OrchestratorError",
    "ParserReviewService",
    "PreflightItem",
    "PreservedFile",
    "RunPlan",
    "RunRequest",
    "SpendEntry",
    "SpendJournal",
    "StageNotAuthorizedError",
    "sized_output_tokens",
]
