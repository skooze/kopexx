# Runbook: model provider outage

SEVERITY: medium; the dashboard is unaffected by design

## What is and is not affected

Unaffected: ticker search, charts, filing browsing, footnote summaries already stored, and every
other dashboard path. **Ordinary dashboard access never invokes a model**, which is precisely why
a provider outage is not a product outage.

Affected: new summarization batches, and Deep Analysis sessions.

## Procedure

1. Confirm the outage is provider-side rather than a credential or quota problem. A normalized
   `ProviderError` with a retryable flag distinguishes transient failure from a permanent
   configuration error.
2. Pause summarization batch submission. Queued work persists; nothing is lost.
3. Deep Analysis returns `MODEL_UNAVAILABLE` with a clear message. Do not silently fall back to a
   different model: `rules.md` forbids unlogged fallback, and a different model changes the
   analysis in ways a user cannot see.
4. If a fallback model is genuinely wanted, activate it explicitly through configuration so the
   invocation record names the model that actually answered.

## Recovery

Resume batch submission. Verify the first batch completes and validates before releasing the full
queue.

## Regional failover

Model access region is configuration. Failing over changes the model identifier and possibly the
tokenizer, so cost accounting and the benchmark are re-verified rather than assumed to carry
over.
