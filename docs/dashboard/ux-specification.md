# Dashboard UX Specification

IMPLEMENTATION STATUS: PLANNED (Sprint 6)
PRODUCT DEFINITION: `docs/architecture/product-definition.md`
API: `docs/api/openapi.yaml`
COMPLETENESS MODEL: `docs/footnotes/completeness.md`

---

## The governing constraint

```
NO-INFERENCE-ON-READ. Every screen, state, and interaction in this document is served entirely
from stored data. Nothing here invokes a language model. The only entry point that spends model
budget is the explicit Deep Analysis action in section 8.
```

A backend architecture does not define a product. This document defines what the investor sees,
including the states most specifications omit: partial, low-confidence, in-progress, and refused.

---

## 1. Issuer search

**Entry.** A single input accepting a ticker or a company name.

**Rule.** A ticker that has never filed a 10-K or 10-Q does not appear in results or
autocomplete. Showing a symbol the product cannot serve is worse than not showing it.

| State | Presentation |
|---|---|
| Match found | Ticker, legal name, exchange, fiscal year end |
| Multiple issuers share a ticker | Disambiguation list showing each issuer's name and the date range it held the ticker. Never auto-select. `BBBY` is two companies |
| Former name matched | Result shows the current legal name with "formerly *X*" |
| Delisted but previously filed | Shown, labelled "no longer listed", still fully browsable |
| Foreign private issuer | Not shown as a result. If typed exactly, an inline notice states that the issuer files Form 20-F and that coverage is limited to domestic 10-K and 10-Q filers |
| No match | "No SEC filer found for *X*." No suggestions invented |

Selecting a result resolves to a CIK. **All subsequent navigation is by CIK.** The ticker is a
display label from that point on.

---

## 2. Issuer overview

Above the fold: legal name, ticker with exchange, CIK, SIC description, fiscal year end, and a
**coverage badge** (section 6).

Then, in order: the timeframe control, the financial charts, the filing timeline, and the
footnote index.

---

## 3. Timeframe behaviour

One control, five options, mapping exactly to the `range` API parameter:

```
Current year    Previous year    5 years    10 years    All-time
```

**"Year" always means the issuer's fiscal year.** Apple's fiscal 2025 ends in September;
comparing it to a calendar year would be wrong. The control labels the actual span it resolved
to, for example `FY2021 – FY2025`, so the user never has to guess.

| Case | Behaviour |
|---|---|
| Current year is partial | Renders with the label "FY2026 (in progress, 2 of 4 quarters filed)" |
| Requested range exceeds available history | Renders what exists and states the true first year: "Data begins FY2011" — never silently shortens the axis |
| Numeric history shorter than document history | The chart states its own boundary: "Charts begin FY2011; filings and footnote summaries reach 1994" |

**Annual/quarterly toggle.** Independent of range. Annual is the default.

- Quarterly series label a derived fourth quarter explicitly: `Q4 FY2025 (derived)`, with a
  tooltip stating that no Q4 10-Q exists and Q4 is computed as FY minus Q1 minus Q2 minus Q3.
- A 52/53-week fiscal year is flagged where it distorts comparison: `FY2023 (53 weeks)`.
- Cash-flow metrics are presented as year-to-date or discrete-quarter, labelled, never mixed.

---

## 4. Financial charts

Deterministic, from published datasets. Never a model call.

| Element | Behaviour |
|---|---|
| Series selection | Curated metrics only, from `metric_definitions/` |
| Point detail | Value, unit, scale, period start and end, duration in months, and the source accession |
| Click-through | Navigates to the footnote that explains that line item, when one is associated |
| Comparability break | A visible marker on the segment where the concept mapping changed, with the reason on hover. The line is not silently redrawn as if nothing happened |
| Restated period | Shows the current value with an indicator that an earlier filing reported a different figure, and links to both |
| Missing period | A gap. Never interpolated, never zero-filled |
| Derived value | Distinct visual treatment plus the `(derived)` label |

**Every number is traceable.** Point detail always exposes the path to `(accession, concept,
context, unit, period)`.

---

## 5. Filing timeline

Reverse-chronological, grouped by fiscal year.

Each entry shows: form type, fiscal period, filing date, period end date, and a per-filing
processing state.

| Marker | Meaning |
|---|---|
| `10-K` / `10-Q` | Form type |
| `10-K/A` | Amendment. Expands to show what it patches. **Never replaces the original in the list** — AMD's 545 KB amendment against a 14 MB original is not a superseding document |
| Era badge | Only where it changes what the user can expect, for example "pre-XBRL: no charts" |

Every entry links to the original SEC document at its authoritative URL.

---

## 6. Coverage and processing states

The single most important honesty requirement in the product: **partial coverage is never
rendered as complete.**

Per filing, from `/filings/{accession}/processing-status`:

```
Footnotes summarized: 13 of 13
Footnotes summarized: 12 of 13 — one footnote is awaiting review
Footnotes: extraction incomplete — this filing is being reprocessed
Footnotes: unavailable — extraction failed, reported and queued
```

| `footnote_status` | Presentation |
|---|---|
| `COMPLETE` | Count shown as *n* of *n*. No warning |
| `PARTIAL` | Count shown as *m* of *n* with the shortfall named. **The missing footnote is listed by number and title with the status "awaiting review", not omitted from the list.** An investor cannot distinguish a footnote that does not exist from one the pipeline dropped, so the product must distinguish them |
| `REQUIRES_REVIEW` | Filing is browsable; affected notes carry a review marker |
| `FAILED` | Filing listed, marked unprocessed, original SEC link still offered |
| `NOT_STARTED` | "Queued for processing" |

The issuer-level coverage badge summarizes: `Coverage: 47 of 51 filings fully processed`.
Clicking it lists the exceptions. It is never rounded up to "complete".

---

## 7. Footnote presentation

### The index

Every canonical footnote for the selected filing, in filed order, showing number as displayed,
title, a one-line summary, and any status marker. **The every-footnote requirement is a UI
requirement too: the index is never filtered by a model's opinion of materiality.**

Optional user-applied filters (`topic`, `classification`, `deep_dive_recommended`) narrow the
view. When any filter is active the header states `Showing 4 of 13 footnotes`, so a filtered
view is never mistaken for the whole set.

### An expanded footnote

```
Note 9 — Debt                                    [ Deep Analysis ]

<plain-language summary>

Key figures      value, unit, scale, period — each linked to its source
Tables           rendered from footnote_table, with the original HTML available
Source           parent block plus every child block, individually addressable
Original         link to the SEC document, anchored to this note
Compare          this note across periods  →  section 9
```

Citations resolve to a source block, a table cell, or a filed fact. **A summary is never itself
offered as evidence for a number.**

### Low-confidence presentation

Confidence is a product-visible property, not an internal one.

| Condition | Presentation |
|---|---|
| Summary passed every validation | No marker. The default |
| `grouping_method` is a fallback stage (6–9) | Note carries "grouping inferred" with the method and what else was considered, from `competing_candidates` |
| `grouping_method` is `model_adjudication` | "Grouping decided by model adjudication", with the model identifier and prompt version |
| `completeness_confidence` below the configured floor | Filing-level banner: "Some structure in this filing could not be determined with confidence" |
| Summary `validation_status` is `REQUIRES_REVIEW` | Summary is **withheld**; the footnote appears with its title, its source text, and "summary awaiting review". Never shown as accepted |
| `reconciliation_status` is `MISMATCH` | Banner naming both numbers: "Table of contents indicates 24 footnotes; 22 were extracted" |
| Source block orphaned | Listed under "unattached source material" on the filing, not hidden |

The rule behind all of these: **uncertainty is surfaced at the point of use, in the same view as
the content it qualifies.** A confidence figure on an internal dashboard protects nobody.

---

## 8. Deep Analysis entry points

Three, matching the three scope types: from a footnote, from a filing, from a timeframe
selection. Each is an explicit, labelled action. Nothing starts a session implicitly.

**Before creation** the user sees what they are authorizing:

```
Deep Analysis
Scope     Apple Inc. (CIK 0000320193) — FY2025 Form 10-K
Covers    13 footnotes, financial facts, derived metrics for this filing
Limits    20 turns, $2.00 maximum
Cannot    retrieve data for any other issuer
[ Start ]  [ Cancel ]
```

**During the session:**

| Element | Behaviour |
|---|---|
| Scope badge | Persistent, naming issuer and period. Never collapsed or hidden |
| Budget meter | Turns used and spend against limit, updated per turn |
| Citations | Every material claim links to the original source |
| Selected-evidence disclosure | An all-history session states plainly that it reasoned over selected evidence and which periods it examined |
| Suggested follow-ups | Only questions answerable within the existing scope |

**Out-of-scope request:**

```
That question is about Microsoft. This session is locked to Apple Inc.
Within this session I can compare Apple across FY2021–FY2025.
To analyse Microsoft, start a new session from that company's page.
```

Refused in one sentence, states what *is* possible, and — when the deterministic detector caught
it — **costs nothing.** The budget meter does not move. That is the visible proof of
requirement 13.

**Budget exhaustion:**

```
This session has reached its limit of $2.00.
The transcript remains available. Start a new session to continue.
```

The session ends cleanly. It never silently degrades to a weaker model or a shorter context.

**Session restoration.** An expired or closed session reopens as a **read-only transcript** with
every citation still resolving. Continuing requires a new session, which re-derives scope from
current data. The UI states this rather than appearing broken.

---

## 9. Same-footnote comparison across periods

Journey 3, specified in `docs/footnotes/period-comparison.md`. From any footnote: "compare this
note across periods".

Presents the same footnote topic for each period in the selected range, side by side, with:

- the summary for each period
- a `changed` / `unchanged` / `absent` / `new` marker per period, computed deterministically
- for changed periods, what changed, from stored comparison records
- links to each original source

**No model call.** The comparison is precomputed and stored. This is what backs the
`classification=changed` filter in section 7.

---

## 10. Cross-cutting states

| State | Presentation |
|---|---|
| Issuer never filed | Unreachable by design — excluded from search |
| Issuer exists, no filings processed yet | Identity and timeline render; charts and footnotes show "queued for processing" |
| Data being republished | Last published version continues to serve. The pointer flip is atomic; the user sees no partial dataset |
| API error | Plain statement of what failed and what still works. Never a blank chart implying zero |
| Empty filter result | "No footnotes match this filter" with a one-click reset |

---

## 11. Accessibility and presentation floor

Charts are readable without colour alone: markers and labels carry the meaning that colour
reinforces. Every status marker has a text equivalent. Tables are navigable by keyboard and
carry proper headers. Numbers are never conveyed by position alone.

---

## 12. Acceptance tests

| Test | Assertion |
|---|---|
| `test_dashboard_session_invokes_no_model` | A full browse — search, overview, chart, timeframe change, filing open, every footnote expanded, filter applied — records **zero** `llm_invocation` rows |
| `test_partial_filing_renders_honestly` | A filing with 12 of 13 summaries shows *12 of 13* and lists the thirteenth as awaiting review |
| `test_missing_footnote_is_listed_not_omitted` | The unsummarized footnote appears in the index with its title |
| `test_never_filed_ticker_absent_from_search` | A symbol with no 10-K or 10-Q returns no result |
| `test_reused_ticker_disambiguates` | `BBBY` offers both issuers with date ranges; neither is auto-selected |
| `test_derived_q4_is_labelled` | A quarterly series marks Q4 as derived |
| `test_low_confidence_grouping_is_surfaced` | A fallback-stage grouping shows its method in the UI |
| `test_requires_review_summary_is_withheld` | An unvalidated summary is not rendered as accepted |
| `test_out_of_scope_request_costs_nothing` | The budget meter is unchanged after a refused cross-ticker request |
| `test_expired_session_restores_read_only` | Transcript renders; the input is disabled with an explanation |
