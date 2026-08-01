# Runbook: parser regression

SEVERITY: high, because it can silently corrupt many filings

## Symptoms

Footnote counts shift for filings that previously reconciled. Confidence distribution moves.
Review backlog rises sharply after a deploy.

## Procedure

1. Identify the parser version boundary from the parse records.
2. Run the golden fixtures for every era. A regression usually shows in one era only.
3. Compare the new output against the stored output for the same source hash. Because raw sources
   are preserved, this is a pure re-parse and needs no SEC traffic.
4. Fix, add a golden fixture covering the regression, then reprocess affected filings.

## The silent case to check first

A parser reading only an inline element body without resolving `continuedAt` and `ix:continuation`
chains returns the footnote **title and nothing else**, with no error raised. Measured: one Apple
10-Q has 16 chains up to 3 hops deep.

The detection is the short-block assertion. A note-level text block resolving to an implausibly
short value is a parse failure, not a short note. If the threshold was recently relaxed, that is
the first thing to check.

## Rollback

Pin the previous parser version and reprocess. Preserved raw sources make this a local operation.
