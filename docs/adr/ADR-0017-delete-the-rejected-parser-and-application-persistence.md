# ADR-0017: Delete the rejected parser and the application persistence layer

STATUS: ACCEPTED
DATE: 2026-08-03

SUPERSEDES:
- ADR-0016 section 16 in full. The deterministic footnote and table work was DEMOTED to a benchmark
  oracle there; it is DELETED here.
- ADR-0016 section 15 in part, only where it retains DERA numeric evidence, table-structure parsing
  and the accession document classifier as valid infrastructure.
- ADR-0005 (canonical footnote grouping), already superseded in substance by ADR-0016 and now
  without an implementation.
- ADR-0001 (DERA NOTES as primary numeric source), ADR-0002 (Parquet/DuckDB serving),
  ADR-0003 (PostgreSQL control plane), ADR-0004 (PostgreSQL ingest ledger), ADR-0007 (pgvector),
  ADR-0011 (metric definition format) — each as an ACTIVE implementation decision. Their reasoning
  stands as history and may be revisited when persistence is designed from measured artifacts.

DOES NOT SUPERSEDE: ADR-0006, ADR-0008, ADR-0009, ADR-0010, ADR-0012, ADR-0013, ADR-0014,
ADR-0015, or ADR-0016 sections 1 through 14 and 17 through 20.

**NO MODEL HAS BEEN INVOKED. NO AWS CALL HAS BEEN MADE. NO APPLICATION DATABASE EXISTS.** Nothing
in this ADR is a measured model result.

---

## 1. Context

ADR-0016 established the product direction: an orchestrator-driven, model-first SEC filing system
in which the selected parsing model owns semantic interpretation and the backend proves coverage
against preserved bytes. It withdrew the deterministic semantic parser from product authority.

It stopped one step short. Section 16 DEMOTED `packages/footnote_extractor`,
`packages/footnote_canonicalizer` and `packages/table_parser` to "benchmark, hint or derived index",
and section 17 closed with: *"No implementation file is deleted by this ADR. Withdrawal of the
implementation is a separate, separately authorized change."*

That change is this one, and the user's instruction for it is unambiguous: the active repository
contains only implementation directly required by the intended beta, directly useful to the next
approved stage, or required to build, test, secure, govern or operate that product. Existing,
being tested, or being expensive to rebuild are explicitly not reasons to keep code.

An attempt to satisfy ADR-0016 by MOVING the parser to an executable `oracle/` tree was prepared
and then withdrawn before it was committed. It is recorded here because its reasoning was
plausible and should not be re-derived: the parser's expected results are computed by the parser
rather than recorded as fixtures, so preserving the oracle meant preserving the implementation.
That is a true observation and it is not a reason to keep the code. It means the oracle was never
a fixture set; it was a second implementation of the thing being withdrawn.

## 2. Decision

**Delete the rejected deterministic semantic parser, the application persistence layer, the
Alembic migrations, the DERA mirror and fact loader, and everything that exists only to serve
them. Git history is the archive.**

Nothing is moved to `oracle/`, `legacy/`, `deprecated/`, `benchmark/` or `tests/support/`. A
deleted subsystem parked in another namespace is still a subsystem the repository maintains,
type-checks, formats, tests and explains to every future reader.

## 3. Why the Apple oracle is not preserved

The measurement stands and is not being disputed: 43 canonical footnotes across four Apple FY2025
filings, 117 of 117 child blocks attached, zero orphans, zero unresolved tables. Three things
disqualify it as retained code.

**It measures one issuer.** Apple, one filing agent, one set of heading conventions, two of six
transport eras. The corpus that refuted the design contains 112 issuers, 75 SIC industries, 22
exact filed form strings and six eras. A recall floor derived from the easiest third of every
measured distribution cannot grade a model on the other two thirds, and a benchmark that is wrong
about breadth is worse than none: it produces a number, and a number gets believed.

**Grading a model against it would reinstate the withdrawn answer.** A parsing model that disagrees
with the deterministic pipeline would be scored as wrong. That makes the deterministic
interpretation authoritative again through the back door, which is precisely what ADR-0016
withdrew and what `rules.md` section 21 rule 1 forbids.

**It is not needed for the validation the product actually performs.** Coverage, citation and
numeric validation run against the PRESERVED SOURCE BYTES, not against a second parse. That is the
control ADR-0016 section 8 specifies, and it needs no oracle at all.

## 4. Why `table_parser` goes with them

`packages/table_parser` decided no financial meaning — it preserved rows, columns, header
hierarchy, cell provenance and exact filed numeric text, and its own docstring says it computes
nothing. It is deleted anyway, on the instruction's stated ground: a structural parser is deleted
when its current purpose is parsing ORIGINAL FILING CONTENT before model submission, and it is not
retained on the theory that it might later render model-produced tables.

Its module docstring opened "Parse the tables embedded in a filing's footnotes." Its only callers
were the canonicalizer and two parser scripts. A renderer for model-generated tables is designed
from real model responses, and will not have this shape because nothing yet knows what shape a
model returns.

## 5. Why the application persistence layer goes

Twenty-four ORM tables and two Alembic revisions describing an interpretation no model has ever
produced. Ten of the twenty-four are the rejected ontology directly — `filing_section`,
`canonical_footnote`, `footnote_source_block`, `footnote_table`, `footnote_summary`,
`filing_amendment`, `metric_definition`, `derived_metric`, `excluded_filer`, and the
`processing_state` half of `filing`, whose CHECK constraint enumerates `EXTRACTING_FOOTNOTES` and
`GROUPING_FOOTNOTES` as pipeline states.

The remaining fourteen are honest transport bookkeeping. They are deleted too, because they are
rows in an application database that does not exist and are shaped by the same unmeasured
assumptions. `rules.md` invariant 15 says schema follows accepted artifacts; there are no accepted
artifacts.

**The sealed-migration rule was checked, not bypassed.** `rules.md` section 8 forbids editing,
regenerating or deleting a migration that has been applied to a non-disposable database. The
precondition was verified before anything was removed: connecting with the configured application
URL returns `FATAL: database "fintek" does not exist`. Only `fintek_test` and
`fintek_integration_test` exist, both disposable, neither an application database. No deployed
environment runs these revisions, so no database is left silently diverged from a file claiming to
describe it — which is the harm the rule exists to prevent. Section 8 is amended additively rather
than weakened: it now records that these two revisions were deleted from the active tree under
explicit user authorization after that verification, and it continues to bind any future
migration.

## 6. Why DERA and XBRL go

The seven-part test in the instruction is conjunctive. `packages/dera_notes` fails three parts.

```
3  must not require the deleted application persistence   FAILS
       loader.py       INSERT INTO xbrl_fact, UPDATE dera_package
       registration.py INSERT INTO issuer, INSERT INTO filing, INSERT INTO dera_package
       reconcile.py    seven aggregates over xbrl_fact
       report.py and __init__.py import those three, so the package cannot import without them

6  must work without the obsolete database infrastructure  FAILS, same evidence

7  maintenance justified by immediate planned use          FAILS
       2,343 lines of package, 1,321 lines of tests, three runbooks, two specifications, for a
       capability no approved next stage uses
```

Part 5 also fails on its own terms. The only retention argument is that DERA numbers could validate
what a parsing model returns, and DERA cannot carry that role: the NOTES dataset starts at 2009Q1
and covers XBRL filers only, against a corpus in which 281 of 613 filings predate HTML-era markup
entirely and only 113 are inline XBRL. Its own values are approximations — `ddate` is rounded to a
month end, so Apple's fiscal year ending 2025-09-27 is recorded as 2025-09-30 — and the loader
writes every row `UNVALIDATED` with the comment that claiming otherwise would be a claim no code in
the repository has earned. A validation oracle available for under a fifth of the corpus, whose
periods are rounded and whose rows are self-declared unvalidated, cannot ground the parser
experiments.

If DERA numeric evidence is wanted later, the right shape is a small read-only comparator over
`num.tsv` for one accession, written against what a model actually returns.

**The mirrored data is untouched.** `var/dera/` holds 78 packages and 26 GB, gitignored, with its
ledger and manifests beside it. Twelve monthly packages have no quarterly consolidation yet and SEC
deletes monthlies on a rolling twelve-month basis, so those bytes are not indefinitely
re-downloadable. That is a data-retention decision about the filesystem and it is deliberately
separated from this code-retention decision. The tracked copies under `artifacts/dera/` are deleted
because they are byte-identical to the copies that travel with the payloads.

## 7. Why the accession document classifier goes

`packages/filing_acquisition/inventory.py` read the accession index page and classified every filed
document. The row scraping is exactly the transport work the product needs, and it is deleted with
the rest of the module because the module is not that.

Its `classify()` assigned a nine-term document ROLE taxonomy sourced from Item 601 of Regulation
S-K — certification, consent, financial schedule, exhibit — which is a universal filing taxonomy in
code and `rules.md` section 21 rule 2 requires explicit user approval for one. Worse, its
courtesy-PDF branch ruled that two different filed documents carry the same content and set
`requires_content_extraction=False` on one of them, suppressing a filed source range on a
semantic-equivalence judgement without reading either file. That is a direct violation of
COMPLETE-CONTENT-INVARIANT.

It had no production caller. The package facade never exported it.

**What replaces it is named, not silently dropped.** A non-classifying `list_filed_documents()`
returning the filer's own declared metadata — filename, sequence, declared type, description, size
— with no document class, no role and no extraction verdict is required by the raw-first source
stage, and the roadmap records it as such.

## 8. What survives, and the one defect the audit found in it

Eight runtime packages: `configuration`, `filing_acquisition`, `filing_discovery`, `llm_gateway`,
`observability`, `sec_client`, `sec_identity`, `storage`. All transport, identity, boundary or
generic infrastructure. `packages/llm_gateway` keeps only format machinery and loses its
footnote-shaped request contract entirely.

**The audit found a live contradiction inside surviving code and it is fixed here.**
`packages/filing_discovery` carried `ANNUAL_FORMS = ("10-K", "10-K405", "10-KSB")` and
`QUARTERLY_FORMS = ("10-Q", "10-QSB")`, matching on the part before `/A`. That is the guessed
hyphenated allowlist ADR-0016 section 6.6 records as producing a confident, precise and completely
inverted conclusion: EDGAR files `10KSB` and `10QSB` unhyphenated, `10QSB` alone is 120,120 filings
and the fourth most common form in the family, and the whole transition family was missed too. The
committed contract adjudicating all 41 observed strings into 22 included and 19 excluded sat beside
it in the same repository.

The reconciliation designed to catch a discovery gap applied the same filter to the master index,
so both sides agreed perfectly and reported a complete history that was missing the form coverage.
**A cross-check that shares the defect it is checking for is not a cross-check.**

The qualifying set is now a required argument with no default, matched on the exact filed string,
supplied from the reviewed contract. An architecture test parses runtime source and fails if a form
literal is written back into it.

## 9. Consequences

Easier: reading the repository; changing direction without a migration; proving what the backend
does and does not decide. The suite has no environmental precondition at all, so CI needs no
database service and a skip has no legitimate cause.

Harder: there is now no local numeric evidence and no filed-document lister. Both were doing real
work and both must be rebuilt against measured requirements rather than inherited.

Lost, and recoverable only from git history: roughly 8,600 lines of working, well-reasoned,
well-tested implementation, and 346 test functions. The docstrings in the deleted DERA modules
record several real defects avoided — `csv.QUOTE_NONE` because a double quote inside a DERA field
is literal data, the fiscal-period clamping bug, why SHA-256 rather than `hashtext` for an advisory
lock. None of that is a retention reason under the stated criteria. It is recorded here so the
decision is made with open eyes.

## 10. Risks

1. **Something deleted turns out to be needed sooner than expected.** Mitigated by git history and
   by the fact that every deleted capability is named in the roadmap where it returns.
2. **The rejected architecture returns by accident.** Mitigated by executable guards rather than
   prose: CI fails if any deleted package imports, an architecture test fails if a form literal
   reappears in runtime source, and a fixture test fails if derived parser output is committed
   again.
3. **Deleting the oracle removes the only independent check on a parsing model.** Accepted. The
   check the product relies on is validation against preserved bytes, which is stronger because it
   does not require a second interpretation to be correct first.

## Revisit conditions

- If parser experiments show that validation against preserved bytes cannot detect an omission that
  a second independent parse would have caught.
- If a measured requirement for local numeric cross-checking appears, at which point DERA is
  reconsidered on its merits and at its real cost rather than inherited.
- When persistence is designed from measured artifacts, at which point ADR-0002, ADR-0003,
  ADR-0004, ADR-0007 and ADR-0011 are reconsidered rather than assumed.

## Migration impact

None. No application database exists, no deployed environment runs the deleted revisions, and no
downgrade was performed. The two disposable databases `fintek_test` and `fintek_integration_test`
remain on the development host as unused leftovers; removing them is host administration and
requires separate authorization. The research corpus, the preserved SEC objects and the DERA mirror
under `var/` are untouched.
