# Model Abstraction

IMPLEMENTATION STATUS: IMPLEMENTED for the interface and the mock provider; Bedrock adapter PLANNED
OWNER PACKAGE: `packages/llm_gateway`

## Principle

Application code selects a model by required capability, never by a hard-coded provider model
identifier. A model swap is a configuration change.

## Interfaces

```
ModelCapabilities        model_id, provider, max_input_tokens, max_output_tokens,
                         supports_batch, supports_flex, supports_reasoning_effort

ModelRequest             model_id, system_text, user_content, user_content_format,
                         max_output_tokens

ModelResponse            text, input_tokens, output_tokens, model_id, provider,
                         stop_reason, truncated

ModelProvider.invoke(request) -> ModelResponse
ModelProvider.count_tokens(text) -> int | None
```

`ModelCapabilities` deliberately has **no** `supports_structured_output` and no
`supports_native_tools` field. Both describe provider features that require JSON at the model
boundary and are therefore unusable in this system regardless of whether a provider offers them
(ADR-0013). Adding those fields would invite a call site to branch on them.

## Provider responsibilities

Only a provider adapter may import a provider SDK, enforced by
`test_bedrock_client_not_imported_outside_provider`.

A provider adapter: translates a `ModelRequest` into its SDK call, normalizes usage accounting,
normalizes errors into `ProviderError` with a retryable flag, and reports an exact token count when
the provider offers one.

A provider adapter does **not**: build model-visible content, validate the boundary, decide
retries, or calculate cost. Those belong to the gateway.

## Error normalization

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
