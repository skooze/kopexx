# Canonical Footnote Grouping Algorithm

IMPLEMENTATION STATUS: stages 1 to 5 IMPLEMENTED (Sprint 4); stages 6 to 11 PLANNED (Stage 2 phase
W-3). The fallback stages remain unwritten because stages 1 to 5 left 0 of 117 child blocks
unattached on the verified filings — they are built when breadth exposes a case that needs them.
DECISION RECORD: `docs/adr/ADR-0005-canonical-footnote-grouping.md`
MODEL: `docs/footnotes/canonical-model.md`

---

## Objective

Given one filing's renderer reports, XBRL roles, TextBlock facts, and primary document, produce
the set of canonical footnotes, attach every source block and table to exactly one parent, and
record how each decision was made and how confident it is.

## Ordering principle

Deterministic evidence first. Textual heuristics next. A model only on residue. A human last.
Every stage records `grouping_method` and `confidence` on the decision it produced, so the
provenance of any grouping is answerable later.

---

## Stage 1 — Candidate discovery

INPUT: renderer report inventory (`FilingSummary.xml`, or the DERA `ren` table)
OUTPUT: candidate canonical footnotes

Take every report whose menu category is `Notes`. For a filing with no renderer metadata
(pre-2009), skip to stage 5.

Apple FY2025: 16 candidates.

## Stage 2 — Filing-item exclusion

INPUT: stage 1 candidates
OUTPUT: candidates minus non-financial-statement disclosures

Remove candidates that are SEC form-item disclosures rather than financial-statement footnotes.
A candidate is excluded when any of the following holds.

Its dominant concept sits in a namespace reserved for item disclosures, currently `ecd` (Item 408
insider trading) and `cyd` (Item 1C cybersecurity).

Its role URI or title matches the maintained exclusion list in
`metric_definitions/item_disclosure_exclusions.yaml`.

Excluded candidates are not discarded. They are routed to `filing_section` with the item number
that produced them.

Apple FY2025: 3 excluded, leaving 13.

> The exclusion list is a maintained artifact that drifts as SEC adds tagging mandates. A
> Notes-category candidate whose dominant concept sits in an unrecognised namespace is flagged
> for review rather than silently included or silently excluded.

## Stage 3 — Role-URI attachment (primary mechanism)

INPUT: surviving candidates; reports categorised `Tables`, `Details`, `Policies`
OUTPUT: parent-child attachments

For each child report, extract the role URI. Match it to a parent candidate by role URI prefix.
Attach on a unique match.

Apple FY2025: 46 of 46 attached, zero unmatched. `grouping_method = role_uri`, `confidence = 1.0`.

Unavailable for filings before 2009, which carry no role URIs at all.

## Stage 4 — Table-of-contents reconciliation

INPUT: canonical footnotes from stage 3; the filing's table of contents
OUTPUT: an expected count and a reconciliation status

Parse the notes section of the table of contents to obtain the expected number of footnotes and
their titles. Compare with the extracted set.

A match sets `reconciliation_status = RECONCILED`. A mismatch does not silently adjust the set;
it records `toc_expected_note_count`, marks the filing `PARTIAL`, and routes it to review. A
filing whose TOC says 24 and whose extraction says 22 is not complete, and the dashboard says so.

## Stage 5 — Heading reconciliation

INPUT: the primary document
OUTPUT: parsed note headings, numbers, and titles

Parse headings matching the note-heading patterns for the filing's era. Apple's FY2025 10-K uses
`Note N – Title`; other filers use `NOTE N. TITLE`, `Note N — Title`, or an unnumbered bold
title.

This stage supplies `number_as_displayed` and `title_as_displayed`, and independently confirms
the count. Apple FY2025: 13 headings parsed, matching 13 extracted.

For pre-2009 filings this stage is the primary mechanism rather than a confirmation, and
confidence is correspondingly lower.

---

## Implementation status — Sprint 4

**Stages 1 through 5 are IMPLEMENTED** in `packages/footnote_canonicalizer` and measured against
four preserved Apple filings: 10-K 13 footnotes / 46 of 46 attached / 0 orphans, and each 10-Q 10
footnotes / 0 orphans.

**Stages 6 through 11 are NOT implemented.** Stage 3 left zero children unattached across all four
filings, so no fallback could be exercised, and an untestable fallback carries the authority of a
tested one without the evidence. An architecture test asserts this sprint's code produces none of
their grouping methods.

Two corrections the implementation forced on this document:

**Stage 4 has no input for these filings.** Apple's 10-K and 10-Qs carry no per-note table of
contents — the notes section begins directly. The result is `NOT_ATTEMPTED`, which this
specification already distinguishes from `RECONCILED`, and stage 5 becomes the independent count
confirmation rather than a redundant one.

**Stage 5's heading pattern must span two elements.** The renderer emits `Note 1 –` and
`Summary of Significant Accounting Policies` as separate blocks. A pattern requiring both on one
line matches nothing in this filing.

**Scope of the evidence.** Role-URI grouping is measured on one issuer, in one era. It is not
established as universally sufficient. Breadth validation across at least 25 issuers and all four
eras is Stage 2 phase W-3 and remains BLOCKING for scale-out.

---

## Stage 6 — Presentation-hierarchy fallback

Used when stage 3 leaves a child unattached.

Walk the presentation linkbase upward from the child's dominant concept to find the nearest
ancestor that is a parent candidate's dominant concept. Attach on a unique result.
`grouping_method = presentation_hierarchy`.

## Stage 7 — Concept-overlap fallback

Used when stage 6 is inconclusive.

Compute the Jaccard overlap between the child's concept set and each candidate's concept set.
Attach when one candidate exceeds a configured threshold and no other comes within a configured
margin. `grouping_method = concept_overlap`, confidence proportional to the margin.

## Stage 8 — Title-similarity fallback

Used when stage 7 is inconclusive.

Normalize both titles (lowercase, strip punctuation and stop words) and compute similarity.
Attach on a clear single winner above threshold. `grouping_method = title_similarity`.

This is deliberately late. Titles are suggestive, not authoritative: a Debt table and a
Debt Covenants detail block share vocabulary with each other and with an Interest Expense block.

## Stage 9 — Filing-order fallback

Used when stage 8 is inconclusive.

Attach the child to the nearest preceding canonical footnote in document order. This is the
weakest signal and yields low confidence, but is usually correct because renderers emit a
footnote's children immediately after it.

## Stage 10 — Model adjudication

Used only on residue that stages 3 to 9 could not resolve, and only when the ambiguity is
genuinely textual.

The model receives the candidate parents and the unattached child as a YAML payload through the
standard gateway, and returns a YAML document naming one parent and a confidence. It never sees
raw HTML or XBRL. It cannot create a new footnote, merge two footnotes, or discard a source
block; it may only choose among supplied candidates.

`grouping_method = model_adjudication`. Any decision from this stage is recorded with the model
identifier and prompt version, and is auditable and reversible.

## Stage 11 — Human review

Anything unresolved after stage 10, plus anything below the configured confidence floor at any
stage, enters the review queue with the evidence each stage produced.

A filing with items in review is `REQUIRES_REVIEW`. It is never published as complete.

---

## Conflict resolution

When two stages disagree, the earlier stage wins, because the ordering is by evidential strength.
The disagreement is recorded rather than discarded: a stage-3 attachment that stage-8 similarity
contradicts is still applied, and the conflict is logged for the breadth-validation report.

When two candidates tie within a stage, the stage is inconclusive and control passes to the next
stage. A tie is never broken arbitrarily.

## Audit record

Every grouping decision persists **on the child block**, because stages 3 and 6 through 10 decide
per child. Columns on `footnote_source_block`:

```
footnote_id                the parent chosen; NULL when unattached
block_id                   the child
grouping_method            which stage produced it
grouping_confidence        0.0 to 1.0
grouping_evidence          the matched role URI, overlap score, or similarity score
competing_candidates       what else was considered and its score
extraction_run_id          which run produced it
grouping_parser_version    the code version
grouping_decided_at        timestamp
```

`canonical_footnote` separately carries `grouping_method`, `confidence`, and `grouping_evidence`
describing how the **parent** was identified in stages 1, 2, 4, and 5. The two are distinct
decisions and are recorded separately.

This makes any grouping answerable: which stage, on what evidence, against what alternatives.

> Corrected after the Sprint 2 alignment review. The original schema recorded the audit only on
> the parent, which could not answer "why was this block attached to this note" — the exact
> question the audit exists to answer.

---

## Test matrix

| Test | Assertion |
|---|---|
| `test_apple_fy2025_yields_thirteen_footnotes` | Exactly 13 canonical footnotes |
| `test_apple_fy2025_attaches_all_child_blocks` | 46 of 46 attached, zero orphans |
| `test_item_408_disclosures_are_not_footnotes` | Both insider-trading reports become filing sections |
| `test_item_1c_cybersecurity_is_not_a_footnote` | Cybersecurity report becomes a filing section |
| `test_toc_mismatch_marks_filing_partial` | 24 expected, 22 extracted yields PARTIAL, not COMPLETE |
| `test_orphan_block_is_not_force_attached` | Unattachable child keeps a null parent and enters review |
| `test_pre_2009_filing_uses_heading_stage` | No role URIs present; grouping_method is heading-based |
| `test_grouping_decision_records_evidence` | Every attachment carries method, confidence, and evidence |
| `test_tie_does_not_break_arbitrarily` | Two equal candidates advance to the next stage |
