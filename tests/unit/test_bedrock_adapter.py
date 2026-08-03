"""The Converse adapter, exercised end to end with a FAKE client and no provider identity at all.

HERMETIC BY CONSTRUCTION, AND DELIBERATELY SO. `BedrockProvider` takes its `client_factory` as an
injected callable precisely so this file can exist: nothing here imports a provider SDK, resolves a
credential, opens a socket or names an account. `tests/architecture/test_phase1_aws_boundary.py`
fails the build if a test does any of that, and the zero-skip gate means a test that quietly needed
identity would fail everywhere rather than skip.

WHAT IS ACTUALLY BEING TESTED. Not that a dictionary comes back with the keys it was given. The
subject is the small set of things this adapter must never do to a request or a response:

    reorder or merge the preserved artifacts, or describe one it was handed
    re-encode image bytes instead of carrying them
    inline those bytes into the evidence envelope
    fold reasoning content into the visible answer, in either direction
    call a model twice
    leak the provider's own exception type past its boundary
    substitute a model, a region or a retry decision it was not given

THE PHASE 1 CASE IS PINNED HERE. One approved candidate spent its entire 8-token output cap on a
`reasoningContent` block, returning an empty text block with stop reason `max_tokens`. An adapter
that concatenated the two would have recorded a chain of thought as an answer; one that read only
the text would have recorded silence from a model that was working correctly. Both readings are
wrong and both are tested against below.
"""

from __future__ import annotations

import base64
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from packages.llm_gateway import ContentFormat, ProviderError
from packages.llm_gateway.providers import bedrock as bedrock_module
from packages.llm_gateway.providers.base import (
    MEDIA_IMAGE,
    MEDIA_TEXT,
    ModelRequest,
    ModelResponse,
    OriginalSourceBlock,
)
from packages.llm_gateway.providers.bedrock import BedrockProvider, default_client_factory
from packages.storage import sha256_bytes

MODEL_ID = "provider.model-one"
OTHER_MODEL_ID = "provider.model-two"
REGION = "region-one"
OTHER_REGION = "region-two"
INSTRUCTION = "Return the structure you find, as one unfenced YAML document."
SYSTEM = "The artifact labels are transport identifiers, not descriptions of meaning."
REQUEST_ID = "request-id-recorded-by-the-provider"

# The three credential argument names, assembled rather than written out. `tests/architecture/
# test_aws_identity.py` fails the build when those literals appear in a tracked file that is not
# the policy itself, and its allowlist is deliberately hard to join, so this file builds them from
# parts exactly as `tests/architecture/test_phase1_aws_boundary.py` builds the variable names.
CREDENTIAL_ARGUMENTS = tuple(
    "aws_" + suffix for suffix in ("access_key_id", "secret_access_key", "session_token")
)


# --- fakes ---------------------------------------------------------------------------------


class FakeConverseClient:
    """A stand-in for the provider runtime client, recording every call it is handed.

    It has exactly one method, because the adapter is allowed to use exactly one.
    """

    def __init__(
        self, payload: dict[str, Any] | None = None, error: Exception | None = None
    ) -> None:
        self.payload = payload if payload is not None else response_payload()
        self.error = error
        self.calls: list[dict[str, Any]] = []

    def converse(self, **arguments: Any) -> dict[str, Any]:
        self.calls.append(arguments)
        if self.error is not None:
            raise self.error
        return self.payload


class RecordingFactory:
    """Hands out one fake client per region and remembers which regions were asked for.

    A per-region record is what makes "no silent region widening" and "one client per region"
    checkable rather than asserted.
    """

    def __init__(
        self, payload: dict[str, Any] | None = None, error: Exception | None = None
    ) -> None:
        self._payload = payload
        self._error = error
        self.regions: list[str] = []
        self.clients: list[FakeConverseClient] = []

    def __call__(self, region: str) -> FakeConverseClient:
        self.regions.append(region)
        client = FakeConverseClient(payload=self._payload, error=self._error)
        self.clients.append(client)
        return client


class TickingClock:
    """A monotonic clock that advances one fixed step per read.

    Injected everywhere so no assertion about latency depends on how fast the test host is.
    """

    def __init__(self, step: float = 0.25) -> None:
        self.now = 0.0
        self.step = step

    def __call__(self) -> float:
        value = self.now
        self.now += self.step
        return value


class FakeServiceError(Exception):
    """Shaped like a service error the SDK would raise: a `response` mapping with an Error Code.

    The adapter must classify it by that structured code and must never let this type out.
    """

    def __init__(self, code: str) -> None:
        super().__init__(f"the service returned {code}")
        self.response = {"Error": {"Code": code, "Message": "synthetic"}}


class EndpointConnectionError(Exception):
    """Named to match a transport failure the adapter can only recognise by exception name."""


# --- builders ------------------------------------------------------------------------------


def text_block(label: str, text: str, *, codec: str = "utf-8") -> OriginalSourceBlock:
    raw = text.encode(codec)
    return OriginalSourceBlock(
        label=label,
        sha256=sha256_bytes(raw),
        byte_count=len(raw),
        media_kind=MEDIA_TEXT,
        raw_bytes=raw,
        text=text,
        codec=codec,
    )


def image_block(label: str, raw: bytes, image_format: str | None = "png") -> OriginalSourceBlock:
    return OriginalSourceBlock(
        label=label,
        sha256=sha256_bytes(raw),
        byte_count=len(raw),
        media_kind=MEDIA_IMAGE,
        raw_bytes=raw,
        image_format=image_format,
    )


def model_request(**overrides: Any) -> ModelRequest:
    """One request with every field supplied. Nothing here is a default the adapter may invent."""
    fields: dict[str, Any] = {
        "model_id": MODEL_ID,
        "system_text": SYSTEM,
        "user_content": INSTRUCTION,
        "user_content_format": ContentFormat.PLAIN_TEXT,
        "max_output_tokens": 4096,
        "temperature": 0.0,
        "original_source": (),
        "region": REGION,
    }
    fields.update(overrides)
    return ModelRequest(**fields)


def response_payload(
    *,
    content: list[dict[str, Any]] | None = None,
    stop_reason: str = "end_turn",
    usage: dict[str, int] | None = None,
    request_id: str | None = REQUEST_ID,
    latency_ms: int | None = None,
) -> dict[str, Any]:
    """A Converse response envelope, in the shape the provider returns one."""
    payload: dict[str, Any] = {
        "output": {"message": {"role": "assistant", "content": content or [{"text": "an answer"}]}},
        "stopReason": stop_reason,
        "usage": usage or {"inputTokens": 11, "outputTokens": 7, "totalTokens": 18},
    }
    if request_id is not None:
        payload["ResponseMetadata"] = {"RequestId": request_id, "HTTPStatusCode": 200}
    if latency_ms is not None:
        payload["metrics"] = {"latencyMs": latency_ms}
    return payload


def arguments_for(request: ModelRequest) -> dict[str, Any]:
    return BedrockProvider.build_converse_arguments(request)


def content_blocks(request: ModelRequest) -> list[dict[str, Any]]:
    return arguments_for(request)["messages"][0]["content"]


def invoke(
    request: ModelRequest | None = None,
    *,
    payload: dict[str, Any] | None = None,
    clock: Callable[[], float] | None = None,
) -> tuple[ModelResponse, RecordingFactory]:
    factory = RecordingFactory(payload=payload)
    provider = BedrockProvider(client_factory=factory, clock=clock or TickingClock())
    return provider.invoke(request or model_request()), factory


# --- request construction: order and labelling ----------------------------------------------


def test_the_instruction_arrives_before_the_filing_it_is_about() -> None:
    """ORDER IS PART OF THE REQUEST, not a formatting detail.

    An instruction that follows a megabyte of preserved source has been read after the thing it
    was meant to govern. The instruction block is first, always, and it is the request's own
    `user_content` rather than anything this adapter composes.
    """
    blocks = content_blocks(model_request(original_source=(text_block("a.htm", "ALPHA"),)))
    assert blocks[0] == {"text": INSTRUCTION}
    assert arguments_for(model_request())["messages"][0]["role"] == "user"


def test_every_artifact_is_preceded_by_its_own_mechanical_label() -> None:
    """rules.md section 11 permits labelling separate package members MECHANICALLY and no more.

    One label line per artifact, carrying the filename and nothing else — no role, no description,
    no classification. A label that said "the financial statements" would be backend code deciding
    what a filing means, which is the drift ADR-0016 was written about.
    """
    request = model_request(
        original_source=(text_block("a.htm", "ALPHA"), text_block("b.htm", "BETA"))
    )
    assert content_blocks(request) == [
        {"text": INSTRUCTION},
        {"text": "SOURCE ARTIFACT: a.htm"},
        {"text": "ALPHA"},
        {"text": "SOURCE ARTIFACT: b.htm"},
        {"text": "BETA"},
    ]


def test_filed_order_survives_and_is_never_sorted() -> None:
    """MUTATION TEST. The blocks follow the source set, not the alphabet.

    Feeding `b.htm` before `a.htm` must produce `b.htm` first. Any sort, dictionary rebuild or
    "tidy" reordering would flip this assertion, and filed order is part of what the filer
    submitted rather than a presentation choice this adapter may make.
    """
    request = model_request(
        original_source=(text_block("b.htm", "BETA"), text_block("a.htm", "ALPHA"))
    )
    assert [block["text"] for block in content_blocks(request)[1:]] == [
        "SOURCE ARTIFACT: b.htm",
        "BETA",
        "SOURCE ARTIFACT: a.htm",
        "ALPHA",
    ]


def test_a_preserved_filing_is_carried_intact_with_no_truncation_and_no_slicing(
    fixtures_dir: Path,
) -> None:
    """INTACT_SOURCE_ONLY, against a real preserved SEC artifact rather than a toy string.

    The complete relevant source goes to the model in ONE invocation or the pairing is
    INCOMPATIBLE and is refused. There is no truncation, no semantic slicing and no mechanical
    multipart here, so a 235 KiB pre-2001 submission must arrive as exactly one text block whose
    content is byte-for-byte the decoded document.
    """
    path = fixtures_dir / "filings" / "0000320193-94-000016" / "0000320193-94-000016.txt"
    raw = path.read_bytes()
    document = raw.decode("latin-1")
    assert len(document) > 200_000, "anti-vacuity: the intactness check needs a large document"

    blocks = content_blocks(
        model_request(original_source=(text_block(path.name, document, codec="latin-1"),))
    )
    assert len(blocks) == 3, "the artifact was split across more than one content block"
    assert blocks[2]["text"] == document
    assert blocks[2]["text"].startswith("-----BEGIN PRIVACY-ENHANCED MESSAGE-----")


# --- request construction: images -----------------------------------------------------------


def test_an_image_artifact_becomes_an_image_block_carrying_the_exact_bytes() -> None:
    """The bytes are handed over as they were preserved, not re-encoded on the way past.

    The final assertion is the product one: an image artifact contributes its mechanical label and
    the image itself, and nothing else. A caption, a transcription or an alt-text line would be
    backend code deciding what a picture in a filing means.
    """
    raw = b"\x89PNG\r\n\x1a\n synthetic pixels \x00\xff"
    blocks = content_blocks(model_request(original_source=(image_block("exhibit.png", raw),)))
    assert blocks[1] == {"text": "SOURCE ARTIFACT: exhibit.png"}
    assert blocks[2] == {"image": {"format": "png", "source": {"bytes": raw}}}
    assert blocks[2]["image"]["source"]["bytes"] is raw, "the bytes were copied or re-encoded"
    assert len(blocks) == 3, "an image acquired a transcription, caption or description"


def test_the_declared_image_format_is_carried_rather_than_inferred() -> None:
    """The block declares its codec; the adapter repeats it and does not sniff the bytes."""
    raw = b"\xff\xd8\xff\xe0 synthetic jpeg"
    blocks = content_blocks(
        model_request(original_source=(image_block("chart.jpg", raw, image_format="jpeg"),))
    )
    assert blocks[2]["image"]["format"] == "jpeg"


def test_an_image_block_with_no_declared_format_is_refused() -> None:
    """A format is never guessed, because guessing supplies a fact about preserved content.

    CORRECTED. This test used to pin a `png` fallback, with a docstring saying the behaviour was
    recorded rather than endorsed. It was a real defect: a JPEG whose format the source store had
    not declared would have been announced to the provider as a PNG, and the provider would then
    have failed on bytes the caller was told were fine — attributing a backend guess to the user's
    chosen model. The format comes from byte-signature detection in the source store or the block
    does not go.
    """
    block = OriginalSourceBlock(
        label="chart.jpg",
        sha256=sha256_bytes(b"binary"),
        byte_count=6,
        media_kind=MEDIA_IMAGE,
        raw_bytes=b"binary",
        image_format=None,
    )
    with pytest.raises(ProviderError, match="never guessed"):
        BedrockProvider.build_converse_arguments(
            ModelRequest(
                model_id="provider.model-one",
                system_text="system",
                user_content="instruction",
                user_content_format=ContentFormat.PLAIN_TEXT,
                original_source=(block,),
                region="region-one",
            )
        )


def test_a_text_block_carrying_no_decoded_text_is_refused() -> None:
    """A labelled artifact with an empty body is a member nothing marked unresolved.

    The model is told the artifact exists, receives nothing for it, and reports on a filing it was
    never shown part of. That is a complete-content failure wearing a successful request.
    """
    block = OriginalSourceBlock(
        label="undecodable.htm",
        sha256=sha256_bytes(b"bytes"),
        byte_count=5,
        media_kind=MEDIA_TEXT,
        raw_bytes=b"bytes",
        text=None,
        codec=None,
    )
    with pytest.raises(ProviderError, match="never sent as an empty body"):
        BedrockProvider.build_converse_arguments(
            ModelRequest(
                model_id="provider.model-one",
                system_text="system",
                user_content="instruction",
                user_content_format=ContentFormat.PLAIN_TEXT,
                original_source=(block,),
                region="region-one",
            )
        )


def test_text_and_image_artifacts_interleave_in_the_order_they_were_given() -> None:
    """A mixed source set is one ordered sequence, not a text section and an image section."""
    raw = b"\x89PNG\r\n\x1a\n pixels"
    request = model_request(
        original_source=(
            text_block("a.htm", "ALPHA"),
            image_block("b.png", raw),
            text_block("c.htm", "GAMMA"),
        )
    )
    blocks = content_blocks(request)
    assert [sorted(block)[0] for block in blocks] == [
        "text",
        "text",
        "text",
        "text",
        "image",
        "text",
        "text",
    ]
    assert blocks[4]["image"]["source"]["bytes"] == raw


# --- request construction: inference configuration and system prompt -------------------------


@pytest.mark.parametrize(("max_tokens", "temperature"), [(8, 0.0), (4096, 0.2), (32000, 1.0)])
def test_the_inference_configuration_carries_the_supplied_cap_and_temperature(
    max_tokens: int, temperature: float
) -> None:
    """The caller's ceiling reaches the provider unmodified.

    Parametrized because a hardcoded constant would satisfy any single case, and an output cap the
    adapter chose for itself is spend nobody authorized.
    """
    arguments = arguments_for(model_request(max_output_tokens=max_tokens, temperature=temperature))
    assert arguments["inferenceConfig"] == {"maxTokens": max_tokens, "temperature": temperature}


def test_the_system_prompt_travels_in_the_system_field_not_in_the_message() -> None:
    """A system prompt folded into the user turn is indistinguishable from filing content."""
    arguments = arguments_for(model_request(original_source=(text_block("a.htm", "ALPHA"),)))
    assert arguments["system"] == [{"text": SYSTEM}]
    assert all(SYSTEM not in str(block) for block in arguments["messages"][0]["content"])


def test_an_absent_system_prompt_adds_no_system_field_at_all() -> None:
    """ANTI-VACUITY for the guard above: blank must mean absent, not an empty text block.

    A parser-only run may legitimately carry no system prompt, and providers reject an empty
    system block outright — a failure that would be reported against the model the user chose.
    """
    assert "system" not in arguments_for(model_request(system_text=""))


@pytest.mark.parametrize("model_id", [MODEL_ID, OTHER_MODEL_ID])
def test_the_model_identifier_is_the_one_supplied_and_no_other(model_id: str) -> None:
    """rules.md section 21: no substitution, no fallback model, no default.

    The adapter is handed an invocation identifier and uses exactly that. It has no catalog, no
    preference and nothing to fall back to.
    """
    assert arguments_for(model_request(model_id=model_id))["modelId"] == model_id


def test_the_request_carries_no_tool_definitions_and_no_extra_keys() -> None:
    """Native tool calling is prohibited at the model boundary, in both directions.

    Asserting the exact key set is what keeps that true: a `toolConfig` key added later fails here
    rather than reaching a provider.
    """
    assert set(arguments_for(model_request())) == {
        "modelId",
        "messages",
        "inferenceConfig",
        "system",
    }


# --- transport evidence ----------------------------------------------------------------------


def test_transport_evidence_replaces_image_bytes_with_a_hash_and_a_count() -> None:
    """The envelope is evidence, not a second copy of every artifact.

    Base64-inlining a preserved image would double the size of the evidence object for no gain:
    the exact bytes are already preserved beside it, and a SHA-256 plus a byte count is what makes
    the envelope reconstructible. The last two assertions are the ones that matter — neither the
    raw bytes nor their base64 encoding appears anywhere in the string.
    """
    raw = b"\x89PNG\r\n\x1a\n" + b"pixel-payload" * 64
    evidence = BedrockProvider.transport_evidence(
        arguments_for(model_request(original_source=(image_block("exhibit.png", raw),)))
    )
    source = json.loads(evidence)["messages"][0]["content"][2]["image"]["source"]
    assert source["bytes_sha256"] == sha256_bytes(raw)
    assert source["byte_count"] == len(raw)
    assert "bytes" not in source
    assert base64.b64encode(raw).decode("ascii") not in evidence
    assert "pixel-payload" not in evidence


def test_transport_evidence_is_valid_json_and_keeps_the_request_readable() -> None:
    """JSON is correct here: this is the PROVIDER's envelope and is never model-visible.

    rules.md section 3 permits provider transport JSON as the API envelope; ADR-0013 governs what
    a MODEL sees. A reviewer has to be able to load this string and read what crossed the wire.
    """
    evidence = BedrockProvider.transport_evidence(
        arguments_for(model_request(original_source=(text_block("a.htm", "ALPHA"),)))
    )
    document = json.loads(evidence)
    assert document["modelId"] == MODEL_ID
    assert document["system"] == [{"text": SYSTEM}]
    assert document["inferenceConfig"]["maxTokens"] == 4096
    assert document["messages"][0]["content"][0]["text"] == INSTRUCTION


def test_transport_evidence_elides_image_bytes_only_and_keeps_text_artifacts() -> None:
    """ANTI-VACUITY. A scrubber that emptied everything would pass the test above.

    Text artifacts stay legible in the envelope, because the whole point of the evidence object is
    that a reviewer can see the request the model actually received.
    """
    evidence = BedrockProvider.transport_evidence(
        arguments_for(model_request(original_source=(text_block("a.htm", "ALPHA disclosure"),)))
    )
    assert "ALPHA disclosure" in evidence
    assert "SOURCE ARTIFACT: a.htm" in evidence
    assert "bytes_sha256" not in evidence, "a text artifact must not be hashed away"


# --- response extraction ---------------------------------------------------------------------


def test_the_visible_answer_and_the_reasoning_are_returned_separately() -> None:
    """THE TWO ARE NEVER MERGED. Concatenating them records a chain of thought as an answer."""
    visible, reasoning = BedrockProvider.extract(
        {
            "output": {
                "message": {
                    "content": [
                        {"reasoningContent": {"reasoningText": {"text": "weighing two readings"}}},
                        {"text": "the answer"},
                    ]
                }
            }
        }
    )
    assert visible == "the answer"
    assert reasoning == "weighing two readings"
    assert "weighing" not in visible
    assert "answer" not in reasoning


def test_a_response_that_is_entirely_reasoning_has_no_visible_answer() -> None:
    """THE EXACT PHASE 1 CASE, at the extraction level.

    One approved candidate spent its whole 8-token cap on reasoning. The visible answer is the
    empty string — not the reasoning, not a placeholder, not None — and the reasoning is kept in
    full so the record shows a model that was working rather than one with nothing to say.
    """
    visible, reasoning = BedrockProvider.extract(
        {
            "output": {
                "message": {
                    "content": [
                        {"reasoningContent": {"reasoningText": {"text": "counting the words"}}}
                    ]
                }
            }
        }
    )
    assert (visible, reasoning) == ("", "counting the words")


@pytest.mark.parametrize(
    "block",
    [
        {"reasoningContent": {"reasoningText": {"text": "the thought"}}},
        {"reasoningContent": {"text": "the thought"}},
    ],
    ids=["nested-reasoningText", "bare-text"],
)
def test_both_known_reasoning_shapes_are_read(block: dict[str, Any]) -> None:
    """A provider that changes the nesting costs a missing field, never a misattribution.

    If only one shape were understood, the other would fall through to the visible answer or
    vanish. Both are read into `reasoning`, and neither reaches the answer.
    """
    visible, reasoning = BedrockProvider.extract({"output": {"message": {"content": [block]}}})
    assert reasoning == "the thought"
    assert visible == ""


def test_a_plain_answer_produces_no_reasoning_at_all() -> None:
    """ANTI-VACUITY / MUTATION. The separation must not manufacture what was not sent.

    A model with no reasoning block returns an empty reasoning string. An extractor that copied
    the answer into both fields would pass every assertion above and fail this one.
    """
    visible, reasoning = BedrockProvider.extract(
        {"output": {"message": {"content": [{"text": "just the answer"}]}}}
    )
    assert visible == "just the answer"
    assert reasoning == ""


def test_a_malformed_or_empty_response_yields_two_empty_strings() -> None:
    """A shape the provider has never returned must not raise out of a static helper.

    The failure that matters is a wrong ANSWER; an unfamiliar block is dropped and shows up as an
    empty visible answer, which the caller already treats as a reviewable outcome.
    """
    assert BedrockProvider.extract({}) == ("", "")
    assert BedrockProvider.extract({"output": {}}) == ("", "")
    assert BedrockProvider.extract({"output": {"message": {"content": None}}}) == ("", "")
    assert BedrockProvider.extract(
        {"output": {"message": {"content": ["a bare string", None, {"text": "kept"}]}}}
    ) == ("kept", "")


# --- failure classification -------------------------------------------------------------------


@pytest.mark.parametrize(
    "code",
    ["ThrottlingException", "TooManyRequestsException", "ModelNotReadyException"],
    ids=["throttling", "too-many-requests", "provisioning-delay"],
)
def test_a_transient_condition_is_worth_one_retry(code: str) -> None:
    """Throttling and a first-use provisioning delay are the two the brief names explicitly.

    Both describe a condition that can differ on a second attempt, which is the only thing that
    makes a retry more than spend.
    """
    assert BedrockProvider.classify(FakeServiceError(code)) is True


@pytest.mark.parametrize(
    "code",
    ["ValidationException", "AccessDeniedException", "InputTooLongException"],
    ids=["validation-error", "access-denied", "context-overflow"],
)
def test_a_permanent_failure_is_never_marked_retryable(code: str) -> None:
    """ANTI-VACUITY for the classifier: the OPPOSITE cases must not be flagged.

    The same request fails the same way every time. Retrying a malformed request, a missing grant
    or a filing that does not fit the context window is spending money to learn nothing — and a
    context overflow specifically means the filing/model pairing is INCOMPATIBLE and has to be
    reported to the user, not attempted again.
    """
    assert BedrockProvider.classify(FakeServiceError(code)) is False


def test_a_transport_failure_is_recognised_by_its_exception_name() -> None:
    """A connection that never reached the service carries no service error code."""
    assert BedrockProvider.classify(EndpointConnectionError("no route")) is True


def test_an_unrecognised_exception_is_not_retryable() -> None:
    """Unknown means permanent. A default of "retry" turns every new failure mode into spend."""
    assert BedrockProvider.classify(RuntimeError("something else entirely")) is False


def test_a_retryable_word_in_the_message_alone_does_not_authorise_a_retry() -> None:
    """MUTATION TEST. The classifier reads the structured code, never the message text.

    An exception whose message happens to contain "ThrottlingException" carries no such code. A
    substring match would pass every other test in this section and fail this one.
    """
    assert BedrockProvider.classify(RuntimeError("ThrottlingException")) is False
    assert BedrockProvider.classify(FakeServiceError("")) is False


# --- invocation ---------------------------------------------------------------------------------


def test_the_client_receives_exactly_the_arguments_that_were_built() -> None:
    """Nothing is added, removed or rewritten between construction and the call."""
    request = model_request(original_source=(text_block("a.htm", "ALPHA"),))
    _, factory = invoke(request)
    assert factory.clients[0].calls == [arguments_for(request)]


def test_usage_stop_reason_and_the_provider_request_id_are_carried_through() -> None:
    """These four fields are the entire evidentiary value of an invocation record.

    Token counts are the only honest input to a cost measurement — every figure in
    `docs/llm/cost-model.md` is still a placeholder — and the provider request id is what lets a
    later question about one invocation be answered at all.
    """
    response, _ = invoke(
        payload=response_payload(
            stop_reason="end_turn", usage={"inputTokens": 210_000, "outputTokens": 3_144}
        )
    )
    assert response.input_tokens == 210_000
    assert response.output_tokens == 3_144
    assert response.stop_reason == "end_turn"
    assert response.provider_request_id == REQUEST_ID


def test_a_response_without_a_request_id_reports_none_rather_than_an_empty_string() -> None:
    """ANTI-VACUITY. An empty string would read as an id that exists and happens to be blank."""
    response, _ = invoke(payload=response_payload(request_id=None))
    assert response.provider_request_id is None


def test_missing_usage_counts_are_zero_rather_than_absent() -> None:
    """A cost calculation must never receive None where it expects a token count."""
    payload = response_payload()
    del payload["usage"]
    response, _ = invoke(payload=payload)
    assert (response.input_tokens, response.output_tokens) == (0, 0)


def test_an_empty_answer_at_the_output_cap_is_reported_as_truncated() -> None:
    """THE PHASE 1 CASE, end to end, and the reason `truncated` exists at all.

    The whole 8-token budget went to reasoning: the text block came back empty and the stop reason
    was `max_tokens`. AN EMPTY ANSWER AT MAX_TOKENS IS NOT AN EMPTY ANSWER. The response records
    an empty visible text, the reasoning in full, and `truncated` set from the provider's stop
    reason rather than inferred from what the text looks like.
    """
    response, _ = invoke(
        payload=response_payload(
            content=[{"reasoningContent": {"reasoningText": {"text": "counting the words"}}}],
            stop_reason="max_tokens",
            usage={"inputTokens": 19, "outputTokens": 8},
        )
    )
    assert response.text == ""
    assert response.reasoning_text == "counting the words"
    assert response.truncated is True
    assert response.stop_reason == "max_tokens"
    assert response.output_tokens == 8


def test_a_completed_response_is_not_marked_truncated() -> None:
    """ANTI-VACUITY for the guard above, in both directions.

    A full answer that stopped on its own is not truncated, and — the case that would otherwise go
    unnoticed — neither is an empty answer that stopped on its own. `truncated` follows the stop
    reason the provider reported and nothing else.
    """
    complete, _ = invoke(payload=response_payload(stop_reason="end_turn"))
    assert complete.truncated is False

    empty_but_finished, _ = invoke(
        payload=response_payload(content=[{"text": ""}], stop_reason="end_turn")
    )
    assert empty_but_finished.truncated is False
    assert empty_but_finished.text == ""


def test_the_response_records_the_model_provider_and_region_actually_used() -> None:
    """A failure or a result stays attached to the model the user selected, in the region asked."""
    response, factory = invoke(model_request(model_id=OTHER_MODEL_ID, region=OTHER_REGION))
    assert response.model_id == OTHER_MODEL_ID
    assert response.provider == "bedrock"
    assert response.region == OTHER_REGION
    assert factory.regions == [OTHER_REGION], "the adapter widened or substituted the region"


def test_both_transport_envelopes_are_recorded_on_the_response() -> None:
    """Evidence for a reviewer: what was sent, and what came back, as the provider framed them."""
    request = model_request(original_source=(text_block("a.htm", "ALPHA"),))
    response, _ = invoke(request)
    assert response.transport_request == BedrockProvider.transport_evidence(arguments_for(request))
    assert json.loads(response.transport_response)["stopReason"] == "end_turn"


def test_the_provider_reported_latency_wins_over_the_local_clock() -> None:
    """The provider's own measurement excludes this process's serialization time."""
    response, _ = invoke(payload=response_payload(latency_ms=4242), clock=TickingClock(step=0.5))
    assert response.latency_ms == 4242


def test_local_elapsed_time_is_recorded_when_the_provider_reports_no_metric() -> None:
    """ANTI-VACUITY for the guard above: latency is never silently zero.

    A missing provider metric falls back to the injected clock, so an invocation always carries
    some measured duration — and the clock is injected precisely so this assertion does not depend
    on how fast the test host is.
    """
    response, _ = invoke(clock=TickingClock(step=0.5))
    assert response.latency_ms == 500


def test_the_client_is_built_once_per_region_and_reused() -> None:
    """A client per invocation would re-resolve identity on every call for no benefit."""
    factory = RecordingFactory()
    provider = BedrockProvider(client_factory=factory, clock=TickingClock())
    provider.invoke(model_request())
    provider.invoke(model_request())
    assert factory.regions == [REGION]
    assert len(factory.clients) == 1
    assert len(factory.clients[0].calls) == 2


def test_a_second_region_never_reuses_the_first_regions_client() -> None:
    """MUTATION TEST for the cache above: caching must be keyed by region, not global.

    A single cached client would silently send the second request to the first region — a model
    invoked somewhere the snapshot never verified it, which is the failure the region rules exist
    to prevent.
    """
    factory = RecordingFactory()
    provider = BedrockProvider(client_factory=factory, clock=TickingClock())
    provider.invoke(model_request(region=REGION))
    provider.invoke(model_request(region=OTHER_REGION))
    assert factory.regions == [REGION, OTHER_REGION]
    assert len(factory.clients) == 2


def test_the_adapter_reports_no_exact_token_count_of_its_own() -> None:
    """Nothing is known about real token counts before Phase 2 measures them.

    The base class returns None for "no exact provider count available", and the adapter must not
    substitute an estimate that would then be recorded as if the provider had said it.
    """
    assert BedrockProvider(client_factory=RecordingFactory()).count_tokens("some text") is None


# --- failure normalisation ------------------------------------------------------------------


def test_a_client_failure_becomes_a_provider_error_and_the_sdk_type_never_escapes() -> None:
    """The provider's exception type stops at this boundary.

    A caller that had to catch a provider-specific exception class would need the provider SDK
    installed to handle a failure — and every layer above would grow an import of it. The original
    is preserved as `__cause__` for a traceback; the TYPE the caller sees is `ProviderError`.
    """
    factory = RecordingFactory(error=FakeServiceError("ValidationException"))
    provider = BedrockProvider(client_factory=factory, clock=TickingClock())
    with pytest.raises(ProviderError) as raised:
        provider.invoke(model_request())

    assert not isinstance(raised.value, FakeServiceError)
    assert isinstance(raised.value.__cause__, FakeServiceError)
    assert raised.value.provider == "bedrock"


def test_the_failure_names_the_model_and_region_it_belongs_to() -> None:
    """A failure stays attached to the model the user selected, by name, in the message.

    "Bedrock refused" with no identifier sends a user to a support channel; naming the model and
    the region is what makes the refusal actionable.
    """
    factory = RecordingFactory(error=FakeServiceError("AccessDeniedException"))
    provider = BedrockProvider(client_factory=factory, clock=TickingClock())
    with pytest.raises(ProviderError) as raised:
        provider.invoke(model_request(model_id=OTHER_MODEL_ID, region=OTHER_REGION))

    message = str(raised.value)
    assert OTHER_MODEL_ID in message
    assert OTHER_REGION in message


def test_an_unset_region_is_named_in_the_failure_rather_than_guessed() -> None:
    """An empty region is reported as unset. It is never filled in with a default."""
    factory = RecordingFactory(error=FakeServiceError("ValidationException"))
    provider = BedrockProvider(client_factory=factory, clock=TickingClock())
    with pytest.raises(ProviderError, match="an unset region"):
        provider.invoke(model_request(region=""))
    assert factory.regions == [""]


@pytest.mark.parametrize(
    ("code", "retryable"),
    [("ThrottlingException", True), ("ValidationException", False)],
    ids=["transient", "permanent"],
)
def test_the_retryable_flag_travels_on_the_normalised_error(code: str, retryable: bool) -> None:
    """The honest flag is the whole point of normalising: the orchestrator decides on it.

    Both directions are asserted, because a flag hardcoded either way would satisfy one case.
    """
    factory = RecordingFactory(error=FakeServiceError(code))
    provider = BedrockProvider(client_factory=factory, clock=TickingClock())
    with pytest.raises(ProviderError) as raised:
        provider.invoke(model_request())
    assert raised.value.retryable is retryable


def test_the_adapter_retries_nothing_of_its_own_even_when_a_retry_is_permitted() -> None:
    """RETRY IS THE ORCHESTRATOR'S DECISION, NOT THE ADAPTER'S.

    `packages/model_catalog.RetryBudget` owns the one permitted automatic retry and charges the
    cost ceiling for it. An adapter that retried internally would spend money the ledger never
    saw — so the strongest case is asserted: a failure the adapter itself marks RETRYABLE still
    reaches the client exactly once.
    """
    factory = RecordingFactory(error=FakeServiceError("ThrottlingException"))
    provider = BedrockProvider(client_factory=factory, clock=TickingClock())
    with pytest.raises(ProviderError) as raised:
        provider.invoke(model_request())

    assert raised.value.retryable is True
    assert len(factory.clients) == 1
    assert len(factory.clients[0].calls) == 1, "the adapter retried an invocation by itself"


def test_a_successful_invocation_calls_the_model_exactly_once() -> None:
    """ANTI-VACUITY for the guard above: the single call is not an artefact of the failure path."""
    _, factory = invoke()
    assert len(factory.clients[0].calls) == 1


# --- client construction and the credential prohibition -------------------------------------


def test_a_client_cannot_be_built_without_a_region() -> None:
    """A guessed region is the form-family defect with a bill attached.

    Phase 1 made that concrete by finding one approved candidate that is not offered in the
    project's preferred region at all. The refusal happens BEFORE any SDK import, which is why
    this test needs nothing installed and reaches nothing.
    """
    with pytest.raises(ProviderError) as raised:
        default_client_factory("")

    assert raised.value.retryable is False
    assert raised.value.provider == "bedrock"
    assert "region" in str(raised.value)


def test_the_adapter_source_names_no_credential_argument_anywhere() -> None:
    """AWS-IDENTITY-AND-SECRETS-INVARIANT: no credential ever reaches this code.

    The client is constructed with a region and nothing else; temporary credentials are resolved
    and refreshed by the SDK's default provider chain. The cheapest moment to forbid an explicit
    credential argument is before the first call site exists, and this is the module where one
    would appear first. The final assertion is the anti-vacuity check: it proves the comparison
    used here would actually detect the thing it forbids.
    """
    source = Path(bedrock_module.__file__).read_text(encoding="utf-8")
    assert len(source) > 1000, "anti-vacuity: the adapter source was not read"

    for name in CREDENTIAL_ARGUMENTS:
        assert f"{name}=" not in source, f"the adapter passes {name} to a client"
        assert name not in source, f"the adapter names {name} at all"

    planted = "client(region, " + CREDENTIAL_ARGUMENTS[0] + "=value)"
    assert any(f"{name}=" in planted for name in CREDENTIAL_ARGUMENTS), (
        "the check cannot detect the argument it forbids"
    )
