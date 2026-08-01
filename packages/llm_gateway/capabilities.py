"""Provider-neutral model capability description.

Application code selects a model by required capability, never by hard-coded provider model
identifier. This keeps a Bedrock model id out of every call site and makes model swaps a
configuration change.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelCapabilities:
    """What a model can do, expressed without reference to any provider SDK."""

    model_id: str
    provider: str
    max_input_tokens: int
    max_output_tokens: int
    supports_batch: bool = False
    supports_flex: bool = False
    supports_reasoning_effort: bool = False

    # Deliberately absent: supports_structured_output and supports_native_tools.
    # Both describe provider features that require JSON at the model boundary and are therefore
    # unusable in this system regardless of whether a provider offers them. See ADR-0013.

    def accepts_input(self, tokens: int) -> bool:
        return tokens <= self.max_input_tokens
