"""Compilation of typed domain objects into model-visible content.

This is the ONLY module permitted to produce model-visible request content. It builds from typed
inputs and never passes an internal serialization through to a model. The boundary validator is a
backstop that catches bypasses; this compiler is the primary control.

LLM-SERIALIZATION-INVARIANT: output is unmarked plain text or exactly one unfenced YAML 1.2
document. See rules.md section 3 and docs/llm/content-boundary.md.
"""

from __future__ import annotations

from dataclasses import dataclass, field
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


@dataclass
class TablePayload:
    """A footnote table prepared for model consumption.

    Tables are emitted as YAML with an explicit column list and row sequences, never as Markdown
    tables or HTML. The row-oriented form is used when it is more compact, which it usually is
    for dense financial tables; the record-oriented form is used for sparse tables.
    """

    table_id: str
    title: str
    unit: str
    columns: list[str]
    rows: list[list[Any]]

    def as_mapping(self) -> dict[str, Any]:
        record_cost = sum(
            len(str(c)) + len(str(v))
            for row in self.rows
            for c, v in zip(self.columns, row, strict=True)
        )
        row_cost = sum(len(str(v)) for row in self.rows for v in row) + sum(
            len(c) for c in self.columns
        )
        base: dict[str, Any] = {
            "id": self.table_id,
            "title": self.title,
            "unit": self.unit,
        }
        if row_cost <= record_cost:
            base["columns"] = list(self.columns)
            base["rows"] = [list(r) for r in self.rows]
        else:
            base["records"] = [dict(zip(self.columns, r, strict=True)) for r in self.rows]
        return base


@dataclass
class SourceBlockPayload:
    """One narrative, policy, or detail block belonging to a canonical footnote."""

    block_id: str
    block_type: str
    text: str

    def as_mapping(self) -> dict[str, Any]:
        return {"id": self.block_id, "type": self.block_type, "text": self.text}


@dataclass
class FootnoteSummaryRequest:
    """Everything the standard summarizer needs for one canonical footnote.

    Deliberately carries no raw HTML, no XBRL, and no JSON. The parsing pipeline has already
    normalized filing markup into prose and structured values before this point.
    """

    cik: str
    accession: str
    form: str
    period_end: str
    footnote_id: str
    footnote_number: str
    footnote_title: str
    source_blocks: list[SourceBlockPayload] = field(default_factory=list)
    tables: list[TablePayload] = field(default_factory=list)
    related_facts: list[dict[str, Any]] = field(default_factory=list)
    prior_period_summary: str | None = None
    prompt_version: str = "footnote-summary-v1.0.0"

    def as_mapping(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "request": {
                "task": "summarize_canonical_footnote",
                "prompt_version": self.prompt_version,
            },
            "filing": {
                "cik": self.cik,
                "accession": self.accession,
                "form": self.form,
                "period_end": self.period_end,
            },
            "footnote": {
                "id": self.footnote_id,
                "number": self.footnote_number,
                "title": self.footnote_title,
            },
            "source_blocks": [b.as_mapping() for b in self.source_blocks],
        }
        if self.tables:
            payload["tables"] = [t.as_mapping() for t in self.tables]
        if self.related_facts:
            payload["related_facts"] = self.related_facts
        if self.prior_period_summary:
            payload["prior_period_summary"] = self.prior_period_summary
        payload["instructions"] = {
            "summarize_every_supplied_source_block": True,
            "cite_material_claims": True,
            "outside_knowledge_allowed": False,
            "invent_values_allowed": False,
        }
        return payload


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


def compile_footnote_summary_request(request: FootnoteSummaryRequest) -> CompiledPayload:
    """Compile a canonical footnote into its model-visible YAML payload."""
    return compile_yaml(request.as_mapping(), origin="summarization.footnote_summary")


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
