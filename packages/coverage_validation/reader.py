"""A PROVISIONAL, ELASTIC reader for a parsed artifact. It requires almost nothing.

THE FINAL CONTRACT IS NOT KNOWN AND MAY NOT BE INVENTED HERE. roadmap.md 2c and rules.md section
21 rule 2 are explicit: the response format stays provisional until real models are tested, and
the real contract is DERIVED from what they return. This reader therefore exposes a few generic
fields and hands back everything else untouched.

WHAT IT WILL NEVER DO.

    It does not require a node to carry a known `type`. `RISK_FACTORS`, `MD&A`, `FOOTNOTE`,
    `STATEMENT` and `CERTIFICATION` are labels a filing or a model may produce; they are not a
    backend ontology and there is no enum of them anywhere in this package.

    It does not drop an unrecognised key. Every key it does not know about survives in `extra`,
    because the whole point of the first experiments is to find out what models actually emit, and
    a reader that silently discarded the surprising half would guarantee the surprise was never
    seen.

    It does not rename, merge, split or reconcile anything. Deciding that two differently named
    sections are the same section is later evaluation work done by a person, not a normalisation
    done in code.

THE EXACT RESPONSE REMAINS AUTHORITATIVE. This reader produces a convenience view for the review
UI and for coverage counting. The bytes the model returned are preserved separately and are what a
reviewer is shown when the two could disagree.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from packages.llm_gateway import parse_yaml

from .errors import ResponseUnreadableError

#: The provisional minimum envelope. Its ABSENCE is recorded as a finding, never as a refusal:
#: a response that omits a key is evidence about the prompt or the model, and throwing it away
#: would destroy the measurement.
PROVISIONAL_ENVELOPE_KEYS: tuple[str, ...] = (
    "artifact",
    "document",
    "nodes",
    "unresolved",
    "metadata",
)

_KNOWN_NODE_KEYS = frozenset(
    {
        "id",
        "order",
        "type",
        "title",
        "parent_id",
        "content",
        "tables",
        "source",
        "confidence",
        "ambiguity",
        "image",
    }
)


@dataclass(frozen=True)
class SourceReference:
    """One locator a model supplied. Resolution against the preserved bytes happens elsewhere."""

    filename: str
    quote: str
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ParsedNode:
    """One node exactly as the model chose to shape it.

    `type` and `title` are strings the model produced. They are displayed and counted; they are
    never validated against a vocabulary.
    """

    node_id: str
    order: int
    node_type: str
    title: str
    parent_id: str | None
    content: str
    tables: tuple[dict[str, Any], ...]
    references: tuple[SourceReference, ...]
    confidence: str | None
    ambiguity: str | None
    image_dependent: bool
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ParsedDocument:
    """The whole parsed artifact, read generically."""

    nodes: tuple[ParsedNode, ...]
    unresolved: tuple[dict[str, Any], ...]
    documents: tuple[dict[str, Any], ...]
    artifact: dict[str, Any]
    metadata: dict[str, Any]
    missing_envelope_keys: tuple[str, ...]
    raw: Any

    @property
    def node_count(self) -> int:
        return len(self.nodes)

    @property
    def reference_count(self) -> int:
        return sum(len(n.references) for n in self.nodes)

    @property
    def table_count(self) -> int:
        return sum(len(n.tables) for n in self.nodes)

    @property
    def image_dependent_count(self) -> int:
        return sum(1 for n in self.nodes if n.image_dependent)

    def types_used(self) -> dict[str, int]:
        """How often each model-chosen `type` appears. A census, never a vocabulary."""
        counts: dict[str, int] = {}
        for node in self.nodes:
            key = node.node_type or "(no type)"
            counts[key] = counts.get(key, 0) + 1
        return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0])))


def _as_mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _reference(raw: Any) -> SourceReference | None:
    if not isinstance(raw, dict):
        return None
    quote = raw.get("quote")
    filename = raw.get("filename")
    if quote is None and filename is None:
        return None
    return SourceReference(
        filename=str(filename or ""),
        quote=str(quote or ""),
        extra={k: v for k, v in raw.items() if k not in {"quote", "filename"}},
    )


def _node(raw: Any, fallback_order: int) -> ParsedNode | None:
    if not isinstance(raw, dict):
        return None
    order = raw.get("order")
    tables = tuple(t for t in _as_list(raw.get("tables")) if isinstance(t, dict))
    references = tuple(
        ref for ref in (_reference(r) for r in _as_list(raw.get("source"))) if ref is not None
    )
    return ParsedNode(
        node_id=str(raw.get("id") or f"node-{fallback_order}"),
        order=order if isinstance(order, int) and not isinstance(order, bool) else fallback_order,
        node_type=str(raw.get("type") or ""),
        title=str(raw.get("title") or ""),
        parent_id=str(raw["parent_id"]) if raw.get("parent_id") is not None else None,
        content=str(raw.get("content") or ""),
        tables=tables,
        references=references,
        confidence=str(raw["confidence"]) if raw.get("confidence") is not None else None,
        ambiguity=str(raw["ambiguity"]) if raw.get("ambiguity") is not None else None,
        image_dependent=bool(raw.get("image")),
        extra={k: v for k, v in raw.items() if k not in _KNOWN_NODE_KEYS},
    )


def read(response_text: str) -> ParsedDocument:
    """Read a parsed artifact from a model's exact response bytes.

    Raises only when the text is not one YAML document at all. Everything else — a missing
    envelope key, an empty node list, a node with no title — is a FINDING the validator records
    against a response that still gets reviewed.
    """
    try:
        document = parse_yaml(response_text)
    except Exception as error:
        raise ResponseUnreadableError(
            f"the response is not one YAML 1.2 document: {error}"
        ) from error

    if not isinstance(document, dict):
        raise ResponseUnreadableError(
            f"the response parsed to {type(document).__name__} rather than a mapping"
        )

    nodes = tuple(
        node
        for node in (_node(raw, index) for index, raw in enumerate(_as_list(document.get("nodes"))))
        if node is not None
    )
    return ParsedDocument(
        nodes=nodes,
        unresolved=tuple(u for u in _as_list(document.get("unresolved")) if isinstance(u, dict)),
        documents=tuple(d for d in _as_list(document.get("document")) if isinstance(d, dict)),
        artifact=_as_mapping(document.get("artifact")),
        metadata=_as_mapping(document.get("metadata")),
        missing_envelope_keys=tuple(k for k in PROVISIONAL_ENVELOPE_KEYS if k not in document),
        raw=document,
    )
