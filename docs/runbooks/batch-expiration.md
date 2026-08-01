# Runbook: expired model batch

SEVERITY: medium; silent if unmonitored, which is the actual danger

## Why this matters

Batch requests expire. An expired request is **not billed** and returns a distinct expiry status
rather than an error. Without a watchdog it leaves a hole in the corpus that looks exactly like
completion.

## Symptoms

Footnote coverage below 100 percent on a filing whose job records show no failures. Batch job
records showing submitted counts above returned counts.

## Procedure

1. Query jobs in `SUMMARIZING` past the expected completion window.
2. Fetch the batch result set and count expiry statuses.
3. Re-queue expired requests. The idempotency key includes the source hash, prompt version, and
   model, so re-queuing is safe and does not duplicate accepted summaries.
4. Confirm the filing's footnote coverage returns to complete.

## Prevention

The watchdog runs on a schedule shorter than the expiry window and re-queues automatically. Alert
when the expiry rate exceeds the configured threshold, because a rising rate usually means batches
are packed too large or submitted too close to a provider capacity limit.

Pack batches by measured payload bytes with headroom, not by request count.
