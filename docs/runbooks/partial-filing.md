# Runbook: filing stuck at PARTIAL

SEVERITY: medium
RELATED: `docs/footnotes/completeness.md`

## Meaning

The filing has canonical footnotes but does not satisfy the completeness invariant. It is never
displayed as complete.

## Diagnose

Read the coverage counters for the filing.

```
canonical_footnotes_extracted vs toc_expected_note_count
summaries_accepted vs canonical_footnotes_extracted
source_blocks_orphaned
summaries_requiring_review
footnotes_missing_source_data
```

## Cases

### Extracted count below the table of contents count

Grouping missed a footnote. Inspect the grouping decisions and the stage that produced them. A
filing whose TOC says 24 and whose extraction says 22 is genuinely incomplete; do not adjust the
expected count to make it reconcile.

### Orphaned source blocks

A child block found no parent. Review the candidates and the scores each fallback stage produced.
Never force-attach to make a count balance; attach on evidence or leave it in review.

### Summaries below extracted count

Check validation outcomes. Numeric mismatch and unresolvable citation are the common causes. Fix
the underlying data or re-run the summary; do not lower the validation bar.

### Missing source data

The footnote was identified but its text is unavailable, usually a parse failure upstream.
Reprocess from the preserved raw source.

## Resolution

Re-run only the failed stage. Every stage is idempotent, so a re-run does not duplicate accepted
work.

## What not to do

Do not mark the filing complete manually. Do not delete the footnote that has no summary. Both
convert a visible gap into an invisible one.
