# Model Abstraction

IMPLEMENTATION STATUS: IMPLEMENTED for the provider interface and the mock provider; a real
provider adapter is PLANNED for Phase 2 and blocked on Phase 1
OWNER PACKAGE: `packages/llm_gateway`

## Principle

**The USER selects the model, per job, for each of the four roles independently.** Application code
never hard-codes a provider model identifier, never substitutes one model for another, and never
falls back silently. An identifier reaches the adapter as configuration or as an explicit user
selection, and a model swap changes no code.

## Interfaces

The complete provider surface, in `packages/llm_gateway/providers/base.py`.

```
ModelRequest             model_id, system_text, user_content, user_content_format,
                         max_output_tokens

ModelResponse            text, input_tokens, output_tokens, model_id, provider,
                         stop_reason, truncated

ModelProvider.invoke(request) -> ModelResponse
ModelProvider.count_tokens(text) -> int | None
```

`user_content_format` is `plain_text` or `yaml` — the two permitted SYNTHETIC formats. **This
interface has no representation for a preserved SEC artifact sent intact under the original-source
exception**, and it will need one before the first real parsing run. Its shape is not guessed here;
it is designed against a real adapter and a real provider request in Phase 2.

There is no `ModelCapabilities` type. There used to be — `model_id`, `provider`, token limits,
batch, flex and reasoning-effort flags — and it was deleted as dead code: it had no constructor and
no caller anywhere in the repository, and every field in it describes a provider this project has
never reached. **Capability facts are discovered live in Phase 1 and recorded then**, and a type
asserting their existence in advance was a standing invitation to write one down from memory.

Whatever replaces it keeps the original omission: no `supports_structured_output` and no
`supports_native_tools`. Both describe provider features that require JSON at the model boundary and
are unusable in this system regardless of whether a provider offers them (ADR-0013). Their presence
would invite a call site to branch on them.

## AWS identity — binding on the Bedrock adapter

The Bedrock provider, when written, uses the AWS SDK default credential provider chain. It accepts
region and model identifiers as configuration and optionally a non-secret profile name. It never
accepts access-key or secret-key parameters, never constructs a client with explicit credential
values, never reads credentials from `.env`, never caches them, and never writes them into an
invocation record.

The mock provider requires no AWS identity and must keep working without one, so the default test
suite never needs AWS access.

Full requirements, including the preflight identity report and its prohibited fields:
`docs/security/aws-identity-and-secrets.md`.

## Provider responsibilities

Only a provider adapter may import a provider SDK, enforced by
`test_bedrock_client_not_imported_outside_provider`.

A provider adapter: translates a `ModelRequest` into its SDK call, normalizes usage accounting,
normalizes errors into `ProviderError` with a retryable flag, and reports an exact token count when
the provider offers one.

A provider adapter does **not**: build model-visible content, validate the boundary, decide
retries, or calculate cost. Those belong to the gateway.

## Error normalization

An incompatible filing/model pairing is not a provider error. It is refused before invocation,
explained to the user with bytes, tokens and the limit, and costs nothing. The user may select a
different compatible model; the system may not.

| Provider condition | Normalized | Retryable |
|---|---|---|
| Throttling | `ProviderError` | yes |
| Transient service error | `ProviderError` | yes |
| Timeout | `ProviderError` | yes |
| Model not found or not enabled | `ProviderError` | no |
| Input too large | `ProviderError` | no |
| Content filtered by the provider | `ProviderError` | no |

## Cost calculation

`PricingRegistry` raises on an unregistered model rather than defaulting to zero. A model whose
price is unknown must not be invocable, because an unknown cost is not a small cost.

## Mock provider

Returns deterministic YAML so the full pipeline, including boundary validation, safe parsing, and
audit persistence, is exercised without network access or spend. Used in every test and in local
development.

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
capability recorded twice drifts, and the copy is always the one that gets believed.

Reproduce the discovery: `../runbooks/bedrock-capability-discovery.md`.
Why a snapshot rather than an adapter: `../adr/ADR-0018-verified-capability-snapshot-over-a-provider-adapter.md`.
