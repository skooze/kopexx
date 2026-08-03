# ADR-0016: Corpus-first evidence and model-first parsing

STATUS: ACCEPTED
DATE: 2026-08-02
SUPERSEDES: ADR-0005 in full. ADR-0013 in the request direction only.
REPLACES: an earlier, withdrawn ADR-0016 ("complete filing content scope") that was authored on
2026-08-02, never committed, and is superseded before it entered history. Its scope correction was
right; its mechanism was not. See "The withdrawn ADR-0016" below.
DOES NOT SUPERSEDE: ADR-0003, ADR-0004, ADR-0011, ADR-0012, ADR-0014, ADR-0015, or the response
direction of ADR-0013.
SUPERSEDED IN PART, 2026-08-03: section 16 in full and section 15 in part, by
`docs/adr/ADR-0017-delete-the-rejected-parser-and-application-persistence.md`, which DELETED the
deterministic parser demoted there to a benchmark oracle.

**NO MODEL HAS BEEN INVOKED. NO BEDROCK CALL HAS BEEN MADE.** Every model-related statement in
this ADR is a design decision or a stated intent, never a measured result. Model availability,
model IDs, regional support, modalities, context and output limits, request formats and prices are
all subject to live discovery in Phase 1.5, which has not run.

---

## 1. The original product intent

An orchestrator-driven SEC filing product. The user selects **four models independently** — a
parsing model, an image model, a summary model, and an analysis/chat model. The backend discovers
and acquires filings, preserves the original SEC artifacts byte-for-byte, sends an intact original
filing to the selected parsing model, receives a clean parsed artifact, persists it separately from
the source, sends the accepted parse to the selected summary model, persists a separate summary
artifact, uses an image model when the parsing model is text-only, uses the analysis model for Deep
Dive and chat, caches reusable results, streams progress, and serves completed results with no
further model calls.

**The backend orchestrates and validates. It does not attempt to understand a filing semantically
before the model sees it.**

## 2. How footnote examples became an exclusive scope

The user described financial-statement footnotes as the hardest and most valuable content, and used
them as the running example of what good output looks like. The repository turned an example into a
boundary. From its first commit it encoded "the footnotes are the product": the schema, the
extraction packages, the summarization specification and the acceptance criteria were all written
as though a filing were a container of footnotes with some surrounding material of no interest.

An example of the hardest case is evidence about difficulty. It is not a definition of scope.

## 3. How deterministic semantic parsing became authoritative

Correcting the scope in the withdrawn ADR-0016 produced the second drift. The conclusion drawn was
that if footnotes were too narrow, the answer was *a more complete deterministic parser*. By Sprint
4.1 that had become an eleven-stage grouping chain, a 22-value content-unit taxonomy enforced by
PostgreSQL CHECK constraints, regular expressions deciding what a Part, an Item, a footnote, a
signature block and a certification are, a programmatic mapping from Regulation S-K topics to proxy
headings, `rules.md` invariant 13 stating "never let a model decide what filing content is", and an
architecture test that failed the build if a model was imported anywhere near extraction.

The backend had become the authoritative semantic parser. The model had been designed out of the
one job the product exists to give it.

## 4. Why five Apple filings were insufficient evidence

Every one of those decisions was validated against **four Apple filings from FY2025 plus one Apple
filing from 1994** — one issuer, one filing agent, effectively two transport eras. That corpus
cannot distinguish "true of SEC filings" from "true of Apple". It cannot contain a small-business
form, a transition form, a co-registration, a filing-agent accession prefix, a malformed table, an
issuer with six former names, or a filing eight times Apple's size.

Confidence had been calibrated against a sample that could not produce a counterexample.

## 5. Why the representative corpus was required

Because the disagreement was about facts, not preferences. "Can a filing be sent intact?" and "does
every filing have a primary document?" and "is the small-business family rare?" are measurable. The
only way to settle them was to acquire a corpus wide enough to contain the cases Apple cannot.

## 6. Corpus findings — DATED PHASE 1 EVIDENCE, measured 2026-08-02

**112 issuers, 613 filings, 6 transport eras, 767 MB on disk, 22 distinct filed form strings, 75
distinct SIC industries, every object hash-verified, zero throttle events.**

These totals describe *this sample on this date*. They are evidence, not permanent universal
constants, and no invariant elsewhere in the repository is written in terms of them.

**6.1 Intact submission is often expensive, and Apple is not the hard case.**
Estimated at 3.0 characters per token — a planning ratio, never a provider tokenizer count — the
primary document alone exceeds ~128,000 tokens in 313 of 613 filings (51 percent), ~200,000 in 271
(44 percent), ~500,000 in 169, and ~1,000,000 in 71. Median 147,524; maximum 4,309,108, a JPMorgan
Chase 10-K of 12.9 MB. Apple's FY2025 10-K, treated as the worst case for four sprints, is roughly
one eighth of that.

**6.2 Markup overhead is inverted from the intuition.** Median raw-to-visible-character ratio by
transport format: PEM-armored SGML 1.34, plain text 1.27, HTML 4.45, inline-XBRL HTML 7.39, worst
observed 24.11. The oldest filings are nearly free to send intact. The modern ones are expensive.

**6.3 Package shape varies by two orders of magnitude.** Median files per package by era: 5, 6, 10,
42, 101, 105 from oldest to newest; maximum 283. Images appear in 187 of 613 filings, none before
1996 and 80 of 108 in the current era, with 108 in a single package. Eleven filings carry PDFs.
Transport formats: PEM-armored SGML 244, HTML 219, inline-XBRL HTML 113, plain text 30, SGML text
7. No fixed expectation about package composition survives the corpus.

**6.4 One accession can belong to more than one CIK.** Alphabet Inc. and GOOGLE INC. co-registered
10-K/A `0001193125-16-520367`: one submission, identical bytes, two filer CIKs. Any uniqueness rule
keyed on the accession alone rejects valid SEC data; the key is `(cik, accession)`. Separately, 361
of 613 filings carry an accession whose prefix is the FILING AGENT's CIK rather than the issuer's,
so ownership must be resolved from the SEC archive path.

**6.5 Identity is unstable in the ways the design assumed it was not.** 48 of 112 issuers have
recorded former names; 68 have no current ticker in the submissions API at all; four report three
or more concurrent tickers. Name matching alone is unreliable and a current ticker is not identity.

**6.6 Form-family membership cannot be guessed.** An exhaustive scan of every time-eligible EDGAR
quarterly master index from 1993Q1 through 2026Q3 — 135 quarters, zero unavailable — enumerated 41
distinct 10-family form strings, of which **22 are direct substantive reports and 19 are adjudicated
near-matches excluded** (notifications, registrations, asset-backed distribution reports and similar).

An earlier draft asserted the small-business families were "almost entirely absent" from EDGAR.
THAT CLAIM WAS WITHDRAWN AND THE MEASUREMENT REVERSES IT. The claim came from a scan searching for
the hyphenated strings `10-KSB` and `10-QSB`; EDGAR's actual submission types are UNHYPHENATED:

```
10QSB        120,120 filings   9,771 issuers   1994-05-09 to 2008-10-31
10KSB         36,912 filings   8,688 issuers   1994-03-29 to 2009-03-16
10QSB/A       17,117 filings   5,262 issuers
10KSB/A       11,909 filings   4,684 issuers
10KSB40        3,441 filings   1,787 issuers
10KSB40/A        625 filings     453 issuers
```

`10QSB` is the FOURTH most common form in the entire 10-family, ahead of `10-K/A` and `10-Q/A`. The
family totals roughly 190,000 filings. The hyphenated spellings exist only as data-entry anomalies:
`10-QSB` 4, `10-KSB/A` 2, `10-KSB` 1, `10-QSB/A` 1. The same defective filter also omitted the
transition family — `10-KT` 610, `10-QT` 247, `10-KT/A` 141, `10KT405` 86, `10-QT/A` 37,
`10KT405/A` 17. Two forms a plausible guess would have added, `10KSB405` and `10KSB405/A`, DO NOT
EXIST in any scanned quarter.

THE GENERAL LESSON, recorded in the decision rather than quietly patched: a guessed allowlist
produced a confident, precise and completely inverted conclusion. Qualifying-family logic is now
GENERATED from an adjudicated inventory in which every included form carries an authoritative SEC
description read from a real filing-detail page and at least one verified accession, and any
unreviewed candidate fails closed. Enforced by `tests/unit/test_form_family_contract.py`.

**6.7 A withdrawn finding, recorded rather than deleted.** An earlier draft stated that "190 of 533
filings declare no primary document — 36 percent of the corpus". THAT FINDING IS WITHDRAWN. It came
from reading `index.json`, whose `type` field is a UI icon name rather than a declared document
type and whose sizes are frequently zero. Re-measured against the filer-declared document tables,
all 613 filings in the expanded corpus resolve a primary document. What remains true, and matters
more, is that **pre-2001 documents are not individually addressable on EDGAR**: the complete
submission text file is the only retrievable artifact and every filed document lives inside it. A
pipeline whose input contract assumes separately addressable documents is blind to an entire era.

### The withdrawn ADR-0016

An earlier ADR-0016 correctly identified that footnote-only scope was too narrow, then concluded
the answer was a more complete deterministic parser. Its scope diagnosis was right; its mechanism
doubled down on the drift. It was never committed and is superseded here before entering history.

---

## 7. Decision — why the LLM owns semantic interpretation

**The selected parsing model owns semantic interpretation.** The corpus shows the variation is not
tractable deterministically at acceptable cost. Table markup spans three orders of magnitude.
Malformed markup is normal before 2005. Heading conventions differ by filer, by agent and by era.
An entire era has no separately addressable documents. Every deterministic rule that fit Apple
would need an exception per issuer per era, and each exception is a place where content is silently
dropped — the exact failure the completeness requirement exists to prevent.

The observed failure mode of the deterministic parser was not an exception. It was silent,
confident wrongness.

## 8. Why the backend owns orchestration and validation

Because a model can also omit content silently and confidently, and model-first is not the same
thing as trusting the model. The backend holds the preserved bytes and can therefore prove,
independently of whatever produced the parse, that every human-readable source range is represented
or explicitly unresolved, that every citation resolves inside the source at its stated offset, and
that every reported number appears verbatim.

**Interpretation is the model's. Proof is the backend's.** Coverage validation is the control that
makes model-first parsing safe.

The backend performs transport-level handling only: file type, MIME type, byte size, encoding,
SEC-declared document type, document count and order, format detection, inline-XBRL presence, image
references and dimensions, page count, table-markup counts, raw-to-visible ratio, malformed markup,
duplicate renderings, source offsets and hashes, and whether an artifact can be sent intact through
a provider API. None of these becomes a semantic ontology.

## 9. Why original source remains authoritative

Because everything else is derived and every derivation can be wrong. Original SEC artifacts are
preserved byte-for-byte, hashed, provenanced, stored durably, and **never replaced** by a parse, a
summary, or a derived index. A parse that disagrees with the source is a defect in the parse. The
source is also the only thing that makes a re-run, a model comparison, or a later correction
possible without re-acquiring from SEC.

## 10. Why intact-source-only remains the current authorized mode

`INTACT_SOURCE_ONLY` is the only authorized input mode. For each filing/model pairing the backend
determines the complete relevant human-readable source set, verifies actual model compatibility
before invocation, and then either sends that set **intact in one invocation** or declares the pair
INCOMPATIBLE.

```
no truncation                    no semantic slicing
no automatic model substitution  no silent fallback
no mechanical multipart          no visible-content projection
```

An incompatible pairing is a visible, reportable result. The user may choose another compatible
model. It is never resolved by quietly sending less.

The reason is section 8: coverage can only be proved against what was actually sent. Every
alternative mode makes "complete" mean something weaker, and the whole product rests on that word.

## 11. Why projection and multipart remain unapproved future options

Sending only extracted visible text is the cheapest option by a factor of between 1.3 and 24, and
mechanical multipart would make large filings processable at all. Both are plausible and both
remain **research options requiring separate explicit user approval**. Neither is accepted
architecture and neither may be presented as such.

Extracting visible text is itself a semantic decision about what is visible, and it discards the
structural signal — table boundaries, emphasis, nesting — the parsing model needs. Multipart raises
a reassembly-correctness problem that has to be solved before it can be trusted. Both must be
revisited if Phase 2 shows intact submission is unaffordable at useful breadth.

## 12. Why final database design is deferred

Migration `0003` was designed before a single model had ever parsed a filing. It encoded 22 unit
types, six dispositions and sixteen CHECK constraints describing an interpretation no model had
produced, and the corpus shows that interpretation would not have survived contact with the second
issuer.

**The schema follows the artifacts; the artifacts follow the experiments.** Final PostgreSQL and
Redis design is Phase 8, after Phase 2 has produced real parsed artifacts from real models over
materially different corpus samples.

## 13. The four model roles

| Role | Selected by | Responsibility |
|---|---|---|
| Parsing | the user, explicitly | determines the filing's native semantic structure |
| Image | the user, from image-capable choices | analyzes image-bearing source objects when the parsing model is text-only |
| Summary | the user, independently | produces a separate summary and explanation artifact from an accepted parse |
| Analysis / chat | the user, independently | Deep Dive, follow-up questions and comparisons within an immutable scope |

No role inherits another's model. No silent substitution and no silent fallback.

If the parsing model is multimodal it handles the images itself, the image selector remains visible
but disabled for that job, and no image model is invoked redundantly. If the parsing model is
text-only, the backend inventories image-bearing objects **mechanically**, the selected image model
analyzes them, and the resulting artifacts stay separate and linked.

Approved beta model candidates: **GPT OSS 120B, NVIDIA Nemotron 3 Super 120B, Qwen3 235B A22B,
Llama 4 Maverick, Qwen3 VL 235B.** None is currently configured or accessible. Availability, model
IDs, regional support, modality, limits and prices are subject to Phase 1.5 live discovery.

## 14. Flexible artifact principles

The parsed artifact must be able to carry filing-native labels, unknown structures, free-form model
descriptions, ordered content, parent/child relationships, paragraphs, lists, tables, images, source
references, confidence, ambiguity, unresolved content, and content types not yet anticipated.

**No universal semantic filing taxonomy is required.** Labels such as MD&A, Risk Factors, Item 7,
Footnote, Part I, Certification, Signature or a fixed proxy topic may appear as filing-native
labels, model annotations, optional derived indexes, search facets, benchmarks or validation
hints. They are not required database ontology and no filing is obliged to use them.

**The complete-content requirement survives the removal of the taxonomy, unchanged:**

> Every human-readable source range in a processed filing must be represented in the accepted
> parsed artifact or explicitly marked unresolved.

> Every financial-statement footnote identified by the accepted parse must remain an independent
> content node and an independent summary target.

A filing is not complete when source content was omitted, a range is unresolved, a citation cannot
be resolved, a required source member was not processed, or a recognized footnote disappeared or
was merged away. Uncertainty produces `PARTIAL` or `REVIEW_REQUIRED`, never a false complete.

## 15. Deterministic work RETAINED as valid infrastructure

SEC identity; SEC request controls, rate limiting and throttle classification; filing discovery;
source acquisition; byte-exact preservation, hashing and provenance; transport decoding of PEM
armor and SGML containers; content-type detection; accession document inventory by the filer's
declared type; image and page-location detection; source offsets; XBRL and DERA numeric evidence;
metric definitions; database and migration safety; test-database isolation; the LLM content
boundary and its gateway chokepoint; cost and token accounting; citation validation; numeric
validation; coverage validation based on source identity; and the test and benchmark corpora.

None of this interprets meaning. All of it is transport, identity, evidence or safety.

## 16. Deterministic work DEMOTED to benchmark, hint or derived index

Apple canonical-footnote extraction; table-ownership measurements; existing historical parsing
measurements; deterministic heading and section observations; complete-filing parser results; and
corpus-derived common patterns.

`packages/footnote_extractor`, `packages/footnote_canonicalizer` and `packages/table_parser` are
**demoted, not deleted**. Their measured Apple results — 43 canonical footnotes cross-checked by
two independent mechanisms, 117 of 117 child-block attachments, 174 classified tables — become
recall floors and validation oracles for grading a parsing model, and may support model evaluation,
regression detection, optional hints, A/B comparison and derived search indexes.

**They no longer define the only valid parse and are no longer a product requirement.**

## 17. Deterministic work WITHDRAWN as an active product requirement

The universal content-unit taxonomy and its CHECK constraints; the required semantic hierarchy;
programmatic Part and Item interpretation; programmatic footnote meaning; programmatic proxy-topic
mapping; fixed semantic enums; rigid semantic completeness; database constraints enforcing one
universal interpretation; deterministic semantic parsing as a prerequisite for LLM processing;
migration `0003`; and any planned migration `0004` derived from that schema.

**No implementation file is deleted by this ADR.** Withdrawal of the implementation is a separate,
separately authorized change.

## 18. Consequences

Easier: representing any filing from any era; adding issuers without adding parser branches; honest
reporting of what could not be processed; changing the output contract without a migration.

Harder: cost, and it is now visible rather than hidden. Intact submission is expensive and often
impossible within current context limits, and the no-slicing policy converts that into a reportable
job failure rather than a silent truncation.

Constrained: no component may assume a primary document is separately addressable, assume a package
shape, assume well-formed markup, assume a recognizable heading convention, or assume that a filing
fits in any model's context window.

## 19. Risks

1. **No model may accept a materially sized modern filing intact.** 44 percent of the corpus exceeds
   ~200,000 estimated tokens in the primary document alone. Mitigation: Phase 1.5 measures real
   limits before any spend; incompatible pairs are reported, not worked around.
2. **Parsing cost may make the product unaffordable at breadth.** Every cost parameter today is a
   placeholder. Mitigation: Phase 2 is the go/no-go and it is explicitly authorized and metered.
3. **Model output may vary between reruns** by more than coverage validation can absorb. Mitigation:
   repeat-run variability is a measured Phase 2 output, and artifacts are versioned and superseded
   rather than overwritten.
4. **The corpus is 613 filings out of millions.** It is representative by construction, not
   complete. Mitigation: findings are dated and revisable; a contradicting expansion supersedes.
5. **Token estimates are character ratios, not tokenizer counts.** They may be materially wrong in
   either direction. Mitigation: they are labelled as estimates everywhere and replaced by measured
   values in Phase 1.5.
6. **Deferring the schema risks a later expensive migration.** Accepted deliberately: designing it
   early is what produced `0003`.

## 20. Alternatives considered and rejected

**Keep the deterministic parser as primary, use a model only for residue.** Rejected: this is the
withdrawn ADR-0016's position and the corpus refutes it. The residue is the majority.

**Hybrid: deterministic parse first, model fallback on failure.** Rejected for now. It requires the
deterministic parser to know when it has failed, and the observed failure mode is silent confident
wrongness, not an exception. Revisit after Phase 2 measures real model accuracy.

**Send only extracted visible text.** Rejected as accepted architecture; retained as an unapproved
future research option. See section 11.

**Mechanical multipart processing.** Same disposition as projection. See section 11.

**Expand the deterministic taxonomy to cover the corpus.** Rejected: the corpus has 75 industries,
six eras and 22 filed form strings, and the taxonomy failed on the second issuer. The exception
count grows without bound and each exception silently drops content.

---

## Revisit conditions

- If Phase 1.5 shows no available model can accept a materially sized modern filing intact.
- If measured parsing cost makes the product unaffordable at any useful breadth.
- If parse variance across reruns exceeds what coverage validation can absorb.
- If a later corpus expansion contradicts a finding recorded here.

## Migration impact

The local `fintek` application database was dropped after proving every original SEC source object
exists byte-exact on the filesystem, and is deliberately not recreated. Migration `0003` was deleted
from the working tree without ever being committed. `0001_initial` and `0002_table_ownership` remain
committed and sealed. No `0004` was created. The schema that will eventually replace them is Phase 8
work. Destructive migration tests target `fintek_test`; persistence integration tests target
`fintek_integration_test`; neither is the application database and no application database exists.
