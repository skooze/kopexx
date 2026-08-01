"""Provider adapter interface.

SECURITY-INVARIANT: only modules in this directory may import a provider SDK. An architecture
test enforces that boto3 and Bedrock clients are not constructed anywhere else in the repository.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from ..boundary_validator import ContentFormat


@dataclass(frozen=True)
class ModelRequest:
    """A provider-neutral model request carrying already-validated model-visible content."""

    model_id: str
    system_text: str
    user_content: str
    user_content_format: ContentFormat
    max_output_tokens: int = 4096


@dataclass(frozen=True)
class ModelResponse:
    """A provider-neutral model response."""

    text: str
    input_tokens: int
    output_tokens: int
    model_id: str
    provider: str
    stop_reason: str = "end_turn"
    truncated: bool = False


class ModelProvider(ABC):
    """Base class for every model provider adapter."""

    name: str = "base"

    @abstractmethod
    def invoke(self, request: ModelRequest) -> ModelResponse:
        """Invoke the model synchronously and return a normalized response."""

    def count_tokens(self, text: str) -> int | None:
        """Return an exact provider token count, or None when unavailable."""
        return None
