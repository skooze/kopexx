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
    """A model provider failed.

    `transport_attempted` IS A BILLING FACT AND THAT IS WHY IT IS ON THE ERROR. A request that
    reached a provider is charged whatever it returned; a request that never left this machine was
    never charged by anybody. Phase 2.1 could not tell those apart — a credential failure and a
    service-side validation refusal both produce zero tokens, zero latency and no request id — so
    eleven reservations totalling USD 0.22590990 were held against the cumulative ceiling for calls
    no provider ever saw.

    IT DEFAULTS TO `True`, AND THE ASYMMETRY IS THE REASON. Assuming a request was sent when it was
    not holds ceiling that could have been released: conservative, and wrong in the safe direction.
    Assuming it was not sent when it was releases ceiling for money that was actually spent, which
    is how a run walks past its authorization. An adapter that does not know says so by saying
    nothing.
    """

    def __init__(
        self,
        message: str,
        *,
        retryable: bool,
        provider: str,
        transport_attempted: bool = True,
    ) -> None:
        self.retryable = retryable
        self.provider = provider
        self.transport_attempted = transport_attempted
        super().__init__(message)


class CredentialResolutionError(ProviderError):
    """Credentials could not be resolved, so nothing was ever sent.

    A SEPARATE TYPE RATHER THAN A FLAG ON A GENERIC ERROR, because the caller that releases a
    reservation has to be able to name the exact condition it is releasing for, and `except
    CredentialResolutionError` is a narrower claim than reading a boolean off anything that failed.

    It is never retryable. An expired federated session does not become valid by being asked twice,
    and Phase 2.1 measured eleven consecutive failures of exactly that kind inside four minutes.
    """

    def __init__(self, message: str, *, provider: str) -> None:
        super().__init__(message, retryable=False, provider=provider, transport_attempted=False)


class NativeToolUseProhibitedError(LlmGatewayError):
    """A caller attempted to pass native tool definitions to a provider.

    Native tool calling requires JSON Schema tool definitions and produces JSON tool arguments,
    both of which are prohibited at the model boundary. Deep Analysis uses the bounded YAML
    action protocol instead.
    """


class BudgetExceededError(LlmGatewayError):
    """The invocation would exceed a configured token or cost budget."""
