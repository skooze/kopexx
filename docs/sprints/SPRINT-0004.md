# SPRINT-0004: Reproduce and validate canonical-footnote extraction

STATUS: COMPLETE — all 17 acceptance criteria measured against real acquired data
DATE: 2026-08-02
DEPENDS ON: Sprint 3 (COMPLETE, pushed as `bc9aeb6`)
SEQUENCING: `docs/adr/ADR-0015-thread-first-delivery-sequence.md`
ALGORITHM: `docs/footnotes/canonicalization-algorithm.md`, stages 1 through 5 only

NOT COMMITTED. Sprint completion and committing are separate; `rules.md` section 15 requires
explicit approval for each commit.

---

## Objective

**Prove deterministic canonical-footnote extraction against Apple's acquired FY2025 filings.**

The thesis this project is built on — that a 10-K's footnotes are the product, and that there are
13 of them rather than the 58 TextBlock facts or 71 renderer reports a naive count produces — has
been confirmed by inspection twice. This sprint turns that inspection into production code, run
against real preserved bytes, with every grouping decision auditable.

No model participates in discovery, grouping, adjudication, completeness calculation, or testing.

## Scope

**In scope.** `packages/footnote_extractor`, `packages/footnote_canonicalizer`,
`packages/table_parser`. Canonicalization stages 1 through 5. Table parsing sufficient for the four
Apple fixtures. Persistence of canonical footnotes, source blocks, attachment audits, filing
sections, tables, and completeness state. Idempotency and concurrency protection. Migration `0002`
if the schema requires a change.

**Out of scope.** Stages 6 through 11 — presentation-hierarchy, concept-overlap, title-similarity,
filing-order, model adjudication, human review — unless the four Apple fixtures produce an
unresolved case that cannot be handled correctly without one. Summarization. Model selection. Any
model invocation. API, dashboard, Deep Analysis. Other issuers. Other filing eras. AWS.

## Dependencies

| Dependency | State |
|---|---|
| Four acquired Apple filings preserved in `var/objects` | present, 20 objects, hashes in the fixture manifest |
| `metric_definitions/item_disclosure_exclusions.yaml` | present, version 1.0.0 |
| Live PostgreSQL with the 24-table schema | `0001_initial (head)`, sealed |
| Disposable `fintek_test` for destructive tests | present, separate |
| Application database | 1 issuer, 4 filings, 2,845 facts |

---

## Findings before implementation

Three facts were established by reading the preserved bytes, before any code was written. Each
changes what the implementation has to do.

**The role-URI mechanism works, measured rather than assumed.** Against the real
`FilingSummary.xml`: 71 reports, 16 `menucat='Notes'` candidates, 3 carrying `ecd`/`cyd` role
URIs, leaving 13 parents. 46 child reports across `Tables`, `Policies`, and `Details`. Prefix
matching attaches **46 of 46 with zero orphans and zero ambiguous multi-parent matches**, and the
per-note distribution matches the specification exactly: 1, 4, 3, 4, 3, 3, 6, 4, 5, 3, 4, 2, 4.

**A note heading is split across two elements.** The primary document renders `Note 1 –` and
`Summary of Significant Accounting Policies` as separate blocks. A stage-5 pattern requiring the
number and title on one line finds **zero** headings in this filing. The parser must join a
number-only heading with the text that follows it.

**This filing has no table of contents listing individual notes.** The notes section begins
directly after `Notes to Consolidated Financial Statements`; there is no note index with titles or
page numbers. Stage 4 therefore has no input, and the honest result is
`reconciliation_status = NOT_ATTEMPTED`, not a fabricated match. The completeness specification
already anticipates this: *"A filing with no parseable TOC is not the same as one that reconciled,
and a count cannot distinguish them."* Stage 5 becomes the independent count confirmation.

---

## Acceptance criteria

### Apple FY2025 10-K, `0000320193-25-000079`

1. Exactly 13 canonical financial-statement footnotes.
2. Exactly 46 child disclosure blocks in the verified scope.
3. 46 of 46 attached.
4. Zero orphan child blocks.
5. Three Item 408 / Item 1C disclosures classified outside the financial-footnote set.
6. Excluded disclosures persisted as filing sections, order and source preserved.
7. Every attachment carries an audit record: stage, method, confidence, evidence, candidate set.
8. Filed order preserved.
9. Displayed note numbers and titles match the filing.
10. Tables owned by the correct footnote.
11. Completeness resolves to a documented status, justified by the invariant.

### Three FY2025 10-Qs

12. Each produces a complete canonical set with **zero orphans**. Counts are measured, not
    predicted; expected values are recorded only after measurement.

### Cross-cutting

13. Rerunning canonicalization creates zero duplicates of any record type and yields the same
    reconciliation result.
14. Concurrent runs against one filing cannot create duplicate or conflicting records.
15. No issuer-specific branch anywhere in the three new packages.
16. Zero `llm_invocation` rows across the whole acceptance run.
17. No AWS authentication, SDK dependency, or network access in the committed test suite.

---

## Test plan

Candidate discovery · item-disclosure exclusion · role-URI grouping · TOC reconciliation ·
heading reconciliation · filed ordering · normalized titles · duplicate titles · missing titles ·
child blocks before a parent · child blocks after a parent · competing candidates · confidence ·
audit persistence · orphan detection · partial completeness · failed reconciliation · excluded
filing-section persistence · table ownership · table structure · cell provenance · exact numeric
text preservation · unsupported table state · idempotent rerun · concurrent-run protection ·
rollback · fixture reproducibility · no issuer-specific branches · no model dependency · no
network · no AWS.

Plus a fixture-level regression test asserting exactly 13 / 46 / 0 / 3, and **mutation proofs**
that it fails when a note is omitted, a child is orphaned, an excluded disclosure is
misclassified, or a duplicate attachment is inserted.

## Data and fixture plan

Committed fixtures support deterministic offline tests. Acceptance additionally runs against the
complete preserved objects under the gitignored `var/objects/`. No test requires the network.

## Persistence and migration plan

The existing schema is inspected before anything is added. `canonical_footnote`,
`footnote_source_block`, `footnote_table`, and `filing_section` already carry the columns the
audit model needs and the uniqueness constraints idempotency needs. Any change uses a new
`0002_*` migration; `0001_initial` is sealed and is never edited. Migration tests run only against
`fintek_test`.

## Known risks

| Risk | Handling |
|---|---|
| Role-URI grouping validated on one issuer | Sprint records it as measured on Apple, not proven universal. Breadth validation is Stage 2 phase W-3 |
| A fixture produces a case stage 3–5 cannot resolve | Stop, report the filing, block, candidates, and failed stages; do not add a fallback or model adjudication without approval |
| Table parsing scope creep | Only what the four fixtures require; no financial interpretation, no metric calculation |
| Silent content loss on unsupported HTML | Preserve raw source and classify the parse state honestly |

## Definition of complete

Every acceptance criterion measured against real acquired data. Documentation synchronized.
Verified behaviour distinguished from general behaviour and from unvalidated breadth. Then stop
and request commit approval.

---

## Measured results

All figures are from runs against the preserved objects under `var/objects/`, not from the
committed fixtures alone.

### Apple FY2025 10-K, `0000320193-25-000079`

```
 #  note                                                 children
 1. Summary of Significant Accounting Policies                  1
 2. Revenue                                                     4
 3. Earnings Per Share                                          3
 4. Financial Instruments                                       4
 5. Property, Plant and Equipment                               3
 6. Consolidated Financial Statement Details                    3
 7. Income Taxes                                                6
 8. Leases                                                      4
 9. Debt                                                        5
10. Shareholders' Equity                                        3
11. Share-Based Compensation                                    4
12. Commitments, Contingencies and Supply Concentrations        2
13. Segment Information and Geographic Data                     4
                                                        total  46
```

| Measure | Result |
|---|---|
| Reports in the inventory | 71, of which **70 real** and 1 navigation entry |
| Stage 1 candidates (`menucat='Notes'`) | **16** |
| Stage 2 exclusions | **3** — two Item 408, one Item 1C, all by namespace |
| Canonical footnotes | **13** |
| Child blocks | **46** (12 Tables, 33 Details, 1 Policies) |
| Attached | **46 of 46** |
| Orphans | **0** |
| Ambiguous multi-parent matches | **0** |
| Headings parsed | **13**, contiguous 1..13, every one joined from the following element |
| Stage 4 reconciliation | `NOT_ATTEMPTED` — the filing has no per-note table of contents |
| Stage 5 confirmation | **yes**, 13 headings confirm 13 footnotes |
| Extraction status | `COMPLETE` |
| Extraction confidence | **0.950**, reduced only by the absent TOC |
| Tables parsed | **62**, 4,891 cells |

Every attachment carries `grouping_method = role_uri`, `confidence = 1.0`, the matched parent role
URI as evidence, and an empty competing-candidate set — empty because the match was unambiguous,
but represented rather than absent.

### The three FY2025 10-Qs — measured, not predicted

| Accession | Period | Cand. | Notes | Excl. | Children | Attached | Orphans | Headings | Status |
|---|---|---|---|---|---|---|---|---|---|
| `…-25-000008` | Q1 | 12 | **10** | 2 | 23 | **23** | **0** | 10 | `COMPLETE` |
| `…-25-000057` | Q2 | 12 | **10** | 2 | 23 | **23** | **0** | 10 | `COMPLETE` |
| `…-25-000073` | Q3 | 12 | **10** | 2 | 25 | **25** | **0** | 10 | `COMPLETE` |

Each 10-Q excludes two item disclosures rather than the 10-K's three: a 10-Q carries the Item 408
insider-trading pair but no Item 1C cybersecurity disclosure, which is an annual requirement.
Confidence is 0.950 for each, for the same reason as the 10-K.

### Persistence

| Filing | Footnotes | Blocks | Attachments | Sections | Tables | Cells |
|---|---|---|---|---|---|---|
| 10-K FY | 13 | 59 | 46 | 3 | 62 | 4,891 |
| 10-Q Q1 | 10 | 33 | 23 | 2 | 37 | 2,226 |
| 10-Q Q2 | 10 | 33 | 23 | 2 | 37 | 2,728 |
| 10-Q Q3 | 10 | 35 | 25 | 2 | 38 | 2,775 |
| **total** | **43** | **160** | **117** | **9** | **174** | **12,620** |

Block count is attachments plus one parent narrative block per note: the note's own rendered report
is stored so a citation can point at what the note itself says, not only at a child.

Database totals after two full runs: 43 canonical footnotes, 160 source blocks, **160 attached, 0
orphaned**, 174 tables, 9 filing sections. `xbrl_fact` unchanged at 2,845. `llm_invocation`: **0**.

### Idempotency

```
run 1   footnotes inserted 13, updated 0    blocks inserted 59, updated 0
run 2   footnotes inserted  0, updated 13   blocks inserted  0, updated 59
```

Every write is `ON CONFLICT ... DO UPDATE` against a constraint that already existed. Footnote
UUIDs are stable across reruns, so a citation issued after run 1 still resolves after run 2.

## Table ownership

**The first answer was wrong, and the mistake is worth recording.** Criterion 10 was reported
unmet on the grounds that attributing a table to a note needs a document-offset-to-report map
`FilingSummary.xml` does not contain. That is true and irrelevant: it assumed the renderer
inventory was the only route to ownership. The filing publishes the relationship itself.

### The chain

```
table byte offset in the primary document
  -> innermost ix:nonNumeric span containing it    the filer's own note boundary
  -> that span's TextBlock concept
  -> the presentation roles that concept is under   from the filing's own _pre.xml
  -> a canonical footnote, an excluded disclosure, or a statement role
  -> footnote_id, or an explicit non-footnote classification
```

Every link is published by the filer. Nothing is positional. A child role — `...Tables`,
`...Details` — resolves through the attachment **stage 3 already audited**, so ownership inherits
one decision rather than deriving a second that could disagree with it.

### The continuation defect this exposed

A first implementation treated the `ix:nonNumeric` element as the note boundary and classified 23
of the 10-K's tables. That is wrong for a long note. Inline XBRL splits non-contiguous content
with `continuedAt`, and the rest lives in `<ix:continuation>` elements which may chain further.
Apple's FY2025 10-K has **24 continued TextBlocks and 35 continuation elements, 11 chained
onward.**

The debt maturity schedule, the commercial-paper table, and the purchase-obligation table all sit
in continuations. Ignoring them classified those as unowned filing furniture — a false negative
that would have silently narrowed what a Sprint 5 summary could be validated against, with nothing
to signal the loss. Resolving the chain took footnote-owned tables from 23 to 26.

### Statements are identified by their facts, not their position

A financial statement is not wrapped in a TextBlock; the filer tags each figure with
`ix:nonFraction`. So a statement table has no containing narrative span and would fall in with
cover layouts. It is classified by the concepts of the numeric facts inside its own byte range: if
those are presented under a Statements role, it is a statement. That separates the five primary
statements from the 31 layout tables they were pooled with.

### Measured classification, all four filings

| Filing | Total | Canonical footnote | Excluded section | Statement | Other | Unresolved |
|---|---|---|---|---|---|---|
| 10-K FY2025 | 62 | **26** | 0 | 5 | 31 | **0** |
| 10-Q Q1 | 37 | **11** | 0 | 5 | 21 | **0** |
| 10-Q Q2 | 37 | **11** | 0 | 5 | 21 | **0** |
| 10-Q Q3 | 38 | **12** | 0 | 5 | 21 | **0** |
| **total** | **174** | **60** | **0** | **20** | **94** | **0** |

**Zero excluded-section tables is a measurement, not a gap.** Apple's three Item 408 and Item 1C
disclosures were checked directly: 3 excluded roles, 21 concepts presented under them, and **no
table inside any of them**. The classifier handles the case; this filer does not exercise it.

Spot-checked rather than trusted in aggregate: `T43`, captioned *"Maturities (calendar year)"*,
resolves to **Debt** through `us-gaap:ScheduleOfDebtInstrumentsTextBlock`.

### Persisted, with provenance — migration 0002

`footnote_table.footnote_id` already existed and now carries the owner. A NULL there was
ambiguous — statement, excluded disclosure, filing furniture, or genuinely unresolved are four
different facts and only the last is a defect — so `0002_table_ownership` adds `ownership_kind`,
`ownership_method`, and `ownership_evidence`, a check constraint restricting the kind, a partial
index over unresolved rows, and a constraint requiring that `ownership_kind = 'CANONICAL_FOOTNOTE'`
and a non-null `footnote_id` agree in both directions, so the classification and the foreign key
cannot drift apart whatever writes them.

`0001_initial` is untouched. The round trip was tested against `fintek_test`, never the
application database.

**An unresolved footnote table now blocks `COMPLETE`.** Sprint 5 validates a summary's numbers
against that footnote's own tables, so a table whose owner is unknown is a number the validator
cannot scope.

## Idempotency, measured rather than asserted

The first implementation reported `updated 13 footnotes, 59 blocks` on an identical rerun. A
digest of every persisted value, before and after, showed what that meant:

```
canonical_footnote      unchanged
source_block (business) unchanged
source_block (run+time) CHANGED    extraction_run_id, grouping_decided_at
footnote_table          unchanged
filing_section          unchanged
filing judgements       unchanged
```

No duplicates and no business-field drift — but every rerun stamped a fresh run id and timestamp
onto decisions that had not changed. Those two fields then answer *"which run last touched this"*
while their names promise *"which run decided this, and when"*, and the original decision time is
destroyed.

Every upsert is now conditional on a value genuinely differing. A rerun performs **no write at
all**:

```
run A   footnotes inserted 0, updated 0, unchanged 13   blocks inserted 0, updated 0, unchanged 59
run B   footnotes inserted 0, updated 0, unchanged 13   blocks inserted 0, updated 0, unchanged 59

full-row digest, timestamps and run ids included, before and after an identical rerun:
  canonical_footnote  footnote_source_block  footnote_table  filing_section  filing  xbrl_fact
  identical           identical              identical       identical       identical  identical
```

Correction behaviour is preserved and tested: the condition is on the VALUES, not on a flag, so a
record whose authoritative input genuinely changed is still updated deliberately, and its audit
fields move with it.

## Defects discovered

**1. A note heading is split across two elements.** The primary document renders `Note 1 –` and
its title separately. A pattern requiring both on one line finds **zero** headings in this filing,
and stage 5 would report success while confirming nothing. The parser joins a number-only heading
with the following line; all 13 headings in the 10-K and all 10 in each 10-Q are joined this way,
so this is the normal case for this filer, not an edge case.

**2. A closure captured a loop variable and destroyed cell provenance.** The table parser's
rowspan handling used an inner function that closed over the row index. Python binds that by
reference, so every cell carried down by a rowspan was stamped with the LAST row index rather than
its own — silently corrupting exactly the provenance the parser exists to preserve. Caught by
`ruff` B023 and covered by a test asserting a carried-down cell records the row it appears in.

**3. Spacing rows were reported as malformed tables.** Filers use `<tr></tr>` for vertical space.
Counting those in the width-consistency check flagged **46 of Apple's 62 tables** as ragged when
none was, and defeated header detection on every one. Spacing rows are now kept — removing them
would shift row indices and break provenance — but excluded from both checks.

**4. The issuer-specific check missed the exact defect it was hunting.** Two attempts:

- Skipping lines that start with `#` or a quote flagged eight docstring *continuation* lines,
  which start with neither. Those docstrings cite the filing the measured numbers came from,
  which is provenance and is required.
- Skipping every `STRING` token then missed `if cik == "0000320193"` entirely, because the issuer
  is a string literal — so exempting all strings exempts precisely the defect.

Now an AST walk that exempts docstrings specifically and inspects every other literal, name, and
attribute. Proven by mutation: adding that branch fails the test.

## Deferred items

- **Stages 6 through 11 are not implemented.** Stage 3 left zero children unattached across all
  four filings, so no fallback ran or could be tested. Implementing one would be untested code
  carrying the authority of tested code. An architecture test asserts the later grouping methods
  are not produced by this sprint's code.
- **`filing_document` registration remains carried forward.** Canonicalization does not need it:
  input is located through the acquisition manifest, which records the storage key of every
  preserved object, and each canonical footnote persists the renderer position, role URI, and the
  inventory's SHA-256. Traceability from a footnote to the exact bytes is therefore complete
  without it. Registering acquired objects is `filing_acquisition`'s concern and is not duplicated
  here.
- **No migration was created.** The sealed `0001_initial` already carries every column the audit
  model needs and every uniqueness constraint idempotency needs, verified against the live catalog
  before the persistence layer was written. A `0002` restating existing constraints would be churn.

## Acceptance criteria — audit

| # | Criterion | Result | Evidence |
|---|---|---|---|
| 1 | Exactly 13 canonical footnotes | **MET** | measured on the preserved 10-K |
| 2 | Exactly 46 child disclosure blocks | **MET** | 12 Tables + 33 Details + 1 Policies |
| 3 | 46 of 46 attached | **MET** | every one `role_uri`, confidence 1.0 |
| 4 | Zero orphans | **MET** | 0 in the result and 0 in the database |
| 5 | Three item disclosures excluded | **MET** | two Item 408, one Item 1C, by namespace |
| 6 | Excluded disclosures persisted as filing sections | **MET** | 9 rows across four filings, item number and order preserved |
| 7 | Every attachment has an audit record | **MET** | method, confidence, evidence, competing set, run id, parser version, timestamp |
| 8 | Filed order preserved | **MET** | `sequence` is renderer position order |
| 9 | Displayed numbers and titles match | **MET** | 13 headings, contiguous 1..13 |
| 10 | Tables owned by the correct footnote | **MET** | 60 of 174 tables owned by a named note, 20 statements, 94 filing furniture, **0 unresolved** on every filing |
| 11 | Completeness resolves to a justified status | **MET** | extraction `COMPLETE`, filing `PARTIAL` (no summaries yet), confidence 0.950 |
| 12 | Each 10-Q complete with zero orphans | **MET** | 10/10/10 notes, 23/23/25 children, 0 orphans each |
| 13 | Rerun creates zero duplicates | **MET** | run 2 inserted 0, updated all; identical reconciliation |
| 14 | Concurrent runs cannot conflict | **MET** | transaction-scoped advisory lock, proven held; plus database constraints |
| 15 | No issuer-specific branch | **MET** | AST guard, proven by mutation |
| 16 | Zero `llm_invocation` rows | **MET** | 0 |
| 17 | No AWS or network in the committed suite | **MET** | architecture guards, proven by mutation |

**Criterion 10 was initially reported unmet and has since been resolved.** The first conclusion —
that ownership needed a document-offset-to-report map `FilingSummary.xml` does not provide — was
wrong. It assumed the renderer inventory was the only route. The filing carries the relationship
itself, through its own inline-XBRL tagging and presentation linkbase. See "Table ownership"
below.

## Final validation

```
editable install         exit 0
make fmt-check           107 files already formatted
make lint                All checks passed
make typecheck           no issues found in 77 source files
make test-no-skips       551 passed, 0 skipped, exit 0
make coverage            93.45%  (85% gate)
make migration-check     exit 0 (offline)
0002 round trip          upgrade/downgrade against fintek_test only
make db-verify-isolation fintek vs fintek_test, differ
YAML                     22 parsed, 0 failed
documentation checks     7 passed
gitleaks history / tree  exit 0 / exit 0
pip-audit --skip-editable exit 0
CI-equivalent, bare env  551 passed, 0 skipped, exit 0
offline footnote suite   158 passed with no var/ and no network
```

Application database: `issuer=1 filing=4 xbrl_fact=2845` before and after. No filed fact modified.
No AWS operation, credential, or SDK. No model invocation. Zero root-owned repository files.
Temporary run reports under the ignored `var/`.

## Proposed commit

Prepared, not created. `rules.md` section 15 requires explicit approval.

Subject: `Extract and reconcile canonical footnotes for one issuer`

## Next sprint

**SPRINT-0005: real-model summarization, fidelity, and cost.** The go/no-go sprint. Its
authentication prerequisite is `docs/security/aws-identity-and-secrets.md`; no long-lived access
key is created for it at any point.
