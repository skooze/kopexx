"""The single entry point for every model invocation in FinTek.

No application package, worker, route, or script may invoke a provider directly. This gateway
owns the ordered pipeline:

    typed domain object
      -> payload compiler        (produces model-visible SYNTHETIC content)
      -> boundary validator      (rejects prohibited serializations)
      -> provenance check        (admits a preserved SEC artifact by its recorded SHA-256)
      -> budget guard            (refuses before spend, not after)
      -> provider adapter        (the only place a provider SDK is used)
      -> boundary validation of the response
      -> safe YAML parser        (when the task is structured)
      -> audit record            (exact request and response bodies preserved)

SECURITY-INVARIANT: the exact model-visible request and the exact model response are persisted
unmodified. They are never rewritten into another serialization and then presented as though
that were what the model produced.

TWO PHASE-2 EXTENSIONS, BOTH FORCED BY A REAL RUN.

    ORIGINAL SOURCE. A parsing request carries a preserved SEC artifact intact. It is admitted by
    PROVENANCE — its bytes must hash to the SHA-256 the source store recorded — and it deliberately
    does NOT go through the synthetic-content validator, which would reject an inline-XBRL filing
    for containing HTML. The provenance check is not weaker than the validator; it is a different
    and stronger question, because it asks whether these are the bytes SEC published rather than
    whether they look acceptable.

    A REJECTED RESPONSE IS EVIDENCE, NOT AN EXCEPTION. `strict_response=True` keeps the original
    behaviour: a model that returns JSON raises. Parser evaluation needs the other mode. That
    response was BOUGHT, it cannot be regenerated for free, and a person has to look at it to
    find out whether the prompt or the model is at fault. `strict_response=False` records the
    violation, returns the exact bytes, and returns no parsed value — the response is still
    refused, it is just refused visibly instead of thrown away.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from .boundary_validator import ContentFormat, enforce
from .cost_calculator import PricingRegistry, default_registry
from .errors import BoundaryViolationError, BudgetExceededError
from .payload_compiler import CompiledPayload, reject_native_tools
from .providers.base import ModelProvider, ModelRequest, ModelResponse, OriginalSourceBlock
from .token_counter import estimate_tokens
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

    ``cost_usd`` IS A DECIMAL. It used to be a float. Phase 1 established that a price is
    multiplied by token counts in the millions and ends up on a bill, and that `Decimal(0.00015)`
    is `0.000149999999999999993145` because that is what the binary double holds. The float made
    that error possible in the one record a reviewer reads.
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
    cost_usd: Decimal
    started_at: datetime
    finished_at: datetime
    status: str
    origin: str
    error: str | None = None
    request_uri: str | None = None
    response_uri: str | None = None
    reasoning_body: str = ""
    stop_reason: str = ""
    truncated: bool = False
    provider_request_id: str | None = None
    region: str = ""
    original_source_hashes: tuple[str, ...] = ()
    transport_request: str = field(default="", repr=False)
    transport_response: str = field(default="", repr=False)

    @property
    def latency_seconds(self) -> float:
        return (self.finished_at - self.started_at).total_seconds()


@dataclass
class GatewayResult:
    """A completed invocation: the parsed value when structured, plus the audit record."""

    record: InvocationRecord
    parsed: Any | None = None
    raw_text: str = ""
    boundary_violation: str | None = None


def verify_original_source(blocks: tuple[OriginalSourceBlock, ...], *, origin: str) -> None:
    """Admit preserved artifacts by provenance, or refuse them.

    THIS IS THE WHOLE BASIS ON WHICH AN SEC ARTIFACT IS ALLOWED PAST THE CONTENT BOUNDARY. Every
    block must hash to the SHA-256 the source store recorded and match its recorded byte count. A
    block that fails either check was constructed, altered or corrupted somewhere between the
    store and here — and the original-source exception explicitly does not cover anything this
    system built.

    A text block additionally has to round-trip: re-encoding the decoded text with the codec that
    produced it must reproduce the original bytes exactly. Decoding is the one transformation the
    intact-source rule permits, and it is permitted because it is lossless. Proving that per block
    is cheap; assuming it is how a filing reaches a model as mojibake.
    """
    # Imported here rather than at module scope: `packages/storage` is a leaf and this keeps the
    # gateway's import graph free of it for every caller that sends no original source.
    from packages.storage import sha256_bytes

    for block in blocks:
        if len(block.sha256) != 64 or not all(c in "0123456789abcdef" for c in block.sha256):
            raise BoundaryViolationError(
                origin=origin,
                declared_format="original_source",
                violations=["missing_provenance"],
                detail=(
                    f"{block.label!r} carries no recorded SHA-256; an original SEC artifact is "
                    "admitted by provenance, never by looking like one"
                ),
            )
        if len(block.raw_bytes) != block.byte_count:
            raise BoundaryViolationError(
                origin=origin,
                declared_format="original_source",
                violations=["byte_count_mismatch"],
                detail=(
                    f"{block.label!r} is recorded as {block.byte_count} bytes and carries "
                    f"{len(block.raw_bytes)}"
                ),
            )
        if sha256_bytes(block.raw_bytes) != block.sha256:
            raise BoundaryViolationError(
                origin=origin,
                declared_format="original_source",
                violations=["provenance_mismatch"],
                detail=(
                    f"{block.label!r} does not hash to its recorded SHA-256, so these are not the "
                    "bytes SEC published and the original-source exception does not cover them"
                ),
            )
        if not block.is_image:
            if block.text is None or block.codec is None:
                raise BoundaryViolationError(
                    origin=origin,
                    declared_format="original_source",
                    violations=["undeclared_decoding"],
                    detail=f"{block.label!r} is a text block with no decoded text or no codec",
                )
            if block.text.encode(block.codec, errors="strict") != block.raw_bytes:
                raise BoundaryViolationError(
                    origin=origin,
                    declared_format="original_source",
                    violations=["lossy_decoding"],
                    detail=(
                        f"{block.label!r} does not round-trip through {block.codec!r}; decoding "
                        "is permitted only because it is lossless"
                    ),
                )


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
        original_source: tuple[OriginalSourceBlock, ...] = (),
        temperature: float = 0.0,
        region: str = "",
        cost: Callable[[int, int], Decimal] | None = None,
        strict_response: bool = True,
    ) -> GatewayResult:
        """Invoke a model through the full boundary-controlled pipeline."""
        reject_native_tools(tools)

        correlation = correlation_id or str(uuid.uuid4())
        origin = payload.origin

        # The system prompt is model-visible SYNTHETIC content and is validated on those terms.
        enforce(system_text, ContentFormat.PLAIN_TEXT, origin=f"{origin}.system")
        enforce(payload.content, payload.content_format, origin=origin)
        verify_original_source(original_source, origin=f"{origin}.source")

        # ONE RATIO, NOT TWO. This used to add `len(system_text) // 4` while the payload's own
        # estimate came from token_counter's 3.8 characters per token, so the single pre-spend
        # budget guard mixed two different unverified ratios and under-counted the system prompt.
        # Under-counting is the unsafe direction for a guard that runs BEFORE the money is spent.
        estimated_input = (
            payload.estimated_tokens
            + estimate_tokens(system_text)
            + sum(estimate_tokens(b.text or "") for b in original_source if not b.is_image)
        )
        self._check_budget(budget, estimated_input, max_output_tokens, model_id)

        started = datetime.now(UTC)
        request = ModelRequest(
            model_id=model_id,
            system_text=system_text,
            user_content=payload.content,
            user_content_format=payload.content_format,
            max_output_tokens=max_output_tokens,
            temperature=temperature,
            original_source=original_source,
            region=region,
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

        # THE ARITHMETIC HAPPENS IN EXACTLY ONE PLACE. A caller holding the reviewed price from
        # the capability snapshot passes `cost`, a function of the MEASURED token counts, and the
        # Decimal it returns is what `packages/model_catalog.PriceInputs.cost` computed. The
        # registry remains the fallback for the mock provider and for callers with no snapshot,
        # and it is never consulted for a model whose real price is known — two homes for one
        # number is how they drift, and this one ends up on a bill.
        if cost is None:
            measured_cost = Decimal(
                str(self._pricing.cost_usd(model_id, response.input_tokens, response.output_tokens))
            )
        else:
            measured_cost = cost(response.input_tokens, response.output_tokens)

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
            cost_usd=measured_cost,
            started_at=started,
            finished_at=finished,
            status=status,
            origin=origin,
            error=error,
            reasoning_body=response.reasoning_text,
            stop_reason=response.stop_reason,
            truncated=response.truncated,
            provider_request_id=response.provider_request_id,
            region=response.region or region,
            original_source_hashes=tuple(b.sha256 for b in original_source),
            transport_request=response.transport_request,
            transport_response=response.transport_response,
        )
        self.audit.append(record)

        if status != "SUCCEEDED" and strict_response:
            raise RuntimeError(f"model response rejected at the boundary: {error}")

        return GatewayResult(
            record=record,
            parsed=parsed,
            raw_text=response.text,
            boundary_violation=error,
        )

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
