"""Centralized LLM gateway: the only path from FinTek to a language model.

LLM-SERIALIZATION-INVARIANT: model-visible content is unmarked plain text or exactly one
unfenced YAML 1.2 document. See rules.md section 3, docs/llm/content-boundary.md, and
docs/adr/ADR-0013-plain-text-or-yaml-llm-boundary.md.
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
from .capabilities import ModelCapabilities
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
    FootnoteSummaryRequest,
    SourceBlockPayload,
    TablePayload,
    compile_footnote_summary_request,
    compile_plain_text,
    compile_yaml,
    reject_native_tools,
)
from .token_counter import SerializationComparison, estimate_tokens
from .yaml_parser import parse_yaml, require_mapping, require_string
from .yaml_serializer import to_yaml

__all__ = [
    "BoundaryReport",
    "BoundaryViolationError",
    "Budget",
    "BudgetExceededError",
    "CompiledPayload",
    "ContentFormat",
    "FootnoteSummaryRequest",
    "GatewayResult",
    "InvocationRecord",
    "LlmGateway",
    "LlmGatewayError",
    "ModelCapabilities",
    "ModelPricing",
    "NativeToolUseProhibitedError",
    "PricingRegistry",
    "ProviderError",
    "SerializationComparison",
    "SourceBlockPayload",
    "TablePayload",
    "Violation",
    "YamlParseError",
    "YamlSafetyError",
    "compile_footnote_summary_request",
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
