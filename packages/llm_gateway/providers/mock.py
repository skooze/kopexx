"""Deterministic mock provider for local development and tests.

Returns canned YAML so the full gateway path, including boundary validation, safe parsing, and
audit persistence, can be exercised without network access or spend.
"""

from __future__ import annotations

from ..token_counter import estimate_tokens
from .base import ModelProvider, ModelRequest, ModelResponse

# THE FIXTURE ASSERTS NO ARTIFACT CONTRACT. Its predecessor was a `footnote-summary-v1.0.0`
# document with a fixed taxonomy of topics, accounting policies and risk categories, which quietly
# made the mock the de facto response schema. No model has ever been invoked, so no response shape
# is known; inventing one here would put the withdrawn ontology back through the test suite. What
# this document has to be is a well-formed, unfenced YAML 1.2 mapping that exercises the boundary
# validator, the safe parser and the audit path — and nothing more.
DEFAULT_YAML_RESPONSE = """schema_version: "mock-response-v1"
response:
  text: A deterministic mock response produced without invoking a real model.
  note: Exercises the gateway path — boundary validation, safe parsing, audit — offline.
"""


class MockProvider(ModelProvider):
    """A provider that echoes a fixed YAML document."""

    name = "mock"

    def __init__(self, response_text: str = DEFAULT_YAML_RESPONSE) -> None:
        self._response_text = response_text
        self.invocations: list[ModelRequest] = []

    def invoke(self, request: ModelRequest) -> ModelResponse:
        self.invocations.append(request)
        return ModelResponse(
            text=self._response_text,
            input_tokens=estimate_tokens(request.system_text)
            + estimate_tokens(request.user_content),
            output_tokens=estimate_tokens(self._response_text),
            model_id=request.model_id,
            provider=self.name,
        )

    def count_tokens(self, text: str) -> int:
        return estimate_tokens(text)
