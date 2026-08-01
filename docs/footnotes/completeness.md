# Footnote Completeness

IMPLEMENTATION STATUS: PLANNED (Sprint 4)

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

Exposed through the processing-status API. **Most are derived, not stored.**

A count that can be recomputed from child rows is never also stored on the filing: a stored copy
is a second source of truth that goes stale the moment a summary is superseded or a block is
re-attached. Only judgements produced by the extraction run — values with no child rows to
recompute from — are persisted.

### Derived at query time

| Counter | Derivation |
|---|---|
| `canonical_footnotes_extracted` | `COUNT(canonical_footnote WHERE filing_id = F AND is_valid)` |
| `source_blocks_associated` | `COUNT(footnote_source_block WHERE filing_id = F AND footnote_id IS NOT NULL)` |
| `source_blocks_orphaned` | `COUNT(footnote_source_block WHERE filing_id = F AND footnote_id IS NULL)` |
| `tables_associated` | `COUNT(footnote_table WHERE filing_id = F AND footnote_id IS NOT NULL)` |
| `summarization_jobs_created` | `COUNT(processing_job WHERE filing_id = F AND type = 'summarize_footnote')` |
| `summaries_accepted` | `COUNT(footnote_summary WHERE ... AND superseded_at IS NULL AND validation_status IN (VALIDATED, VALIDATED_NORMALIZED))` |
| `summaries_failed` | `COUNT(footnote_summary WHERE ... AND validation_status = 'FAILED')` |
| `summaries_requiring_review` | `COUNT(footnote_summary WHERE ... AND validation_status = 'REQUIRES_REVIEW')` |
| `footnotes_missing_source_data` | `COUNT(canonical_footnote WHERE filing_id = F AND text IS NULL)` |
| `extraction_method` | modal `grouping_method` over the filing's canonical footnotes |
| `orphan_block_count` | same as `source_blocks_orphaned`; named separately in the invariant above |

### Stored on `filing`

| Column | Why it cannot be derived |
|---|---|
| `toc_expected_note_count` | Read from the table of contents at extraction time. Nothing else records what the document claimed |
| `reconciliation_status` | `RECONCILED` \| `MISMATCH` \| `NOT_ATTEMPTED`. A filing with no parseable TOC is not the same as one that reconciled, and a count cannot distinguish them |
| `completeness_confidence` | A judgement combining grouping confidences, reconciliation outcome, and source availability. Not a count |
| `footnote_status` | The computed verdict, materialized so the dashboard does not re-evaluate the full invariant on every read |

> Corrected after the Sprint 2 alignment review. The original text said all thirteen counters
> were "recorded per filing", while the schema stored two of them. Rather than adding eleven
> denormalized columns, the derivable ones are now documented as derived and the two genuine
> gaps were added to the schema.

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
