"""Compilation of synthetic content into model-visible request content.

This is the ONLY module permitted to produce model-visible SYNTHETIC request content. It never
passes an internal serialization through to a model. The boundary validator is a backstop that
catches bypasses; this compiler is the primary control.

LLM-SERIALIZATION-INVARIANT: output is unmarked plain text or exactly one unfenced YAML 1.2
document. See rules.md section 3 and docs/llm/content-boundary.md. The ORIGINAL-SOURCE EXCEPTION is
handled elsewhere: a preserved SEC artifact is admitted by provenance and is sent intact in the
syntax SEC published, never rewritten into YAML and never routed through this compiler.

DELIBERATELY FORMAT-ONLY, NOT REQUEST-SHAPED. This module used to carry `FootnoteSummaryRequest`,
`SourceBlockPayload` and `TablePayload` — a request contract built around canonical footnotes,
which was the deterministic parser's output shape. That parser is deleted and no model has ever
been invoked, so no request or response contract is known. Compiling an arbitrary mapping is
everything the boundary needs and everything that can honestly be asserted today. The real
contracts are derived from observed model behaviour in the parser-experiment stage.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .boundary_validator import ContentFormat, enforce
from .errors import NativeToolUseProhibitedError
from .token_counter import estimate_tokens
from .yaml_serializer import to_yaml


@dataclass(frozen=True)
class CompiledPayload:
    """Model-visible content plus the metadata needed for audit and budgeting."""

    content: str
    content_format: ContentFormat
    estimated_tokens: int
    origin: str

    @property
    def format_value(self) -> str:
        return self.content_format.value


def compile_yaml(payload: dict[str, Any], *, origin: str) -> CompiledPayload:
    """Compile a mapping into a validated YAML model payload."""
    content = to_yaml(payload)
    enforce(content, ContentFormat.YAML, origin=origin)
    return CompiledPayload(
        content=content,
        content_format=ContentFormat.YAML,
        estimated_tokens=estimate_tokens(content),
        origin=origin,
    )


def compile_plain_text(text: str, *, origin: str) -> CompiledPayload:
    """Compile normalized prose into a validated plain-text model payload."""
    normalized = _normalize_prose(text)
    enforce(normalized, ContentFormat.PLAIN_TEXT, origin=origin)
    return CompiledPayload(
        content=normalized,
        content_format=ContentFormat.PLAIN_TEXT,
        estimated_tokens=estimate_tokens(normalized),
        origin=origin,
    )


def reject_native_tools(tools: Any) -> None:
    """Refuse any attempt to pass native tool definitions to a provider.

    Native tool calling requires JSON Schema definitions and yields JSON arguments, both
    prohibited at the boundary. Deep Analysis uses the bounded YAML action protocol instead.
    """
    if tools:
        raise NativeToolUseProhibitedError(
            "native tool calling is prohibited at the model boundary; "
            "use the YAML action protocol in docs/deep-analysis/action-protocol.yaml"
        )


def _normalize_prose(text: str) -> str:
    """Collapse whitespace runs while preserving paragraph boundaries."""
    if not text:
        return ""
    paragraphs = [
        " ".join(part.split())
        for part in text.replace("\r\n", "\n").replace("\r", "\n").split("\n\n")
    ]
    return "\n\n".join(p for p in paragraphs if p)
