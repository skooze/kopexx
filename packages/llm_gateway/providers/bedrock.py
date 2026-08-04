"""The Bedrock runtime adapter — the only place in this repository that touches an AWS SDK.

rules.md section 5 names this exact module as the sole home for provider SDK usage, and
`tests/architecture/test_architecture.py` fails the build if `boto3` or `botocore` is imported
anywhere outside this directory.

NO CREDENTIAL EVER REACHES THIS CODE. The client is constructed with a region and nothing else.
Temporary credentials are resolved and refreshed by the SDK's default provider chain — a federated
login on a workstation, an IAM role on a workload, an OIDC-assumed role in CI. This adapter does
not accept an access key, a secret key, a session token or a credential file path, does not read
one from the environment itself, does not cache one, and never writes one into an invocation
record. rules.md section 3, AWS-IDENTITY-AND-SECRETS-INVARIANT.

boto3 IS AN OPTIONAL DEPENDENCY AND IS IMPORTED LAZILY. Ordinary CI installs `.[dev]`, which does
not include it, so the phrase "ordinary CI is AWS-free" means the SDK is not even present rather
than merely unused. The import happens inside the client factory, so importing this module — which
the architecture tests do — costs nothing and requires nothing.

WHAT THIS ADAPTER KNOWS. Converse request construction, multimodal content blocks, usage
extraction, latency, stop reason, the separation of reasoning content from answer text, the
provider request id, and how to turn a provider failure into a typed error with an honest
retryable flag.

WHAT IT MUST NEVER KNOW. Filing sections, footnote meaning, table meaning, semantic hierarchy, UI
layout, approval policy, or which model should have been chosen. It is handed an invocation
identifier and a region and it uses exactly those — no fallback model, no fallback region, no
fallback prompt, no substitution. A failure stays attached to the model the user selected.
"""

from __future__ import annotations

import base64
import json
import time
from collections.abc import Callable
from typing import Any

from ..errors import CredentialResolutionError, ProviderError
from .base import ModelProvider, ModelRequest, ModelResponse

#: Provider error codes that describe a transient condition. Everything else is permanent.
#:
#: `ThrottlingException` and `ModelNotReadyException` are the two the Phase 2 brief names
#: explicitly — throttling, and a first-use provisioning delay. A validation error, an unsupported
#: source, a context overflow, an access denial or an output-schema failure is NOT retryable: the
#: same request would fail the same way, and retrying it is spending money to learn nothing.
RETRYABLE_ERROR_CODES: frozenset[str] = frozenset(
    {
        "ThrottlingException",
        "TooManyRequestsException",
        "ModelNotReadyException",
        "ModelTimeoutException",
        "ServiceUnavailableException",
        "InternalServerException",
        "RequestTimeout",
        "RequestTimeoutException",
    }
)

#: SDK exceptions raised while RESOLVING AN IDENTITY, before any request is constructed or sent.
#:
#: MEASURED, AND THE REASON THIS SET EXISTS. Phase 2.1 lost an AWS IAM Identity Center session
#: mid-run at 2026-08-04T02:18:20Z. Eleven subsequent attempts failed with `TokenRetrievalError:
#: Token has expired and refresh failed`, every one with zero input tokens, zero output tokens,
#: zero latency and no provider request id — and every one held its full worst-case reservation
#: against the cumulative ceiling, because nothing could prove the request had never been sent.
#: USD 0.22590990 of authorization, held for calls no provider ever saw.
#:
#: NONE OF THESE IS RETRYABLE. An expired federated session does not become valid by being asked
#: twice, and the eleven failures above happened inside four minutes. Neither does a request the
#: SDK refused to send: the same parameters produce the same refusal.
CREDENTIAL_EXCEPTION_NAMES: frozenset[str] = frozenset(
    {
        "TokenRetrievalError",
        "UnauthorizedSSOTokenError",
        "SSOTokenLoadError",
        "SSOError",
        "NoCredentialsError",
        "PartialCredentialsError",
        "CredentialRetrievalError",
        "InvalidConfigError",
        "ProfileNotFound",
        "TokenProviderNotSupportedError",
        "RefreshWithMFAUnsupportedError",
        # NOT a credential failure, but provably pre-transport for the same reason and with the
        # same billing consequence: botocore validates the request parameters locally and raises
        # before it opens a connection. MEASURED 2026-08-04 — a sizing policy that computed a
        # zero-token output budget produced `Invalid value for parameter
        # inferenceConfig.maxTokens, value: 0`, and the reservation was charged for a call no
        # provider ever saw.
        "ParamValidationError",
        "MissingParametersError",
        "ValidationError",
    }
)

#: Transport-level failures raised by the SDK rather than returned by the service.
RETRYABLE_EXCEPTION_NAMES: frozenset[str] = frozenset(
    {
        "EndpointConnectionError",
        "ConnectTimeoutError",
        "ReadTimeoutError",
        "ConnectionClosedError",
        "IncompleteReadError",
    }
)


#: How long one Converse call may take before the SDK gives up, in seconds.
#:
#: MEASURED, NOT GUESSED. The SDK's default read timeout is 60 seconds. The first real parse of a
#: preserved filing took 158 seconds — a 23,000-token input producing a 4,900-token structured
#: response — and a candidate with a larger output limit timed out at the default on the same
#: filing. Sixty seconds is a sensible default for a control-plane call and is simply the wrong
#: order of magnitude for a language model reading a 10-K.
READ_TIMEOUT_SECONDS: int = 900
CONNECT_TIMEOUT_SECONDS: int = 15

#: Total attempts the SDK itself may make. ONE. Not a retry — one attempt, and no retry.
#:
#: THIS IS A COST CONTROL, AND ITS ABSENCE WAS A REAL DEFECT. botocore retries on its own by
#: default, and a Converse call is BILLABLE FROM THE MOMENT IT IS ISSUED. A retry inside the SDK
#: is therefore a second charge that `packages/model_catalog.RetryBudget` never counted and the
#: durable spend journal never saw — the ceiling would have been enforced against a number smaller
#: than the bill. The one permitted automatic retry belongs to the orchestrator, which reserves
#: for it before it happens and settles it afterwards.
SDK_MAX_ATTEMPTS: int = 1


def default_client_factory(region: str) -> Any:
    """Construct a Bedrock Runtime client for one region, with no credential arguments.

    The region is REQUIRED and has no default. `packages/configuration` already refuses to build
    settings for a non-mock provider without one, because a guessed region is the form-family
    defect with a bill attached — and Phase 1 made that concrete by finding one approved candidate
    that is not offered in the project's preferred region at all.
    """
    if not region:
        raise ProviderError(
            "a Bedrock client requires a region and none was supplied; the region comes from the "
            "reviewed capability snapshot through the model router, never from a default here",
            retryable=False,
            provider="bedrock",
        )
    try:
        import boto3  # noqa: PLC0415 - deliberately lazy; see the module docstring
        from botocore.config import Config  # noqa: PLC0415
    except ImportError as error:  # pragma: no cover - exercised only without the optional extra
        raise ProviderError(
            "the AWS SDK is not installed. It is an OPTIONAL dependency so that ordinary CI has "
            "no provider SDK at all: install it with `pip install -e '.[aws]'` on a host that is "
            "meant to reach a model.",
            retryable=False,
            provider="bedrock",
        ) from error
    # No credential arguments. The default provider chain resolves temporary credentials.
    return boto3.client(
        "bedrock-runtime",
        region_name=region,
        config=Config(
            read_timeout=READ_TIMEOUT_SECONDS,
            connect_timeout=CONNECT_TIMEOUT_SECONDS,
            retries={"max_attempts": SDK_MAX_ATTEMPTS, "mode": "standard"},
        ),
    )


class BedrockProvider(ModelProvider):
    """Invoke one model through the Bedrock Converse API.

    `client_factory` is injectable so the whole adapter is testable with a fake client and no AWS
    identity. That is not a convenience: `tests/architecture/test_phase1_aws_boundary.py` fails
    the build if any test imports a provider SDK, and the suite has to keep its property of having
    no environmental precondition at all.
    """

    name = "bedrock"

    def __init__(
        self,
        *,
        client_factory: Callable[[str], Any] = default_client_factory,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._client_factory = client_factory
        self._clock = clock
        self._clients: dict[str, Any] = {}

    def _client(self, region: str) -> Any:
        if region not in self._clients:
            self._clients[region] = self._client_factory(region)
        return self._clients[region]

    # --- request construction ------------------------------------------------------------------

    @staticmethod
    def build_converse_arguments(request: ModelRequest) -> dict[str, Any]:
        """The exact Converse arguments for one request.

        ORDER IS DELIBERATE: the instruction first, then the preserved artifacts in the order the
        source set assembled them. The instruction has to be readable before the filing it is
        about, and a filing's members have to arrive in filed order because that order is part of
        what the filer submitted.

        EACH ARTIFACT IS LABELLED WITH ITS FILENAME AND NOTHING ELSE. A label is a mechanical
        identifier, exactly as rules.md section 11 permits — "labelling separate original package
        members mechanically". It is not a description, not a role and not a classification, and
        the model is told in the prompt that the labels are transport identifiers rather than
        meaning.
        """
        blocks: list[dict[str, Any]] = [{"text": request.user_content}]
        for block in request.original_source:
            if block.is_image:
                if not block.image_format:
                    # NEVER GUESSED. Defaulting to png announced a fact about preserved content
                    # that the source store never declared: a JPEG with no declared format would
                    # have been sent as a PNG, and the provider would then fail on bytes the
                    # caller had been told were fine. The format comes from byte-signature
                    # detection in the source store or the block does not go.
                    raise ProviderError(
                        f"{block.label!r} is an image block with no declared format; the format "
                        "comes from byte-signature detection and is never guessed here",
                        retryable=False,
                        provider="bedrock",
                    )
                blocks.append({"text": f"SOURCE ARTIFACT: {block.label}"})
                blocks.append(
                    {
                        "image": {
                            "format": block.image_format,
                            "source": {"bytes": block.raw_bytes},
                        }
                    }
                )
            else:
                if block.text is None:
                    # A labelled artifact with an empty body is a member the model is told about
                    # and cannot read, with nothing marked unresolved — a complete-content failure
                    # wearing a successful request.
                    raise ProviderError(
                        f"{block.label!r} is a text block carrying no decoded text; an artifact "
                        "that failed to decode is reported, never sent as an empty body",
                        retryable=False,
                        provider="bedrock",
                    )
                blocks.append({"text": f"SOURCE ARTIFACT: {block.label}"})
                blocks.append({"text": block.text})

        arguments: dict[str, Any] = {
            "modelId": request.model_id,
            "messages": [{"role": "user", "content": blocks}],
            "inferenceConfig": {
                "maxTokens": request.max_output_tokens,
                "temperature": request.temperature,
            },
        }
        if request.system_text:
            arguments["system"] = [{"text": request.system_text}]
        return arguments

    @staticmethod
    def transport_evidence(arguments: dict[str, Any]) -> str:
        """The request envelope as transport evidence, with image bytes referenced by hash.

        JSON IS CORRECT HERE AND IS NOT A BOUNDARY VIOLATION. This string is never model-visible.
        It is the provider's own envelope, written to ignored evaluation storage so a reviewer can
        see exactly what crossed the wire. rules.md section 3 permits provider transport JSON as
        the API envelope; ADR-0013 governs what a MODEL sees.

        Image bytes are replaced by their SHA-256 and byte count rather than base64-inlined. The
        exact image bytes are preserved as their own evidence object beside this envelope, so the
        request remains fully reconstructible without carrying every artifact twice.
        """
        from packages.storage import sha256_bytes  # noqa: PLC0415 - leaf import kept local

        def scrub(node: Any) -> Any:
            if isinstance(node, dict):
                if "bytes" in node and isinstance(node["bytes"], (bytes, bytearray)):
                    raw = bytes(node["bytes"])
                    return {
                        "bytes_sha256": sha256_bytes(raw),
                        "byte_count": len(raw),
                        "note": "exact bytes preserved as a separate evidence object",
                    }
                return {key: scrub(value) for key, value in node.items()}
            if isinstance(node, list):
                return [scrub(item) for item in node]
            if isinstance(node, (bytes, bytearray)):
                return base64.b64encode(bytes(node)).decode("ascii")
            return node

        return json.dumps(scrub(arguments), indent=2, sort_keys=True)

    # --- response extraction -------------------------------------------------------------------

    @staticmethod
    def extract(payload: dict[str, Any]) -> tuple[str, str]:
        """(visible answer text, reasoning text) from a Converse response.

        THE TWO ARE NEVER MERGED. Phase 1 measured a candidate whose 8-token output cap was
        consumed entirely by a `reasoningContent` block, leaving the text block empty with stop
        reason `max_tokens`. A caller that concatenated them would have seen a plausible answer
        that was really a chain of thought; a caller that read only the text would have recorded
        an empty response from a model that was working correctly and had simply run out of room.

        Both known shapes of a reasoning block are read — `reasoningText.text` and a bare `text` —
        because a provider that changes the nesting should cost a missing field, not a silent
        misattribution of reasoning into the answer.
        """
        visible: list[str] = []
        reasoning: list[str] = []
        message = (payload.get("output") or {}).get("message") or {}
        for block in message.get("content") or ():
            if not isinstance(block, dict):
                continue
            if "text" in block:
                visible.append(str(block["text"]))
            reasoning_block = block.get("reasoningContent")
            if isinstance(reasoning_block, dict):
                inner = reasoning_block.get("reasoningText")
                if isinstance(inner, dict) and "text" in inner:
                    reasoning.append(str(inner["text"]))
                elif "text" in reasoning_block:
                    reasoning.append(str(reasoning_block["text"]))
        return "".join(visible), "".join(reasoning)

    @staticmethod
    def classify(error: Exception) -> bool:
        """Whether a provider failure is worth exactly one retry."""
        code = ""
        response = getattr(error, "response", None)
        if isinstance(response, dict):
            code = str((response.get("Error") or {}).get("Code") or "")
        if code in RETRYABLE_ERROR_CODES:
            return True
        return type(error).__name__ in RETRYABLE_EXCEPTION_NAMES

    # --- invocation ----------------------------------------------------------------------------

    def invoke(self, request: ModelRequest) -> ModelResponse:
        """One Converse call. No retry, no fallback, no substitution.

        RETRY IS THE ORCHESTRATOR'S DECISION, NOT THE ADAPTER'S. `packages/model_catalog.RetryBudget`
        owns the one permitted automatic retry and the reasons that justify one, and it charges the
        cost ceiling for it. An adapter that retried internally would spend money the ledger never
        saw.
        """
        arguments = self.build_converse_arguments(request)
        envelope = self.transport_evidence(arguments)
        client = self._client(request.region)

        started = self._clock()
        try:
            payload = client.converse(**arguments)
        except Exception as error:  # normalised, never leaked as a provider-specific type
            # A CREDENTIAL FAILURE IS A DIFFERENT FACT FROM A PROVIDER REFUSAL, and the difference
            # is worth money. Both arrive here with zero tokens and no request id; only one of them
            # means a request was actually issued. Naming the identity failures explicitly is what
            # lets the spend journal release a reservation it can PROVE was never spent.
            if type(error).__name__ in CREDENTIAL_EXCEPTION_NAMES:
                raise CredentialResolutionError(
                    f"bedrock could not resolve an identity for {request.model_id!r} in "
                    f"{request.region or 'an unset region'}: {type(error).__name__}: {error}. "
                    "No request was constructed and nothing was sent.",
                    provider=self.name,
                ) from error
            raise ProviderError(
                f"bedrock refused the invocation of {request.model_id!r} in "
                f"{request.region or 'an unset region'}: {type(error).__name__}: {error}",
                retryable=self.classify(error),
                provider=self.name,
            ) from error
        elapsed_ms = int((self._clock() - started) * 1000)

        visible, reasoning = self.extract(payload)
        usage = payload.get("usage") or {}
        metadata = payload.get("ResponseMetadata") or {}
        stop_reason = str(payload.get("stopReason") or "")

        return ModelResponse(
            text=visible,
            input_tokens=int(usage.get("inputTokens") or 0),
            output_tokens=int(usage.get("outputTokens") or 0),
            model_id=request.model_id,
            provider=self.name,
            stop_reason=stop_reason,
            # A response is truncated when the provider says the budget ran out, whatever the
            # visible text looks like. An empty answer at `max_tokens` is not an empty answer.
            truncated=stop_reason == "max_tokens",
            reasoning_text=reasoning,
            provider_request_id=str(metadata.get("RequestId") or "") or None,
            # `payload.get("metrics", {})` returns None when the key is PRESENT and null, and
            # `.get` on None raises. This line sits outside the try, after an already-billed
            # response came back, so the raw AttributeError lost a response that had been paid
            # for — the exact leak the adapter's error boundary exists to prevent. Every other
            # field on this path already used the `or {}` idiom; this one did not.
            latency_ms=int((payload.get("metrics") or {}).get("latencyMs") or elapsed_ms),
            region=request.region,
            transport_request=envelope,
            transport_response=json.dumps(payload, indent=2, sort_keys=True, default=str),
        )
