# DERA Financial Statement and Notes Data Sets

IMPLEMENTATION STATUS: discovery, ledger, and bulk mirror IMPLEMENTED and EXECUTED (Sprint 2).
All 78 packages held locally, 25.36 GiB. TSV loading, normalization, validation, and
reconciliation IMPLEMENTED and EXECUTED (Sprint 3): 2,845 facts across four Apple filings.
OWNER PACKAGE: `packages/dera_notes`
DECISION RECORD: `docs/adr/ADR-0001-dera-notes-primary-source.md`
RUNBOOKS: `docs/runbooks/dera-mirror.md` (mirroring), `docs/runbooks/dera-fact-load.md`
(loading a filing's facts), `docs/runbooks/dera-backup-mount.md` (the second copy)

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

**A filing belongs to the package for the period it was SUBMITTED in, not the period it reports
on.** Apple's FY2025 10-K covers a year ending 2025-09-27 and was filed 2025-10-31, so it is in
`2025_10_notes.zip`, not `2025q3`. Never derive the package from a report date. `locate_filing`
reads each candidate's `sub.tsv` and answers from the data, because this is exactly the kind of
off-by-one-quarter error that produces a confident, wrong, silent result: the load finds nothing
and reports a filing with no facts, which is indistinguishable from a filing that has none.

Where a filing appears in both a monthly package and the quarterly consolidation, prefer the
quarterly one. Monthlies are deleted upstream, so a load whose recorded provenance names a monthly
package becomes unreproducible from SEC once that deletion happens.

**`num` is not contiguously sorted by accession.** In one quarter, 3,690,955 rows form 123,720
runs across only 6,169 distinct accessions. An early-exit scan that stops at the first
non-matching accession returned 13 of one issuer's 323 rows. Always scan fully or index first.

**Filter `segments = ''` and `coreg = ''`** for consolidated figures, or segment-level breakdowns
mix with consolidated totals. Only 171 of one Apple 10-Q's 323 `num` rows are consolidated. In the
loader this is `dimensions = '{}'::jsonb`, which the partial index
`ix_xbrl_fact_consolidated_series` selects on. `num.dimh` is an opaque hash, not the dimensions
themselves: `dim.tsv` is the lookup, and without joining it every dimensional fact is stored as if
it were consolidated. 547 of the FY2025 10-K's 967 facts are consolidated.

**`num.tsv`'s primary key is `(adsh, tag, version, ddate, qtrs, uom, dimh, iprx, coreg)`.** All
nine parts are needed. `dimh` separates dimensional variants of one concept, and `iprx` exists
precisely because DERA emits rows that collide on everything else. This tuple is the loader's
natural key and the whole basis of its idempotency.

**Period boundaries are normalized, not filed.** `ddate` is rounded to the nearest month end,
`qtrs` is a whole number of quarters, and DERA publishes the residuals separately as `datp` and
`durp`. A period START is not published at all. Apple's FY2025 ended 2025-09-27; DERA records
2025-09-30. So a DERA period is an approximation by design, and the exact filed context lives in
the XBRL instance document.

The loader derives `period_start` as the first day of the month `qtrs * 3 - 1` months before
`ddate`. Subtracting whole months and adding a day is NOT equivalent: 30 June minus three months
clamps to 30 March, because March has 31 days, and the derived quarter then starts a day short.
That defect is invisible on annual periods ending 30 September and wrong on every quarter ending
in a 30-day month.

**A row with no value is not a defect.** DERA emits rows whose value is genuinely absent — the
shape it uses for a line-item label such as `CommitmentsAndContingencies`. Two of the FY2025
10-K's 969 matching rows are these. They are counted and named as rejections, never silently
dropped, because "rows read = rows accepted + rows rejected" is what proves nothing was lost.

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

## Loading a filing's facts

```
python scripts/load_dera_partition.py 0000320193-25-000079            # loads and reconciles
python scripts/load_dera_partition.py 0000320193-25-000079 --dry-run  # parses only, no database
```

Per accession, not per package. `xbrl_fact` has foreign keys to `issuer` and `filing`, so loading a
whole monthly package would first require registering its 7,098 submissions as issuers and filings
— Stage 2 phase W-1, out of scope by ADR-0015.

The load is one transaction covering insertion, the row counts, and the `dera_package.loaded_at`
update, serialized against concurrent loaders of the same accession by a transaction-scoped
advisory lock. `loaded_at` records what happened; it never authorises a skip, because a flag set
by a run that half-failed would make the gap permanent and invisible.

The script exits non-zero unless all nine reconciliation checks pass:

```
every_matched_row_is_accounted_for   accepted + rejected = rows read for this accession
database_row_count_matches_accepted  a short load is otherwise invisible
natural_key_is_unique_in_database    a repeat means a rerun would double-count
distinct_concepts_match              catches a whole tag dropped by normalization
numeric_total_matches                Python's sum against PostgreSQL's, within NUMERIC(38,6)
consolidated_split_matches           dimensional facts must not enter the consolidated series
period_type_split_matches            catches a misread qtrs moving a fact between series
every_dimension_hash_resolved        a dimh absent from dim.tsv means the package is inconsistent
no_duplicate_natural_keys_in_source  DERA documents this tuple as num.tsv's primary key
```

## Tests

IMPLEMENTED. 105 across mirror and load; see `techspecs.md` section 3.6 for the per-file counts.

```
test_dera_links_are_scraped                       test_dera_filename_not_generated
test_irregular_suffixes_classify_correctly        test_dera_mirror_is_resumable
test_empty_listing_raises_rather_than_returning_nothing
test_monthly_packages_retained_alongside_quarterly
test_dera_discovery_resolves_absolute_urls
test_mirror_run_is_idempotent                     test_mirror_records_full_provenance

test_a_quote_character_is_data_not_a_delimiter
test_an_embedded_quote_does_not_swallow_the_next_column
test_the_package_is_chosen_by_reading_sub_tsv_not_by_deriving_a_period
test_the_quarterly_package_wins_a_tie_because_monthlies_are_deleted_upstream
test_the_derived_start_is_not_a_day_short_when_the_end_month_is_shorter
test_derived_starts_cover_every_quarter_end_without_gap_or_overlap
test_the_natural_key_separates_dimensional_variants
test_the_natural_key_separates_dera_duplicate_facts
test_a_dimensional_fact_does_not_land_in_the_consolidated_series
test_a_rerun_inserts_nothing
test_a_package_whose_bytes_changed_since_mirroring_is_refused
test_facts_are_written_unvalidated_because_nothing_has_validated_them
```

PLANNED Sprint 2: TSV parsing with quoting disabled, `txt` extraction, monthly-versus-quarterly
coverage reconciliation, and replay into a fresh schema.
