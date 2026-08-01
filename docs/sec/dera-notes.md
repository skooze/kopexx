# DERA Financial Statement and Notes Data Sets

IMPLEMENTATION STATUS: discovery, ledger, and bulk mirror IMPLEMENTED and EXECUTED (Sprint 2).
All 78 packages held locally, 25.36 GiB. TSV loading PLANNED (Sprint 3).
OWNER PACKAGE: `packages/dera_notes`
DECISION RECORD: `docs/adr/ADR-0001-dera-notes-primary-source.md`
RUNBOOK: `docs/runbooks/dera-mirror.md`

## Why this is the primary source

NOTES is a strict superset of the plain Financial Statement Data Sets. On one Boeing 10-K the
plain sets carry 623 numeric facts across 146 tags; NOTES carries 2,477 facts across 620 tags,
with zero plain-set tags absent from NOTES. Every plain-set accession for the sampled month also
appears in NOTES. The plain sets are therefore not ingested at all, saving 5.2 GB and a redundant
schema.

NOTES additionally carries footnote narrative text with the filer's own titles, presentation
ordering, and disclosure metadata.

## The deadline

**SEC retains only a rolling twelve months of monthly packages and deletes them once consolidated
into quarterly packages.** A period reachable only as a monthly becomes permanently unreachable if
deleted before its quarterly consolidation is published.

The mirror therefore **retains monthly packages even after the corresponding quarterly arrives**,
and comparing monthly against quarterly coverage is an explicit reconciliation step rather than an
assumption.

This is the only task in the project with an external deadline. It is roadmap item URGENT-01.

## Discovery rules

**Filenames are scraped from the authoritative listing page. They are never generated.**

Three 2010 packages carry irregular numeric suffixes: `2010q1_notes_1.zip`,
`2010q2_notes_0.zip`, `2010q3_notes_0.zip`. A generated-name downloader requesting
`2010q1_notes.zip` receives a 404 and records a gap that does not exist.

The metadata filename inside a package is also vintage-specific: recent packages contain
`notes-metadata.json` while 2009 packages contain `2009q1_notes-metadata.json`. Glob for
`*metadata.json`.

Discovery raises rather than returning an empty list when the listing yields no packages, because
silent zero-discovery is indistinguishable from "nothing new to mirror".

## Parsing rules

**Parse the TSV members with quoting disabled.** Values contain unescaped double-quote characters
that corrupt a standard CSV reader. Values contain no embedded newlines, so line count equals row
count and the file can be split safely.

**`readme.htm` inside the packages is stale and actively misleading.** It documents a `txtlen`
truncation at 8192 characters that no longer applies; values of 287,406 characters have been
measured.

**`num` is not contiguously sorted by accession.** In one quarter, 3,690,955 rows form 123,720
runs across only 6,169 distinct accessions. An early-exit scan that stops at the first
non-matching accession returned 13 of one issuer's 323 rows. Always scan fully or index first.

**Filter `segments = ''` and `coreg = ''`** for consolidated figures, or segment-level breakdowns
mix with consolidated totals. Only 171 of one Apple 10-Q's 323 `num` rows are consolidated.

**Quarterly `pre` contains zero abstract elements.** Header rows such as "Operating expenses:" are
stripped, so line numbers jump 9 to 11 and 18 to 20. Presentation reconstruction must tolerate
gaps rather than assuming contiguity.

## Table roles

| Member | Carries | Used for |
|---|---|---|
| `sub` | Submission metadata, one row per filing | Filing identity, period, form |
| `num` | Numeric facts | The fact lake |
| `pre` | Presentation ordering and statement grouping | Statement reconstruction |
| `tag` | Tag definitions including custom flag | Extension concept identification |
| `cal` | Calculation relationships | Parent-child indentation, subtotals |
| `ren` | Renderer report inventory | Canonical footnote candidates, titles, menu category |
| `dim` | Dimensional qualifiers | Segment and axis handling |
| `txt` | Footnote narrative text | Footnote source blocks |

`txt.value` is markup-stripped, so embedded tables collapse to unstructured text. It is LLM and
search input only. Human-readable footnote rendering uses the filing's own `R*.htm` fragment,
addressed through `ren.report`.

## Publication lag

Typically 3 to 13 days after period end, but observed to slip to 46 and 62 days. One quarterly
package was 404 more than a month past its normal cadence. Cadence is never hardcoded, and the
companyfacts freshness patch is not optional.

## Mirror provenance

Each mirrored package records:

```
filename          url               cadence        period
sha256            size_bytes        retrieved_at   storage_key
format_version
```

Resumability is a ledger property: `MirrorLedger.pending(packages)` returns only unmirrored
packages, so a killed run resumes and a completed run downloads nothing.

## Tests

IMPLEMENTED:

```
test_dera_links_are_scraped                       test_dera_filename_not_generated
test_irregular_suffixes_classify_correctly        test_dera_mirror_is_resumable
test_empty_listing_raises_rather_than_returning_nothing
test_monthly_packages_retained_alongside_quarterly
test_dera_discovery_resolves_absolute_urls
test_mirror_run_is_idempotent                     test_mirror_records_full_provenance
```

PLANNED Sprint 2: TSV parsing with quoting disabled, `txt` extraction, monthly-versus-quarterly
coverage reconciliation, and replay into a fresh schema.
