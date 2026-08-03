# SPRINT-0004A: Sprint 4.1 — the scope correction, the second drift, and the corpus-first recovery

STATUS: SUPERSEDED AS PLANNED WORK. Recorded here as the account of what happened.
DATE OPENED: 2026-08-02
DATE SUPERSEDED: 2026-08-02
DEPENDS ON: Sprint 4 (COMPLETE, `468d0f2`, hardened by `1d05199`)
AUTHORITATIVE OUTCOME: `docs/adr/ADR-0016-corpus-first-model-first-architecture.md` and `roadmap.md`

**NO MODEL HAS EVER BEEN INVOKED. AWS IS NOT CONFIGURED. NOTHING IS DEPLOYED.**
**NO MODEL-FIRST PARSER IMPLEMENTATION EXISTS, AND NONE IS MARKED COMPLETE.**

This record exists because Sprint 4.1 did not end the way it began, and the honest account is more
useful than a tidy one. It opened as a scope correction, became a second architecture drift, and
ended by being replaced with a corpus-first recovery. All three phases are recorded below.

> **Forward note, added 2026-08-03. Nothing below this note has been edited.** The deterministic
> parser this record adjudicates — `packages/footnote_extractor`, `packages/footnote_canonicalizer`
> and `packages/table_parser` — was demoted to an oracle here and has now been DELETED from the
> active tree, together with `packages/persistence`, `migrations/` and `packages/dera_notes`. The
> account below stands unchanged. Authoritative:
> `docs/adr/ADR-0017-delete-the-rejected-parser-and-application-persistence.md`.

---

## 1. What Sprint 4.1 set out to correct

Sprints 1 through 4 had built a repository in which **financial-statement footnotes were treated as
nearly the entire summarization product**. The schema, the extraction packages, the summarization
specification and the acceptance criteria were all written as though a 10-K were a container of
footnotes with some surrounding material of no particular interest.

That was too narrow, and the diagnosis was correct. A 10-K runs from the cover page through
Business, Risk Factors, Legal Proceedings, MD&A, Market Risk, the financial statements and their
notes, Controls and Procedures, Cybersecurity, the exhibit index, the filed exhibits, the
certifications and the signatures. All of it is disclosure an investor may need.

The user had used footnotes as the running example of the *hardest* content. The repository turned
an example into a boundary.

## 2. The second drift

Having correctly identified that footnote-only scope was too narrow, Sprint 4.1 drew the wrong
conclusion: that the answer was **a more complete deterministic parser**.

What that produced, before it was stopped:

```
an eleven-stage deterministic grouping chain
a 22-value content-unit taxonomy enforced by PostgreSQL CHECK constraints
regular expressions deciding what a Part, an Item, a footnote, a signature block
     and a certification are
a programmatic mapping from Regulation S-K topics to proxy headings
migration 0003, encoding one universal interpretation of every filing
rules.md invariant 13: "Never let a model decide what filing content is"
an architecture test that FAILED THE BUILD if a model was imported near extraction
```

The backend had become the authoritative semantic parser, and the model had been designed out of
the one job the product exists to give it. The user's stated product — an orchestrator that hands
an intact filing to a model of the user's choosing — had been contradicted in code, in the schema,
and in the governance rules, all at once.

**Both drifts passed every gate the repository had.** The tests were green, the documentation was
internally consistent, and the measurements were real. They were measurements of Apple.

## 3. Why five Apple filings could not catch it

Every decision above was validated against four Apple FY2025 filings plus one Apple 1994 filing:
one issuer, one filing agent, effectively two transport eras. That sample cannot contain a
small-business form, a transition form, a co-registration, a filing-agent accession prefix, a
malformed table, an issuer with six former names, or a filing eight times Apple's size.

Confidence had been calibrated against a sample that could not produce a counterexample.

## 4. The corpus-first recovery

A representative corpus was acquired to settle the question with evidence rather than argument.

### Phase 1 completion evidence — DATED 2026-08-02

```
112 issuers                         613 filings
6 transport eras                    760,174,532 bytes of preserved objects
22 direct substantive form strings  19 adjudicated near-matches excluded
75 distinct SIC industries          138 amendments
313 annual, 300 quarterly           187 filings carry images, 11 carry PDFs
median package 11 files             largest package 283 files
613 of 613 objects hash-verified    0 throttle events
0 duplicate (cik, accession) pairs  0 accession-to-CIK ownership mismatches
0 authoritative-name contradictions
```

Represented: standard forms, transition forms, small-business forms, Item-405 variants, base
reports, amendments, modern inline-XBRL filings, historical SGML and plain-text filings, HTML
filings, image-bearing packages, PDF-bearing packages, filings too large for some context windows,
and wide variation among issuers, eras, forms and industries.

**These totals describe one sample on one date. They are evidence, not permanent constants.**

### The four findings that decided it

1. **Intact submission is often expensive.** 44 percent of primary documents exceed ~200,000
   estimated tokens; 12 percent exceed ~1,000,000. The largest is a JPMorgan Chase 10-K at 12.9 MB,
   roughly eight times the Apple filing treated as the worst case for four sprints.
2. **Markup overhead is inverted from the intuition.** PEM-armored SGML 1.34, plain text 1.27, HTML
   4.45, inline-XBRL HTML 7.39, worst observed 24.11. The oldest filings are nearly free to send;
   the modern ones are expensive.
3. **Package shape varies by two orders of magnitude**, from 4 to 283 files, and pre-2001 filings
   expose no individually addressable documents at all — the complete submission text file is the
   only retrievable artifact.
4. **Identity is unstable in the ways the design assumed it was not.** One accession can belong to
   two CIKs (Alphabet/Google co-registration). 361 of 613 accession prefixes are the filing agent's
   CIK. 48 of 112 issuers have former names; 68 have no current ticker.

### The form-family defect, recorded rather than quietly patched

The first corpus pass filtered EDGAR for the hyphenated strings `10-KSB` and `10-QSB`, matched
almost nothing, and concluded that the small-business family was "effectively absent".

EDGAR writes `10KSB` and `10QSB`. The family is roughly **190,000 filings**, and `10QSB` alone —
120,120 filings by 9,771 issuers — is the **fourth most common form in the entire 10-family**. The
conclusion was not merely wrong, it was precisely inverted, and it was stated confidently.

The fix is structural, not a corrected string. An exhaustive scan of all 135 time-eligible EDGAR
quarterly master indexes from 1993Q1 through 2026Q3 enumerated 41 distinct 10-family form strings,
which were adjudicated into 22 included and 19 excluded. Qualifying logic is now **generated** from
that inventory; every included form carries an authoritative SEC description read from a real
filing-detail page and a verified accession; and any unreviewed candidate **fails closed**.
Enforced in ordinary CI by `tests/unit/test_form_family_contract.py`.

## 5. What was learned

1. **An example of the hardest case is not a definition of scope.**
2. **Correcting a scope error can produce a worse architecture error.** The second drift was a
   direct consequence of taking the first correction seriously and reasoning from the wrong
   premise.
3. **A green suite over the wrong product proves nothing.** Every gate passed during both drifts.
4. **A guessed allowlist can produce a confident, precise, inverted conclusion.** Qualifying logic
   must be generated from adjudicated evidence and must fail closed.
5. **Measure before designing.** The schema was designed before a single model had ever parsed a
   filing, and the corpus shows it would not have survived the second issuer.
6. **One issuer is a fixture, never a specification.**

These are now `rules.md` section 21, PRODUCT-DIRECTION-INVARIANT — seventeen mandatory rules that
may be strengthened and never weakened.

## 6. What is withdrawn

The universal content-unit taxonomy and its CHECK constraints; the required semantic hierarchy;
programmatic Part and Item interpretation; programmatic footnote meaning; programmatic proxy-topic
mapping; fixed semantic enums; rigid semantic completeness; database constraints enforcing one
universal interpretation; deterministic semantic parsing as a prerequisite for LLM processing;
migration `0003`; and any planned `0004` derived from it.

## 7. What implementation remains uncommitted

**NONE.** This is a correction to an earlier expectation and is recorded rather than glossed over.

`packages/filing_parser`, `packages/filing_content`, `scripts/extract_filing_content.py`, the
complete-content-model document, the earlier uncommitted ADR-0016 and their tests were deleted from
the working tree **before Commit 1 and without ever being committed**. Migration
`0003_filing_content_coverage.py` was likewise deleted without being committed, and no `0004` was
created. They exist in no commit and require no withdrawal commit.

What IS committed, and therefore what Commit 3 has to deal with, is different and smaller:

```
packages/footnote_extractor          committed, DEMOTED to validation oracle
packages/footnote_canonicalizer      committed, DEMOTED to validation oracle
packages/table_parser                committed, DEMOTED to validation oracle
scripts/canonicalize_footnotes.py    committed
scripts/build_ownership_fixtures.py  committed
the footnote-centric tables in migrations 0001 and 0002 — filing_section,
     canonical_footnote, footnote_source_block, footnote_table, footnote_summary
```

The migrations are SEALED under `rules.md` section 8 and are not edited. The schema that eventually
replaces them is Phase 8 work, after real model artifacts exist.

## 8. What remains valuable

Sprint 4's measured result **stands and is not superseded as a measurement**: 43 canonical
footnotes across four Apple filings, 117 of 117 child blocks attached, zero orphans, zero
unresolved tables, every attachment recording its method, confidence, evidence and the candidates
it beat.

**Its ROLE changed, not its correctness.** It is now a recall floor and a validation oracle for
grading a parsing model. It is not a product requirement and it does not define a correct parse.

Also retained as valid infrastructure: SEC identity, SEC request controls and throttle
classification, filing discovery, source acquisition, byte-exact preservation, hashing, provenance,
transport decoding, content-type detection, the accession document inventory, image and
page-location detection, source offsets, XBRL and DERA numeric evidence, database and migration
safety, the model content boundary, cost and token accounting, citation and numeric validation,
coverage validation based on source identity, and the test and benchmark corpora.

## 9. Phase status

```
Phase 1    Representative filing corpus            COMPLETE
Phase 1.5  Intact-source compatibility             OPEN — blocks Phase 2
Phase 2    Model contract and parsing experiments  BLOCKED PENDING USER AUTHORIZATION AND LIVE
                                                   BEDROCK CAPABILITY DISCOVERY
Phase 3-8  orchestrator, images, summaries, UI, chat, persistence   NOT STARTED
```

Phase 1.5 must verify live model availability, real model IDs, modalities, context and output
limits and supported request formats; calculate compatibility for representative filings; disable
incompatible filing/model pairs; and obtain explicit approval for the first billable experiments.
**Multipart and projection are not implemented there, or anywhere.**

## 10. Commit 1 — the preservation checkpoint

Committed and pushed as `062baafc` on 2026-08-02. 28 paths.

Preserved five original SEC filings that cost rate-limited network fetches and cannot be reproduced
offline: four Apple FY2025 inline-XBRL documents and the 1994 PEM-armored complete submission, all
five pinned in the fixture manifest with their SHA-256. Added two small durable fixtures and 25
contract tests that make the form-family and identity defects unrepeatable. Added the accession
document inventory. Added the database-safety work that closed defect D-13.

It also separated the test databases into three identities with no fallback between them:
`fintek_test` for destructive migration tests, `fintek_integration_test` for persistence
integration tests, and an application database that **deliberately does not exist**. Ordinary CI
creates no database named `fintek` and does not set `DATABASE_URL` at all.

## 11. The CI correction

The first push of Commit 1 produced a **red GitHub Actions run**. One unit test asserted that the
migration-target resolver reads `TEST_DATABASE_URL` from the project's `.env` — and then relied on
the developer's own `.env` to supply it. That file is gitignored, so it exists on every workstation
and on no CI runner: the test passed locally and could only ever fail in CI.

Corrected in `068eceb2`, pushed, and **CI green on both jobs**. The test now writes its own `.env`
under `tmp_path` and points the resolver's `REPO_ROOT` at it, so the real parser, the real resolver
and the real precedence chain all still run with nothing stubbed out. Four regression tests were
added alongside it, including the first coverage of the cluster-database rejection rule.

The lesson is recorded because it is the same shape as the others: **a test that depends on an
untracked file tests the machine, not the code.**

## 12. What this sprint did NOT deliver

No orchestrator. No model catalog. No capability router. No parsed artifact. No summary artifact.
No image artifact. No chat session. No UI. No final schema. No Redis design. No AWS configuration.
No model invocation of any kind. No cost measurement.

**Nothing above is planned work recorded as complete.** Sprint 4.1 as originally scoped was
replaced, not finished, and this record says so.
