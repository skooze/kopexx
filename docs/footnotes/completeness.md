# Footnote Completeness

IMPLEMENTATION STATUS: PLANNED (Phase 1)

## The requirement

Every actual financial-statement footnote in every processed 10-K and 10-Q has exactly one
canonical record and exactly one active accepted summary. Routine footnotes get shorter
summaries. No footnote is omitted because a model judged it immaterial.

## The invariant

```
filing.footnote_status = COMPLETE  if and only if

    count(canonical_footnote where filing_id = F and valid)
      == count(footnote_summary where filing_id = F
               and superseded_at is null
               and validation_status in (VALIDATED, VALIDATED_NORMALIZED))

  and (toc_expected_note_count is null
       or toc_expected_note_count == count(canonical_footnote where filing_id = F and valid))

  and count(footnote_source_block where filing_id = F
            and canonical_footnote_id is null) == 0
```

The third clause matters: an unattached source block means part of a footnote was extracted but
never assigned to one, so the filing is not fully represented even if every extracted footnote has
a summary.

## Tracked counters

Recorded per filing and exposed through the processing-status API.

```
toc_expected_note_count           what the table of contents indicated
canonical_footnotes_extracted     what grouping produced
source_blocks_associated          child blocks attached
source_blocks_orphaned            child blocks with no parent
tables_associated                 tables attached
summarization_jobs_created        one per canonical footnote
summaries_accepted                passed every validation stage
summaries_failed                  failed and exhausted retries
summaries_requiring_review        routed to a human
footnotes_missing_source_data     footnote identified but its text is unavailable
completeness_confidence           0.0 to 1.0
extraction_method                 which grouping stage dominated
reconciliation_status             RECONCILED | MISMATCH | NOT_ATTEMPTED
```

## Status values

| Status | Meaning |
|---|---|
| `COMPLETE` | The invariant above holds |
| `PARTIAL` | Footnotes extracted, some without an accepted summary |
| `REQUIRES_REVIEW` | A grouping or validation decision needs a human |
| `FAILED` | Extraction could not produce footnotes at all |

## Dashboard presentation

The true state is always shown:

```
Footnotes summarized: 24 of 24
Footnotes summarized: 23 of 24 — one footnote is awaiting review
Footnotes: extraction incomplete — this filing is being reprocessed
```

Partial coverage is never rendered as complete. A missing footnote is visible as missing rather
than absent from the list, because an investor cannot tell the difference between a footnote that
does not exist and one the pipeline dropped.

## Tests

```
test_no_completed_filing_lacks_a_summary       property test over the corpus
test_toc_mismatch_marks_filing_partial
test_orphaned_source_block_blocks_completion
test_failed_summary_marks_filing_partial
test_dashboard_renders_partial_state_honestly
```
