"""Cost calculation for model invocations.

Prices are configuration, never constants embedded in application code. A model whose price is
not registered raises rather than silently costing an unknown amount.

IMPLEMENTATION STATUS: PLANNED for real provider rates. The registry below contains only the
mock provider used in tests. Real rates are loaded from configuration once the Bedrock catalog
has been verified in-region, which is a blocking gate before Phase 6. See
docs/llm/cost-model.md.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelPricing:
    """Per-million-token prices for one model in one tier."""

    model_id: str
    input_per_million_usd: float
    output_per_million_usd: float
    batch_discount: float = 0.0

    def cost_usd(self, input_tokens: int, output_tokens: int, *, batch: bool = False) -> float:
        """Return the cost of one invocation in US dollars."""
        gross = (
            input_tokens / 1_000_000 * self.input_per_million_usd
            + output_tokens / 1_000_000 * self.output_per_million_usd
        )
        return gross * (1.0 - self.batch_discount) if batch else gross


class PricingRegistry:
    """Registry of model prices. Unknown models raise rather than defaulting to zero."""

    def __init__(self) -> None:
        self._pricing: dict[str, ModelPricing] = {}

    def register(self, pricing: ModelPricing) -> None:
        self._pricing[pricing.model_id] = pricing

    def get(self, model_id: str) -> ModelPricing:
        if model_id not in self._pricing:
            raise KeyError(
                f"no pricing registered for model {model_id!r}; "
                "register a ModelPricing before invoking it so cost is never unknown"
            )
        return self._pricing[model_id]

    def cost_usd(
        self, model_id: str, input_tokens: int, output_tokens: int, *, batch: bool = False
    ) -> float:
        return self.get(model_id).cost_usd(input_tokens, output_tokens, batch=batch)


def default_registry() -> PricingRegistry:
    """Return a registry containing only the zero-cost mock model used in tests."""
    registry = PricingRegistry()
    registry.register(
        ModelPricing(
            model_id="mock-model-v1", input_per_million_usd=0.0, output_per_million_usd=0.0
        )
    )
    return registry
