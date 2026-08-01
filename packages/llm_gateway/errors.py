"""Typed errors for the LLM gateway."""

from __future__ import annotations


class LlmGatewayError(Exception):
    """Base class for every gateway failure."""


class BoundaryViolationError(LlmGatewayError):
    """Model-visible content contained a prohibited serialization.

    SECURITY-INVARIANT: the offending content is NOT stored on the exception. It may be large and
    may contain filing text. Only the origin, declared format, and violation names are carried.
    """

    def __init__(
        self,
        *,
        origin: str,
        declared_format: str,
        violations: list[str],
        detail: str = "",
    ) -> None:
        self.origin = origin
        self.declared_format = declared_format
        self.violations = violations
        self.detail = detail
        super().__init__(
            f"model-visible content from {origin!r} declared as {declared_format!r} "
            f"contains prohibited constructs: {', '.join(violations)}"
            + (f" ({detail})" if detail else "")
        )


class YamlSafetyError(LlmGatewayError):
    """A YAML document violated a parser safety limit."""


class YamlParseError(LlmGatewayError):
    """A model response was not parseable as YAML."""


class ProviderError(LlmGatewayError):
    """A model provider failed."""

    def __init__(self, message: str, *, retryable: bool, provider: str) -> None:
        self.retryable = retryable
        self.provider = provider
        super().__init__(message)


class NativeToolUseProhibitedError(LlmGatewayError):
    """A caller attempted to pass native tool definitions to a provider.

    Native tool calling requires JSON Schema tool definitions and produces JSON tool arguments,
    both of which are prohibited at the model boundary. Deep Analysis uses the bounded YAML
    action protocol instead.
    """


class BudgetExceededError(LlmGatewayError):
    """The invocation would exceed a configured token or cost budget."""
