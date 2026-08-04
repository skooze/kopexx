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
    BenchmarkFilingCatalog,
    CompositeFilingCatalog,
    CorpusFilingCatalog,
    EntityRecord,
    FilingCatalog,
    FilingRecord,
    PreservedFile,
)
from .errors import (
    CeilingReachedError,
    FilingNotInCatalogError,
    MultipartProtocolError,
    NoParsingModelError,
    OrchestratorError,
    StageNotAuthorizedError,
    UnknownStrategyError,
)
from .multipart_service import MultipartParseService, MultipartSettings
from .service import (
    MINIMUM_PARSE_OUTPUT_TOKENS,
    MULTIPART_STRATEGY,
    OUTPUT_RATIO_OF_INPUT,
    SINGLE_RESPONSE_STRATEGY,
    STRATEGIES,
    InventoriedFiling,
    ParserReviewService,
    PreflightItem,
    RunPlan,
    RunRequest,
    sized_output_tokens,
)
from .sizing import (
    MAXIMUM_PART_TARGET_TOKENS,
    MINIMUM_PART_TARGET_TOKENS,
    OutputSizing,
    compact_sizing,
    part_sizing,
    repair_sizing,
)
from .spend_journal import SpendEntry, SpendJournal
from .worker import BoundedWorker, InlineWorker

__all__ = [
    "MAXIMUM_PART_TARGET_TOKENS",
    "MINIMUM_PARSE_OUTPUT_TOKENS",
    "MINIMUM_PART_TARGET_TOKENS",
    "MULTIPART_STRATEGY",
    "OUTPUT_RATIO_OF_INPUT",
    "SINGLE_RESPONSE_STRATEGY",
    "STRATEGIES",
    "BoundedWorker",
    "CeilingReachedError",
    "BenchmarkFilingCatalog",
    "CompositeFilingCatalog",
    "CorpusFilingCatalog",
    "EntityRecord",
    "FilingCatalog",
    "FilingNotInCatalogError",
    "FilingRecord",
    "InlineWorker",
    "InventoriedFiling",
    "MultipartParseService",
    "MultipartProtocolError",
    "MultipartSettings",
    "NoParsingModelError",
    "OrchestratorError",
    "OutputSizing",
    "ParserReviewService",
    "PreflightItem",
    "PreservedFile",
    "RunPlan",
    "RunRequest",
    "SpendEntry",
    "SpendJournal",
    "StageNotAuthorizedError",
    "UnknownStrategyError",
    "compact_sizing",
    "part_sizing",
    "repair_sizing",
    "sized_output_tokens",
]
