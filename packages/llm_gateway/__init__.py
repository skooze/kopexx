"""Centralized LLM gateway: the only path from FinTek to a language model.

LLM-SERIALIZATION-INVARIANT: model-visible SYNTHETIC content is unmarked plain text or exactly one
unfenced YAML 1.2 document. A preserved original SEC artifact is admitted by PROVENANCE and sent
intact in whatever syntax SEC published it. See rules.md section 3, docs/llm/content-boundary.md,
and docs/adr/ADR-0013-plain-text-or-yaml-llm-boundary.md.

GENERIC BY CONSTRUCTION. This package knows about model identity, roles, budgets, formats, bytes,
tokens, cost and latency. It knows nothing about what a filing contains, and it must not learn.
The footnote-shaped request contract that used to live here — `FootnoteSummaryRequest`,
`SourceBlockPayload`, `TablePayload`, `compile_footnote_summary_request` — was deleted with the
deterministic parser whose output it carried. No model has ever been invoked, so no request or
response contract is known; the real ones are derived from observed model behaviour in the
parser-experiment stage, not declared here in advance.
"""

from .boundary_validator import (
    BoundaryReport,
    ContentFormat,
    Violation,
    enforce,
    validate,
    validate_plain_text,
    validate_yaml_text,
)
from .cost_calculator import ModelPricing, PricingRegistry, default_registry
from .errors import (
    BoundaryViolationError,
    BudgetExceededError,
    LlmGatewayError,
    NativeToolUseProhibitedError,
    ProviderError,
    YamlParseError,
    YamlSafetyError,
)
from .gateway import Budget, GatewayResult, InvocationRecord, LlmGateway
from .payload_compiler import (
    CompiledPayload,
    compile_plain_text,
    compile_yaml,
    reject_native_tools,
)
from .token_counter import estimate_tokens
from .yaml_parser import parse_yaml, require_mapping, require_string
from .yaml_serializer import to_yaml

__all__ = [
    "BoundaryReport",
    "BoundaryViolationError",
    "Budget",
    "BudgetExceededError",
    "CompiledPayload",
    "ContentFormat",
    "GatewayResult",
    "InvocationRecord",
    "LlmGateway",
    "LlmGatewayError",
    "ModelPricing",
    "NativeToolUseProhibitedError",
    "PricingRegistry",
    "ProviderError",
    "Violation",
    "YamlParseError",
    "YamlSafetyError",
    "compile_plain_text",
    "compile_yaml",
    "default_registry",
    "enforce",
    "estimate_tokens",
    "parse_yaml",
    "reject_native_tools",
    "require_mapping",
    "require_string",
    "to_yaml",
    "validate",
    "validate_plain_text",
    "validate_yaml_text",
]
