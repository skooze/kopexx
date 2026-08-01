"""Deterministic mock provider for local development and tests.

Returns canned YAML so the full gateway path, including boundary validation, safe parsing, and
audit persistence, can be exercised without network access or spend.
"""

from __future__ import annotations

from ..token_counter import estimate_tokens
from .base import ModelProvider, ModelRequest, ModelResponse

DEFAULT_YAML_RESPONSE = """schema_version: "footnote-summary-v1.0.0"
footnote:
  id: "mock-footnote-0001"
  number: "1"
  title: Mock Footnote
summary:
  plain_language: A deterministic mock summary produced without invoking a real model.
  purpose: Exercises the gateway path in tests.
  classification: routine
  classification_reason: Fixture content is intentionally unremarkable.
financial_relationships: []
important_facts: []
period_changes: []
topics:
  - mock
accounting_policies: []
accounting_judgments: []
risks_and_obligations: []
deep_dive:
  recommended: false
  reasons: []
quality:
  confidence: 1.0
  requires_review: false
  ambiguous_items: []
  missing_information: []
source_coverage:
  blocks_supplied: 0
  blocks_referenced: 0
  tables_supplied: 0
  tables_referenced: 0
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
