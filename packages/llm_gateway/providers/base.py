"""Provider adapter interface.

SECURITY-INVARIANT: only modules in this directory may import a provider SDK. An architecture
test enforces that boto3 and Bedrock clients are not constructed anywhere else in the repository.

EXTENDED IN PHASE 2, FROM A REAL ADAPTER AND A REAL REQUEST. `docs/llm/model-abstraction.md` said
this interface had no representation for a preserved SEC artifact sent intact under the
original-source exception, that it would need one before the first real parsing run, and that its
shape would be designed against a real provider request rather than guessed in advance.
`OriginalSourceBlock` is that shape, and every field in it exists because a real Converse request
needed it: the decoded text a text block takes, the raw bytes an image block takes, the codec that
did the decoding, and the SHA-256 that admits the block by PROVENANCE rather than by syntax.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Final

from ..boundary_validator import ContentFormat

#: The two kinds of preserved content a provider block can carry.
MEDIA_TEXT: Final[str] = "text"
MEDIA_IMAGE: Final[str] = "image"


@dataclass(frozen=True)
class OriginalSourceBlock:
    """One preserved SEC artifact, sent to a model INTACT.

    ADMITTED BY PROVENANCE, NOT BY SYNTAX. rules.md section 3: an untouched original SEC artifact
    may be sent in whatever format SEC published — HTML, SGML, XML, inline XBRL, PDF, image, plain
    text — provided the bytes are identical to a preserved artifact whose SHA-256 is recorded and
    were not constructed by this system. `raw_bytes` and `sha256` are what make that CHECKABLE
    rather than asserted, and the gateway verifies it before anything reaches a provider.

    THE EXCEPTION IS ONE-DIRECTIONAL. No model RESPONSE may use it. A response is still exactly
    one unfenced YAML 1.2 document, or plain text, validated on the way back.

    `text` is the losslessly decoded content of a text block and `codec` names what decoded it, so
    the one permitted transformation is recorded rather than invisible. An image block carries no
    text at all: backend code never transcribes, describes or captions an image, because that
    would be backend code deciding what filing content means.
    """

    label: str
    sha256: str
    byte_count: int
    media_kind: str
    raw_bytes: bytes = field(repr=False)
    text: str | None = field(default=None, repr=False)
    codec: str | None = None
    image_format: str | None = None

    @property
    def is_image(self) -> bool:
        return self.media_kind == MEDIA_IMAGE


@dataclass(frozen=True)
class ModelRequest:
    """A provider-neutral model request.

    `user_content` is SYNTHETIC content and has already passed the boundary validator.
    `original_source` is PRESERVED content and deliberately has not: an SEC artifact is admitted
    by provenance, and running an inline-XBRL filing through a validator that rejects HTML would
    reject the filing for being a filing.
    """

    model_id: str
    system_text: str
    user_content: str
    user_content_format: ContentFormat
    max_output_tokens: int = 4096
    temperature: float = 0.0
    original_source: tuple[OriginalSourceBlock, ...] = ()
    region: str = ""


@dataclass(frozen=True)
class ModelResponse:
    """A provider-neutral model response.

    `reasoning_text` IS SEPARATE FROM `text`, AND THE SEPARATION IS LOAD-BEARING. Phase 1 measured
    a candidate that emits reasoning content before its answer on the Converse path: at an 8-token
    output cap the whole budget went to reasoning, the text block came back empty, and the stop
    reason was `max_tokens`. Folding the two together would make a well-formed response look
    empty; dropping the reasoning would make an exhausted budget look like a model with nothing to
    say. Both are recorded and both are preserved.

    `transport_request` and `transport_response` carry the provider's own envelope as it crossed
    the wire. That is TRANSPORT EVIDENCE. It goes to ignored evaluation storage and is never shown
    to another model as semantic input.
    """

    text: str
    input_tokens: int
    output_tokens: int
    model_id: str
    provider: str
    stop_reason: str = "end_turn"
    truncated: bool = False
    reasoning_text: str = ""
    provider_request_id: str | None = None
    latency_ms: int = 0
    region: str = ""
    transport_request: str = field(default="", repr=False)
    transport_response: str = field(default="", repr=False)


class ModelProvider(ABC):
    """Base class for every model provider adapter."""

    name: str = "base"

    @abstractmethod
    def invoke(self, request: ModelRequest) -> ModelResponse:
        """Invoke the model synchronously and return a normalized response."""

    def count_tokens(self, text: str) -> int | None:
        """Return an exact provider token count, or None when unavailable."""
        return None
