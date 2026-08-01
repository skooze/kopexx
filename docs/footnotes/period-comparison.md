# Same-Footnote Comparison Across Periods

IMPLEMENTATION STATUS: PLANNED (Sprint 6)
PRODUCT JOURNEY: `docs/architecture/product-definition.md` — "Scan what changed"
UI: `docs/dashboard/ux-specification.md` section 9
API: `docs/api/openapi.yaml` — `/issuers/{cik}/footnote-topics/{topic_key}`

---

## Why this document exists

"Compare a footnote topic across periods and see which changed" was a stated user journey with
no algorithm, no schema support, and no endpoint. The API nonetheless exposed a
`classification=changed` filter, which meant the interface promised something nothing computed.
This specification supplies the missing mechanism.

The investor question behind it is the real product question: *the debt note changed between
2024 and 2025 — what changed, and why?*

---

## The unit of comparison

Not the footnote number. **Note numbering is unstable across periods**: a note that is Note 9 in
FY2024 may be Note 8 in FY2025 when an earlier note is removed. Comparing by number produces
false change everywhere.

The comparison unit is the **topic key**: a stable identifier for what a footnote is *about*,
derived deterministically and independent of its position in the filing.

```
topic_key resolution, in order of evidence strength

1. ROLE URI STEM       the role URI with the filing-specific prefix stripped.
                       Apple's Debt note carries the same stem in FY2024 and FY2025.
                       Deterministic. Available 2009 onward.

2. DOMINANT CONCEPT    the primary us-gaap TextBlock concept, e.g.
                       us-gaap:DebtDisclosureTextBlock. Stable across filers and years.

3. NORMALIZED TITLE    lowercase, punctuation and stop words stripped, mapped through a
                       curated synonym table ("Debt" / "Borrowings" / "Long-Term Debt"
                       resolve to one key). Used pre-2009 and when 1 and 2 disagree.

4. UNRESOLVED          no key assigned. The footnote is shown, and is simply not offered for
                       comparison. A wrong pairing is worse than no pairing.
```

The synonym table will live in `metric_definitions/footnote_topic_synonyms.yaml`, created in
Sprint 6 alongside the comparison implementation, and reviewed like a metric definition, because
merging two distinct topics silently fabricates a comparison.

---

## Change classification

For each pair of consecutive periods sharing a topic key, one classification is computed and
stored. **This is deterministic. No model is involved.**

| Classification | Condition |
|---|---|
| `NEW` | Topic present this period, absent in the prior period |
| `ABSENT` | Present in the prior period, absent this period |
| `UNCHANGED` | Normalized text hash identical to the prior period |
| `CHANGED_IMMATERIAL` | Text differs only in period labels, figures updated in place, or whitespace |
| `CHANGED_MATERIAL` | Structural or substantive difference — see below |
| `INCOMPARABLE` | Either side is `REQUIRES_REVIEW`, or the topic key is unresolved |

`CHANGED_MATERIAL` requires at least one of:

```
a paragraph added or removed after normalization
a table gaining or losing a row or column category
a concept appearing or disappearing from the note's fact set
a figure changing by more than the configured relative threshold
a new defined term introduced
```

Normalization before hashing removes: whitespace runs, period labels, page artifacts, and the
figures themselves. **Figures are compared separately and explicitly**, so that a note whose
only change is its numbers is `CHANGED_IMMATERIAL` in structure while still reporting which
figures moved.

---

## Stored comparison record

Computed once at publication, never at read time.

```
footnote_comparison
    comparison_id
    issuer_id
    topic_key
    from_filing_id            null when classification is NEW
    to_filing_id
    from_footnote_id
    to_footnote_id
    classification            the vocabulary above
    text_similarity           0.0 to 1.0, normalized
    changed_figures           JSONB: concept, prior value, current value, unit, scale, period
    structural_changes        JSONB: paragraphs and table categories added or removed
    comparison_method         role_uri_stem | dominant_concept | normalized_title
    confidence                0.0 to 1.0
    parser_version
    computed_at
```

`UNIQUE (issuer_id, topic_key, to_filing_id)` — one comparison per topic per period.

Confidence carries the weakest link: a comparison built on `normalized_title` cannot be more
confident than the title match that produced it, and the UI surfaces that per
`docs/dashboard/ux-specification.md` section 7.

---

## API

```
GET /issuers/{cik}/footnote-topics
    Topics available for comparison, with the periods each covers.

GET /issuers/{cik}/footnote-topics/{topic_key}?range=5y
    The topic across the range: one entry per period with its summary, its classification
    against the prior period, changed figures, and a link to each original source.
```

`GET /filings/{accession}/footnotes?classification=changed` is defined as: return footnotes whose
stored comparison against the immediately prior period is `CHANGED_MATERIAL`. **Until
`footnote_comparison` is populated, this filter parameter is not accepted** — the endpoint
returns `400 UNSUPPORTED_FILTER` rather than silently returning everything or nothing. An
interface must not imply a capability that does not exist.

---

## What this is not

It is not Deep Analysis. It reports *that* a note changed and *what* changed textually and
numerically. It does not explain *why*, does not assess significance, and does not draw
conclusions. Those require reasoning over evidence, cost budget, and a scoped session — which is
exactly the boundary between requirement 9 and requirement 10.

The comparison is the index into Deep Analysis: the user sees that the debt note changed
materially, and *then* decides to spend budget asking why.

---

## Tests

| Test | Assertion |
|---|---|
| `test_topic_key_survives_note_renumbering` | A note that moves from 9 to 8 between years resolves to one topic key |
| `test_unresolved_topic_is_not_paired` | No topic key means no comparison row, not a guessed pairing |
| `test_figures_only_change_is_immaterial` | Same structure with updated numbers is `CHANGED_IMMATERIAL`, and the moved figures are still reported |
| `test_added_paragraph_is_material` | A new paragraph yields `CHANGED_MATERIAL` |
| `test_new_topic_has_no_prior_filing` | A first-appearance note is `NEW` with a null `from_filing_id` |
| `test_review_state_blocks_comparison` | A `REQUIRES_REVIEW` footnote yields `INCOMPARABLE`, never a silent pass |
| `test_comparison_endpoint_invokes_no_model` | Zero `llm_invocation` rows across a full comparison request |
| `test_changed_filter_rejected_before_backfill` | `classification=changed` returns `400 UNSUPPORTED_FILTER` while comparisons are unpopulated |
| `test_synonym_merge_requires_curation` | Two topics not in the synonym table never merge automatically |
