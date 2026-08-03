# Model Abstraction

IMPLEMENTATION STATUS: IMPLEMENTED — the provider interface, the mock provider, the Bedrock
Converse adapter, and the gateway's provenance admission of preserved SEC source. Phase 2 invoked
the PARSING role only; the image, summary and analysis roles are routed, but their stages are
PLANNED and raise `StageNotAuthorizedError` rather than invoking anything.
OWNER PACKAGE: `packages/llm_gateway`

## Principle

**The USER selects the model, per job, for each of the four roles independently.** Application code
never hard-codes a provider model identifier, never substitutes one model for another, and never
falls back silently. An identifier reaches the adapter as configuration or as an explicit user
selection, and a model swap changes no code.

## Interfaces

The complete provider surface, in `packages/llm_gateway/providers/base.py`.

```
OriginalSourceBlock      label, sha256, byte_count, media_kind, raw_bytes,
                         text, codec, image_format

ModelRequest             model_id, system_text, user_content, user_content_format,
                         max_output_tokens, temperature, original_source, region

ModelResponse            text, reasoning_text, input_tokens, output_tokens, model_id, provider,
                         stop_reason, truncated, provider_request_id, latency_ms, region,
                         transport_request, transport_response

ModelProvider.invoke(request) -> ModelResponse
ModelProvider.count_tokens(text) -> int | None
```

`user_content_format` is `plain_text` or `yaml` — the two permitted SYNTHETIC formats. `region` is
supplied by the caller and never defaulted: it is DERIVED from the reviewed capability snapshot by
`packages/model_catalog/routing.py`, which is why no region literal appears in this document, in
the router, or in the adapter.

There is no `ModelCapabilities` type. There used to be — `model_id`, `provider`, token limits,
batch, flex and reasoning-effort flags — and it was deleted as dead code: it had no constructor and
no caller anywhere in the repository, and every field in it describes a provider this project had
never reached. **Capability facts were discovered live in Phase 1 and recorded then**, and a type
asserting their existence in advance was a standing invitation to write one down from memory.

Whatever replaces it keeps the original omission: no `supports_structured_output` and no
`supports_native_tools`. Both describe provider features that require JSON at the model boundary and
are unusable in this system regardless of whether a provider offers them (ADR-0013). Their presence
would invite a call site to branch on them.

---

## Preserved source at the boundary — added 2026-08-03, Phase 2

### The omission this document recorded, and how it was closed

Until Phase 2 this section said, of the provider interface:

```
This interface has no representation for a preserved SEC artifact sent intact under the
original-source exception, and it will need one before the first real parsing run. Its shape is
not guessed here; it is designed against a real adapter and a real provider request in Phase 2.
```

That is RESOLVED as of 2026-08-03. `OriginalSourceBlock` is the shape, and it was designed the way
the note promised: against a real Converse request rather than in advance. Every field exists
because the request needed it, which is why there is no field for a role, a section name, a
document class or an importance ranking — nothing on the wire asked for one, and rules.md section 21
rule 1 forbids the backend from deciding any of them.

### Why each field exists

```
label          the filed filename, and nothing else. A mechanical transport identifier, exactly
               what rules.md section 11 permits. Not a description, not a role, not a class.
sha256         the digest the source store recorded. This is what ADMITS the block.
byte_count     the length the source store recorded, checked against the bytes actually carried.
media_kind     text or image. The only distinction the transport itself requires.
raw_bytes      the exact preserved bytes. An image block sends these; every block is verified
               against its digest using these.
text           the losslessly decoded content of a TEXT block — the one permitted transformation,
               recorded rather than invisible.
codec          what performed that decoding, so the round-trip is checkable rather than asserted.
image_format   the format the source store declared for an IMAGE block, carried rather than
               sniffed by the adapter.
```

An image block carries no `text` at all. Backend code never transcribes, describes or captions a
filed image, because that would be backend code deciding what filing content means. When the
selected model has no verified image path, the orchestrator omits the image block and tells the
model in the instruction that image-bearing members were filed and excluded — the absence is
disclosed, never silently absorbed.

### Admitted by PROVENANCE, not by syntax

`packages/llm_gateway/gateway.py::verify_original_source` runs before anything reaches a provider,
and it is the whole basis on which an SEC artifact is allowed past the content boundary. Preserved
blocks deliberately do NOT go through the synthetic-content validator: running an inline-XBRL filing
through a validator that rejects HTML would reject the filing for being a filing.

The provenance check is not a weaker check than the validator. It is a different and stronger
question — are these the bytes SEC published — and it refuses in five named ways:

| Refusal | The defect it catches |
|---|---|
| `missing_provenance` | no recorded 64-character hex digest; the block only *looks* like an original |
| `byte_count_mismatch` | the carried length disagrees with the recorded length |
| `provenance_mismatch` | the bytes do not hash to the recorded digest, so this system built or altered them |
| `undeclared_decoding` | a text block with no decoded text, or no codec naming what decoded it |
| `lossy_decoding` | `text.encode(codec)` does not reproduce `raw_bytes` exactly |

The round-trip check is the one worth stating plainly. Decoding is permitted by the intact-source
rule **only because it is lossless**, so the code proves that per block instead of assuming it.
Proving it costs a re-encode; assuming it is how a filing reaches a model as mojibake and a reviewer
spends an afternoon blaming the model.

**The exception is one-directional.** No model RESPONSE may use it. A response is still exactly one
unfenced YAML 1.2 document, or plain text, validated on the way back. Full specification:
`docs/llm/content-boundary.md`.

The audit record carries `original_source_hashes` — the digest of every preserved artifact sent —
so what was in the request is identifiable without storing the filing a second time.

---

## Reasoning is not the answer — added 2026-08-03, Phase 2

`ModelResponse.reasoning_text` IS SEPARATE FROM `ModelResponse.text`, AND THE SEPARATION IS
LOAD-BEARING.

Phase 1 measured a candidate that emits reasoning content before its answer on the Converse path.
At a deliberately tiny output cap the whole budget went to reasoning, the text block came back
empty, and the stop reason was `max_tokens`. Folding the two together would make a chain of thought
look like a well-formed answer; dropping the reasoning would make an exhausted budget look like a
model with nothing to say. Both are recorded, both are preserved, and neither is ever presented as
the other.

`truncated` follows the provider's stop reason and not the look of the text, for the same reason:
**an empty answer at `max_tokens` is not an empty answer.**

`transport_request` and `transport_response` carry the provider's own envelope as it crossed the
wire. That is TRANSPORT EVIDENCE, written to gitignored evaluation storage so a reviewer can see
exactly what was sent and returned. It is never shown to another model as semantic input, and the
JSON in it is not a boundary violation — rules.md section 3 permits provider transport JSON as the
API envelope, while ADR-0013 governs what a MODEL sees.

---

## AWS identity — binding on the Bedrock adapter

The Bedrock provider uses the AWS SDK default credential provider chain. The client is constructed
with a region and nothing else. It never accepts access-key or secret-key parameters, never
constructs a client with explicit credential values, never reads credentials from `.env`, never
caches them, and never writes them into an invocation record. Temporary credentials are resolved and
refreshed externally — a federated login on a workstation, an IAM role on a workload, an
OIDC-assumed role in CI. `tests/unit/test_bedrock_adapter.py` scans the adapter's own source and
fails if any credential argument name appears in it.

**boto3 is an OPTIONAL extra and is imported LAZILY.** `pyproject.toml` declares it under the `aws`
extra; ordinary CI installs `.[dev]`, so "ordinary CI is AWS-free" means the provider SDK is not
even present rather than merely unused. The import happens inside the client factory, so importing
the adapter module — which the architecture tests do — costs nothing and requires nothing. When the
extra is absent the factory raises a named `ProviderError` telling the operator to install
`.[aws]` on a host that is meant to reach a model, rather than failing at import time on every host
that is not.

The region is REQUIRED and has no default. A guessed region is the form-family defect with a bill
attached, and Phase 1 made that concrete by finding an approved candidate that is not offered in the
project's preferred region at all.

The mock provider requires no AWS identity and keeps working without one, so the default test suite
never needs AWS access.

Full requirements, including the preflight identity report and its prohibited fields:
`docs/security/aws-identity-and-secrets.md`.

## Provider responsibilities

Only a provider adapter may import a provider SDK, enforced by
`test_bedrock_client_not_imported_outside_provider`.

A provider adapter: translates a `ModelRequest` into its SDK call, normalizes usage accounting,
normalizes errors into `ProviderError` with a retryable flag, and reports an exact token count when
the provider offers one.

A provider adapter does **not**: build model-visible content, validate the boundary, decide
retries, or calculate cost. Those belong to the gateway and to the orchestrator.

### Retry belongs to the orchestrator, not the adapter

`BedrockProvider.invoke` makes exactly one Converse call. It never retries, never falls back to
another model, never falls back to another region, and never substitutes a prompt. A failure stays
attached to the model the user selected.

`packages/model_catalog.RetryBudget` owns the one permitted automatic retry, and the orchestrator
holds it. That placement is deliberate: the budget is consumed only for a transient service error,
throttling, a first-use provisioning delay or a retryable network failure, and it charges the
attempt against the cumulative spend ceiling. **An adapter that retried internally would spend money
the ledger never saw.** A response whose wording is merely disliked is never a retryable reason —
retrying until a model says what you wanted is prompt tuning with the measurement removed.

---

## The Bedrock adapter — IMPLEMENTED 2026-08-03, Phase 2

`packages/llm_gateway/providers/bedrock.py` is the only module in the repository that touches an AWS
SDK. `tests/architecture/test_architecture.py` fails the build if `boto3` or `botocore` is imported
anywhere else, and `tests/architecture/test_phase1_aws_boundary.py` fails it if a TEST imports one —
which is why the client factory is injectable. That is not a convenience: the suite has to keep its
property of having no environmental precondition at all.

**What it knows.** Converse request construction, multimodal content blocks, usage extraction,
latency, stop reason, the separation of reasoning content from answer text, the provider request id,
one client per region built once and reused, and how to turn a provider failure into a typed error
with an honest retryable flag.

**What it must never know.** Filing sections, footnote meaning, table meaning, semantic hierarchy,
UI layout, approval policy, or which model should have been chosen.

**Request order is part of the contract.** The instruction goes first, then the preserved artifacts
in the order the source set assembled them. The instruction has to be readable before the filing it
is about, and a filing's members have to arrive in filed order because that order is part of what
the filer submitted; the adapter never sorts them. Each artifact is preceded by a bare
`SOURCE ARTIFACT: <filename>` text block, and the prompt tells the model those labels are transport
identifiers rather than meaning.

### Normalisation table

| Converse observation | Normalized onto `ModelResponse` | Rule applied |
|---|---|---|
| `output.message.content[].text` | `text` | concatenated in block order |
| `reasoningContent.reasoningText.text`, or a bare `reasoningContent.text` | `reasoning_text` | both known shapes read; never merged into `text` |
| `usage.inputTokens` / `usage.outputTokens` | `input_tokens` / `output_tokens` | an absent count becomes 0, never an estimate |
| `stopReason` | `stop_reason` | recorded verbatim, unreported becomes empty |
| `stopReason == "max_tokens"` | `truncated = True` | whatever the visible text looks like |
| `ResponseMetadata.RequestId` | `provider_request_id` | absent becomes `None`, never `""` |
| `metrics.latencyMs`, else the local monotonic clock | `latency_ms` | the provider's own figure wins |
| the built request envelope | `transport_request` | image bytes replaced by digest and count |
| the raw response payload | `transport_response` | preserved as returned |

A provider that changes the nesting of a reasoning block costs a missing field, not a silent
misattribution of reasoning into the answer. Image bytes are elided from the request envelope by
digest and byte count rather than base64-inlined, because the exact bytes are already preserved as
their own evidence object beside it — the request stays fully reconstructible without carrying every
artifact twice.

## Error normalization

An incompatible filing/model pairing is not a provider error. It is refused before invocation,
explained to the user with bytes, tokens and the limit, and costs nothing. The user may select a
different compatible model; the system may not.

Every provider failure becomes a `ProviderError` carrying the provider name and a retryable flag.
The SDK's own exception type never escapes the adapter. Classification reads the service ERROR CODE
or the EXCEPTION TYPE NAME — never the message text, because a retryable-sounding word in a sentence
is not a transient condition and treating it as one buys a second identical failure.

| Provider condition | Retryable |
|---|---|
| `ThrottlingException`, `TooManyRequestsException` | yes |
| `ModelNotReadyException` — a first-use provisioning delay | yes |
| `ModelTimeoutException`, `RequestTimeout`, `RequestTimeoutException` | yes |
| `ServiceUnavailableException`, `InternalServerException` | yes |
| transport failures by exception name: `EndpointConnectionError`, `ConnectTimeoutError`, `ReadTimeoutError`, `ConnectionClosedError`, `IncompleteReadError` | yes |
| a validation error, an unsupported source, a context overflow, an access denial | no |
| model not found or not enabled | no |
| content filtered by the provider | no |

Everything not named above is treated as permanent. The same request would fail the same way, and
retrying it is spending money to learn nothing.

## Cost calculation

**The arithmetic happens in exactly one place.** A caller holding the reviewed price from the
capability snapshot passes `cost` to `LlmGateway.invoke` — a function of the MEASURED token counts —
and the `Decimal` it returns is what `packages/model_catalog.PriceInputs.cost` computed. The
`PricingRegistry` remains the fallback for the mock provider and for callers with no snapshot, and
it is never consulted for a model whose real price is known. Two homes for one number is how they
drift, and this one ends up on a bill.

`PricingRegistry` raises on an unregistered model rather than defaulting to zero. A model whose
price is unknown must not be invocable, because an unknown cost is not a small cost.

`InvocationRecord.cost_usd` is a `Decimal`. It used to be a float, and Phase 1 established that
`Decimal(0.00015)` is `0.000149999999999999993145` because that is what the binary double holds —
in the one record a reviewer reads.

The pre-spend budget guard estimates input tokens with ONE ratio for the system prompt, the compiled
payload and every preserved TEXT block. An IMAGE block contributes nothing to that estimate: no
measured bytes-to-tokens relationship for a filed raster exists in this project, and inventing one
would make the guard confidently wrong in the unsafe direction. That measurement is PENDING.

## Mock provider

Returns deterministic YAML so the full pipeline, including boundary validation, safe parsing, and
audit persistence, is exercised without network access or spend. Used in every test and in local
development.

The fixture asserts no artifact contract. Its predecessor was a footnote-summary document with a
fixed taxonomy, which quietly made the mock the de facto response schema; that is exactly the drift
ADR-0016 and ADR-0017 were written about. What the fixture has to be is a well-formed, unfenced
YAML 1.2 mapping — and nothing more.

---

## A rejected response is evidence, not an exception — added 2026-08-03, Phase 2

`LlmGateway.invoke(..., strict_response=True)` is the default and keeps the original behaviour: a
response that fails the boundary validator or the safe YAML parser is recorded in the audit row and
then raised.

Parser evaluation needs the other mode. `strict_response=False` records the identical violation,
returns `GatewayResult` with `boundary_violation` set and `raw_text` holding the exact response
bytes, and leaves `parsed` as `None`.

**The response is still refused.** Nothing unparsed is promoted into an artifact, and no violation
is downgraded. It is refused VISIBLY instead of being thrown away, because:

```
that response was BOUGHT and cannot be regenerated for free;
the question a reviewer has to answer — is the prompt wrong, or is this model wrong for this
filing — is unanswerable once the only evidence is gone; and
a stack trace is not a measurement.
```

The orchestrator invokes with `strict_response=False` for exactly that reason. The exact bytes
become durable BEFORE any claim is made about them, the job still advances through `VALIDATING` to
`READY_FOR_REVIEW`, and a person looks at the response beside the filing it came from. A run that
spent money and recorded nothing is the outcome this mode exists to prevent.

---

## Verified capabilities live in one place — added 2026-08-03, Phase 1

The abstraction above describes how a provider is called. What a specific model can actually do —
its real identifier, the regions it answers in, whether it needs an inference profile, whether it
truly accepts images, its context and output limits, and its official price inputs — is EVIDENCE,
dated, and is recorded in exactly one file:

`bedrock-capability-snapshot.yaml`

`packages/model_catalog` is the only code that reads it, and it carries no model identifier, no
region, no limit and no price of its own. An architecture test parses shipped source and fails on a
provider identifier or region literal, for the same reason the qualifying-form set is supplied
rather than hardcoded.

**Do not copy a capability into this document, into `techspecs.md`, or into a provider adapter.** A
capability recorded twice drifts, and the copy is always the one that gets believed. The Bedrock
adapter is now IMPLEMENTED and this rule is unchanged by that: the adapter is handed an invocation
identifier and a region and uses exactly those.

Reproduce the discovery: `../runbooks/bedrock-capability-discovery.md`.
Why a snapshot rather than an adapter: `../adr/ADR-0018-verified-capability-snapshot-over-a-provider-adapter.md`.
