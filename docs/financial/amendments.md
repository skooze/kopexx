# Amendments

IMPLEMENTATION STATUS: PLANNED (Phase 4)
DECISION RECORD: `docs/adr/ADR-0010-amendments-as-patches.md`

## The evidence against the intuitive model

"A 10-K/A supersedes the 10-K" is false often enough to be dangerous.

AMD's 10-K/A, accession `0000002488-26-000021`, is **545,192 bytes against the original's
14,078,338**. It was filed the same day, carries the same report date, and reuses the same primary
document filename.

NTRB's amendment is a 95 KB document containing one text block of four characters and no Item 1A
content at all.

In one recent quarter, 373 amendments were filed against 621 original annual reports.

Replacing the original with the amendment blanks the dashboard for every amended filer.

## Model

```
filing_amendment
  amendment_filing_id        uuid references filing
  amends_filing_id           uuid references filing
  amendment_form             text          -- 10-K/A, 10-Q/A, 10-KT/A
  is_complete_replacement    boolean
  sections_changed           text[]
  footnotes_changed          uuid[]
  facts_changed              uuid[]
  patch_confidence           numeric
  detected_by                text          -- content_diff | filer_statement | manual
  created_at                 timestamptz
```

Both filings persist and remain independently retrievable.

## Complete versus partial detection

An amendment is treated as a complete replacement only when it contains a full set of financial
statements and a footnote count comparable to the original. Detection is heuristic, records a
confidence, and routes low confidence to review. **The default when uncertain is partial**,
because treating a partial amendment as complete destroys content while the reverse merely shows
slightly stale content alongside a patch.

## Views

```
as_filed        the original document exactly as filed
current         original with all applicable patches applied
amendment_only  what the amendment itself contains
```

The dashboard defaults to `current` and labels it, offering `as_filed` alongside.

## Footnotes and summaries

An amended footnote receives a **new summary version**. The original version is superseded, not
deleted, so the summary history shows what was said before and after the amendment.

## Tests

```
test_amd_amendment_does_not_blank_the_original     uses the real 545KB-vs-14MB case
test_ntrb_near_empty_amendment_is_partial
test_amended_footnote_supersedes_summary_version
test_original_summary_remains_retrievable
test_uncertain_amendment_defaults_to_partial
```
