# The Canonical Footnote Model

IMPLEMENTATION STATUS: PLANNED (model specified; implementation is Sprint 4)
DECISION RECORD: `docs/adr/ADR-0005-canonical-footnote-grouping.md`
ALGORITHM: `docs/footnotes/canonicalization-algorithm.md`

---

## Why this document exists

An earlier version of this architecture asserted that Apple's FY2025 10-K contains 58 note
sections. That number came from counting XBRL TextBlock facts. It is wrong by a factor of 4.5,
and building on it would have produced 58 summaries for a filing that has 13 footnotes,
fragmenting each real footnote across its narrative, policy, table, and detail pieces.

Getting this unit right determines the completeness invariant, the summarization cost, and
whether the dashboard is coherent.

---

## Definitions

These nine things are distinct. Conflating any two of them produces the error above.

### Canonical footnote

One actual financial-statement footnote as a reader of the filing would recognise it: *Note 7,
Income Taxes*. This is the product unit. It is what gets one summary, what appears once in the
dashboard, and what the completeness invariant counts.

### DERA report

One row in the SEC renderer's report inventory for a filing, exposed through `FilingSummary.xml`
and through the DERA `ren` table. A single canonical footnote typically owns several. Apple's
FY2025 10-K has 71 reports for 13 footnotes.

### XBRL role

A URI declared in the filing's schema that groups related facts and presentation relationships,
for example `.../9952156 - Disclosure - Income Taxes`. This is the join key that attaches child
reports to their parent footnote.

### TextBlock fact

One XBRL fact whose concept name ends in `TextBlock`, carrying a span of narrative as its value.
A canonical footnote's narrative may be one TextBlock; its policies, tables, and details are
usually separate TextBlock facts. Apple's FY2025 10-K has 58.

### Policy block

A report or TextBlock carrying an accounting policy disclosure, categorised `Policies` by the
renderer. It belongs to a parent footnote, usually Note 1.

### Detail block

A report categorised `Details`, carrying the granular breakdown behind a footnote's tables. These
are the most numerous: 33 of Apple's 71.

### Table report

A report categorised `Tables`, carrying the tabular content of a footnote. Twelve in Apple's
FY2025 10-K.

### Filing item disclosure

A disclosure required by an SEC form item rather than by accounting standards. These appear in
the renderer's `Notes` category but are not financial-statement footnotes. Apple's FY2025 10-K
has three: Insider Trading Arrangements and Insider Trading Policies and Procedures (Item 408),
and Cybersecurity Risk Management and Strategy (Item 1C).

### Filing section

A narrative section of the filing identified by item number: Item 1 Business, Item 1A Risk
Factors, Item 7 MD&A. These are valuable and separately summarized, but they are not footnotes
and they never substitute for one.

---

## Verified structure, Apple FY2025 10-K

Accession `0000320193-25-000079`, verified 2026-08-01 by direct retrieval.

```
Object                                        Count
-------------------------------------------  ------
XBRL TextBlock facts                             58     <- the earlier error
FilingSummary <Report> elements                  71
Reports with MenuCategory "Notes"                16
Actual numbered footnotes in the document        13     <- the correct unit
```

Report inventory by category:

```
Details      33
Notes        16
Tables       12
Statements    6
Cover         2
Policies      1
uncategorised 1
             --
             71
```

The 13 canonical footnotes and their attached child blocks:

```
Note  1  Summary of Significant Accounting Policies            1 child
Note  2  Revenue                                               4 children
Note  3  Earnings Per Share                                    3 children
Note  4  Financial Instruments                                 4 children
Note  5  Property, Plant and Equipment                         3 children
Note  6  Consolidated Financial Statement Details              3 children
Note  7  Income Taxes                                          6 children
Note  8  Leases                                                4 children
Note  9  Debt                                                  5 children
Note 10  Shareholders' Equity                                  3 children
Note 11  Share-Based Compensation                              4 children
Note 12  Commitments, Contingencies and Supply Concentrations  2 children
Note 13  Segment Information and Geographic Data               4 children
                                                              --
                                                              46 child blocks
```

Excluded from the footnote model and routed to `filing_section`:

```
Insider Trading Arrangements                     Item 408
Insider Trading Policies and Procedures          Item 408
Cybersecurity Risk Management and Strategy       Item 1C
```

Reconciliation: 16 Notes-category reports minus 3 filing-item disclosures equals 13, matching the
13 `Note N` headings parsed independently from the primary document.

Role URI attachment: all 46 Tables, Details, and Policies reports matched a parent by role URI
prefix. Zero unmatched.

---

## Scope of that evidence

This is a **single-filing result**. It must not be presented as a general guarantee.

| Claim | Status |
|---|---|
| Apple FY2025 has 13 canonical footnotes | VERIFIED on one filing |
| Role URI attaches 46/46 child blocks on that filing | VERIFIED on one filing |
| Role URI is a reliable grouping key generally | UNVERIFIED, requires breadth validation |
| Role URI works before 2009 | KNOWN FALSE, role URIs do not exist pre-XBRL |
| Filing agents construct role URIs consistently | UNKNOWN, a plausible failure mode |

Stage 2 phase W-3 validates across at least 25 issuers spanning all four filing eras before scale-out, and
publishes the confidence distribution. Until that runs, the fallback chain is not optional
scaffolding; it is the part of the design that makes the single-filing result safe to build on.

---

## Entity model

```
filing
  |
  +-- canonical_footnote            one per actual footnote; the product unit
  |     |
  |     +-- footnote_source_block   narrative, policy, and detail blocks
  |     +-- footnote_table          tabular content, structurally preserved
  |     +-- canonical_footnote      child footnotes, for multi-part notes
  |     +-- footnote_summary        exactly one active version
  |
  +-- filing_section                Item 1, 1A, 1C, 7, 408 disclosures
```

`footnote_source_block.canonical_footnote_id` is **nullable**. An ungrouped source block is
visible as a defect and appears in the review queue. It is never silently dropped, and it is
never force-attached to an arbitrary parent to make a count reconcile.

---

## The completeness invariant

A filing is fully summarized only when:

```
count(canonical_footnote where valid)
  == count(footnote_summary where active and validation_status in (VALIDATED, VALIDATED_NORMALIZED))
```

and, when the table of contents yielded an expected count, that count matches the number of
canonical footnotes extracted.

Anything else is `PARTIAL` or `REQUIRES_REVIEW`. The dashboard renders the true state:

```
Footnotes summarized: 24 of 24
Footnotes summarized: 23 of 24 — one footnote is awaiting review
```

Partial coverage is never displayed as complete coverage. Per-filing counters tracked:

```
toc_expected_note_count            source_blocks_associated
canonical_footnotes_extracted      tables_associated
summarization_jobs_created         summaries_accepted
summaries_failed                   summaries_requiring_review
footnotes_missing_source_data      completeness_confidence
extraction_method                  reconciliation_status
```

---

## Edge cases the model must handle

| Case | Handling |
|---|---|
| Unnumbered notes | Title becomes the identity; `normalized_number` is null; sequence preserves filing order |
| Lettered notes (Note A, Note B) | `number_as_displayed` keeps the letter; `normalized_number` maps to an ordinal |
| Repeated note numbers | A parse defect or a genuinely restarted numbering; both route to review |
| Multi-part notes (Note 7 and 7A) | Parent with child footnotes, both summarized, child linked to parent |
| Cross-references between notes | Recorded as a relationship, never as a reason to merge two footnotes |
| Historical text-only notes | No role URIs; text-only stages of the chain; lower confidence, surfaced in the UI |
| Amendment footnotes | A patch on the original per ADR-0010; original summary superseded, not deleted |
| Orphan source blocks | `canonical_footnote_id` left null; review queue; never force-attached |
| A filing with zero footnotes | Valid for some amendments; `PARTIAL` only if the TOC expected some |
