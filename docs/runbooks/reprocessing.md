# Runbook: reprocessing

SEVERITY: routine

## Principle

Every derived artifact is a pure function of preserved raw sources. Reprocessing never re-fetches
from SEC, so it costs no rate-limit budget and cannot be throttled.

## Scopes

```
one filing            a parse or grouping fix
one issuer            a metric definition change affecting that issuer
one era               an era-specific parser fix
one prompt version    a summarization prompt change
whole corpus          a schema change
```

## Procedure

1. Choose the narrowest scope that covers the change.
2. Bump the relevant version: parser, grouping, formula, or prompt. The version is part of the
   idempotency key, so bumping it is what makes the work run again.
3. Enqueue at low priority. Reprocessing must never starve user-requested work.
4. Monitor coverage counters. Coverage should return to its prior level or better; a fall means
   the change regressed something.

## Summaries

Reprocessing creates a new summary version and supersedes the previous one. Accepted historical
outputs are never overwritten, so a regression is recoverable by reactivating the prior version.

## Cost

Corpus-wide summarization reprocessing costs a full backfill. Confirm the benchmark justifies it
before enqueuing, and prefer a sampled validation first.
