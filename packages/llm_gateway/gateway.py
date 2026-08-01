"""The single entry point for every model invocation in FinTek.

No application package, worker, route, or script may invoke a provider directly. This gateway
owns the ordered pipeline:

    typed domain object
      -> payload compiler        (produces model-visible content)
      -> boundary validator      (rejects prohibited serializations)
      -> budget guard            (refuses before spend, not after)
      -> provider adapter        (the only place a provider SDK is used)
      -> boundary validation of the response
      -> safe YAML parser        (when the task is structured)
      -> audit record            (exact request and response bodies preserved)

SECURITY-INVARIANT: the exact model-visible request and the exact model response are persisted
unmodified. They are never rewritten into another serialization and then presented as though
that were what the model produced.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from .boundary_validator import ContentFormat, enforce
from .cost_calculator import PricingRegistry, default_registry
from .errors import BudgetExceededError
from .payload_compiler import CompiledPayload, reject_native_tools
from .providers.base import ModelProvider, ModelRequest, ModelResponse
from .yaml_parser import parse_yaml


@dataclass(frozen=True)
class Budget:
    """Pre-flight limits enforced before a model is invoked."""

    max_input_tokens: int | None = None
    max_output_tokens: int | None = None
    max_cost_usd: float | None = None


@dataclass
class InvocationRecord:
    """The audit record for one model invocation.

    ``request_body`` and ``response_body`` hold the exact model-visible content. In production
    these are written to object storage and this record carries the URIs; in tests they are held
    inline. Either way the original serialization is preserved.
    """

    correlation_id: str
    model_id: str
    provider: str
    prompt_version: str
    request_format: str
    response_format: str
    request_body: str
    response_body: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    started_at: datetime
    finished_at: datetime
    status: str
    origin: str
    error: str | None = None
    request_uri: str | None = None
    response_uri: str | None = None

    @property
    def latency_seconds(self) -> float:
        return (self.finished_at - self.started_at).total_seconds()


@dataclass
class GatewayResult:
    """A completed invocation: the parsed value when structured, plus the audit record."""

    record: InvocationRecord
    parsed: Any | None = None
    raw_text: str = ""


class LlmGateway:
    """Mediates all model access."""

    def __init__(
        self,
        provider: ModelProvider,
        *,
        pricing: PricingRegistry | None = None,
        audit_sink: list[InvocationRecord] | None = None,
    ) -> None:
        self._provider = provider
        self._pricing = pricing or default_registry()
        self.audit: list[InvocationRecord] = audit_sink if audit_sink is not None else []

    def invoke(
        self,
        *,
        model_id: str,
        system_text: str,
        payload: CompiledPayload,
        prompt_version: str,
        expect_structured: bool = True,
        max_output_tokens: int = 4096,
        budget: Budget | None = None,
        tools: Any = None,
        correlation_id: str | None = None,
    ) -> GatewayResult:
        """Invoke a model through the full boundary-controlled pipeline."""
        reject_native_tools(tools)

        correlation = correlation_id or str(uuid.uuid4())
        origin = payload.origin

        # The system prompt is model-visible content and is validated on the same terms.
        enforce(system_text, ContentFormat.PLAIN_TEXT, origin=f"{origin}.system")
        enforce(payload.content, payload.content_format, origin=origin)

        estimated_input = payload.estimated_tokens + len(system_text) // 4
        self._check_budget(budget, estimated_input, max_output_tokens, model_id)

        started = datetime.now(UTC)
        request = ModelRequest(
            model_id=model_id,
            system_text=system_text,
            user_content=payload.content,
            user_content_format=payload.content_format,
            max_output_tokens=max_output_tokens,
        )
        response: ModelResponse = self._provider.invoke(request)
        finished = datetime.now(UTC)

        response_format = ContentFormat.YAML if expect_structured else ContentFormat.PLAIN_TEXT
        parsed: Any | None = None
        status = "SUCCEEDED"
        error: str | None = None

        try:
            enforce(response.text, response_format, origin=f"{origin}.response")
            if expect_structured:
                parsed = parse_yaml(response.text)
        except Exception as exc:  # recorded, then re-raised after the audit row exists
            status = "BOUNDARY_REJECTED"
            error = f"{type(exc).__name__}: {exc}"

        cost = self._pricing.cost_usd(model_id, response.input_tokens, response.output_tokens)
        record = InvocationRecord(
            correlation_id=correlation,
            model_id=model_id,
            provider=response.provider,
            prompt_version=prompt_version,
            request_format=payload.format_value,
            response_format=response_format.value,
            request_body=payload.content,
            response_body=response.text,
            input_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
            cost_usd=cost,
            started_at=started,
            finished_at=finished,
            status=status,
            origin=origin,
            error=error,
        )
        self.audit.append(record)

        if status != "SUCCEEDED":
            raise RuntimeError(f"model response rejected at the boundary: {error}")

        return GatewayResult(record=record, parsed=parsed, raw_text=response.text)

    def _check_budget(
        self, budget: Budget | None, input_tokens: int, output_tokens: int, model_id: str
    ) -> None:
        if budget is None:
            return
        if budget.max_input_tokens is not None and input_tokens > budget.max_input_tokens:
            raise BudgetExceededError(
                f"estimated input {input_tokens} exceeds budget {budget.max_input_tokens}"
            )
        if budget.max_output_tokens is not None and output_tokens > budget.max_output_tokens:
            raise BudgetExceededError(
                f"requested output {output_tokens} exceeds budget {budget.max_output_tokens}"
            )
        if budget.max_cost_usd is not None:
            projected = self._pricing.cost_usd(model_id, input_tokens, output_tokens)
            if projected > budget.max_cost_usd:
                raise BudgetExceededError(
                    f"projected cost {projected:.6f} exceeds budget {budget.max_cost_usd:.6f}"
                )
