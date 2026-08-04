# ADR-0021 — Completeness measured against a mechanical inventory, one filing at a time

STATUS: ACCEPTED
DATE: 2026-08-04
PHASE: 2.2
SUPERSEDES: nothing
BUILDS ON: [ADR-0016](ADR-0016-corpus-first-model-first-architecture.md),
[ADR-0017](ADR-0017-delete-the-rejected-parser-and-application-persistence.md),
[ADR-0020](ADR-0020-model-directed-multipart-parsing.md)

---

## Context

Phase 2.1 ran the model-directed multipart protocol against preserved filings with all five
candidates, seven runs, `USD 2.603827` of measured spend. It published four numbers that have each
been read as a completeness figure:

```
352/364 references resolved   GPT OSS 120B on the 3M 10-K405 of 1996
47/47 parts terminal          the same run
214 nodes vs 24 nodes         two candidates on the same bytes on the same day
table_count 0                 all seven runs, no exceptions
```

**Not one of them is a completeness figure, and the defect is the same in every case: the
denominator is supplied by the thing being measured.** A model that cites forty regions and
resolves thirty-eight of them scores 95 percent whether the filing has forty regions or four
hundred. A model that never mentions the financial statements at all is not penalised by any of
those four numbers, because unmentioned content never enters a count of mentions.

`rules.md` section 3, COMPLETE-CONTENT-INVARIANT, says what is actually required: every
human-readable source range is represented in the accepted parsed artifact or explicitly marked
unresolved, and **coverage is reconciled against discovered source material, never against section
counts.** Phase 2.1 proved something narrower and true — a citation the model emitted resolves in
the preserved bytes. It could not answer the invariant's question, which is what the parse never
mentioned at all.

The evidence that the gap is real, not theoretical, is Phase 2.1's own record: the same filing
produced plan sizes from **5 parts to 28**, a 5.6x spread, and node counts from **24 to 214**. If
either extreme is complete the other is not, and no number Phase 2.1 produced can say which.

Phase 2.2 built the missing denominator against one filing: Apple Inc., CIK `0000320193`, form
10-Q, accession `0000320193-25-000008`, filed 2025-01-31, inline XBRL, 63 package members, 9.9 MB
preserved.

```
63 members, 6 human-readable (915,890 characters), 2 images, 5 machine-only,
   49 SEC renderer artifacts, 1 duplicate complete submission, 0 unknown
1,757 text spans, of which 1,750 are visible and 607 are mechanically duplicate
229,410 visible characters
41 table elements: 18 with 20 or more non-empty cells, 8 empty of text,
   7 byte-identical to an earlier element, 0 nested
source_set_sha256 ca1b1f461fb695c5e10c1ac3e16dca0ad216f08fd4e87f8f59350b38cc90e465
built in 0.4 seconds, by packages/source_inventory, with NO MODEL INVOLVED
```

**No model was invoked in the phase that produced this decision.** Measured Bedrock spend: `USD
0.00000000`. Everything below is a decision about how a future run will be measured, taken from
preserved bytes and from Phase 2.1's preserved evidence.

---

## Decision

Coverage stops being measured by a model's own reference rate and is measured against a
**MECHANICAL INVENTORY of the preserved bytes** — every member, every visible text span, every
`table` element, every filed image — with a **HUMAN classification** of that inventory for ONE
filing, and **FOUR dispositions** per item:

```
COVERED             a coverage claim's two anchors both resolve and bound it, or a structured
                    table maps to it, or a model reference resolves inside it
UNRESOLVED          the model explicitly said it could not resolve this
HUMAN_EXCLUDED      a reviewer classified it as repeated, navigation, layout, transport markup,
                    decorative or not human-readable, with a reason on the record
SILENTLY_OMITTED    none of the above. The parse never mentioned it in any form.
```

**`SILENTLY_OMITTED` is the disposition this whole decision exists to produce**, and it is the one
no reference rate can compute. `rules.md` invariant 6a is "never silently omit human-readable
filing content"; until this phase, nothing in the repository could count an omission.

Eight decisions followed. Each is recorded here once.

---

## 1. A reference count has no denominator, and 352/364 is the proof

**Decision.** A resolved-reference rate is reported as what it is — how many of the model's OWN
citations were located in the preserved bytes — and is never reported as filing coverage. It is
never a numerator over the filing.

**Why.** `352/364 references resolved` means the model emitted 364 references and 352 of them were
found. It does not mean 96.7 percent of the filing was covered. Every region the model chose not to
cite is absent from both sides of that fraction. The measurement is **entirely inside the model's
own output**, and a parse that skipped half a filing while citing carefully within the half it kept
would score higher than one that covered everything and quoted sloppily.

**What replaces it.** `packages/completeness` counts the same references, and counts them beside
`spans_total`, `spans_covered`, `spans_unresolved`, `spans_human_excluded` and
`spans_silently_omitted` — where `spans_total` comes from the bytes and not from the parse. The
percentage properties on `SourceCoverageState` are derived; **the counts are authoritative**,
because a percentage printed without its denominator beside it is exactly how `352/364` came to be
read as coverage.

---

## 2. Terminal part counts and node counts are not completeness either

**Decision.** `47/47 parts terminal` is a scheduler fact and is labelled as one. Node counts are
reported without any implication of ordering, and no code compares two runs' node counts to decide
which parsed better.

**Why terminal is not complete.** A part reaches a terminal queue state by succeeding, by failing,
by truncating or by being cancelled. GPT OSS reached 47 of 47 terminal while its final
reconciliation still returned `plan_complete: false`. **A count of finished work is a statement
about the queue, not about the filing.**

**Why node counts have no correct denominator.** 214 nodes against 24 on the same bytes may mean
more detail, different granularity, duplication, fragmentation, fuller coverage, or a more verbose
representation of the same content. Nothing in the repository can distinguish those, and `rules.md`
section 21 rule 14 forbids concluding from one issuer anyway.

**Why the status enums were rebuilt.** Phase 2.1's `AssemblyStatus` had three members and a
repeated warning in prose that none of them meant complete. That warning was doing work a type
should do, and it failed: `INCOMPLETE_WORK` and `RECONCILIATION_UNRESOLVED` were both read as
quality verdicts. `packages/completeness/status.py` replaces the single value with **six
independent dimensions** — transport, serialization, source coverage, tables, images, human
readiness — precisely because none of them can be misread as a score. **No enum in that module has
a member meaning SEMANTICALLY COMPLETE**, and none ever will.

---

## 3. The inventory is MECHANICAL, and that is what keeps it on the transport side of invariant 14

This is the hardest part of the argument, because a package that walks a filing's markup and
enumerates its `table` elements looks a great deal like the deterministic semantic parser ADR-0017
deleted. It is not one, and the difference has to be stated precisely rather than asserted.

**Decision.** `packages/source_inventory` records, for each member: its media type, its decoded
character count, the byte offsets and lengths of every text span, the byte range and cell count of
every `table` element, each image's byte signature and pixel dimensions, and byte-level
duplication. **It assigns no meaning to any of them.** It does not name a section, detect a
heading, identify a financial statement, decide which table is an income statement, or decide which
span is material.

`rules.md` invariant 14 is explicit about where the line runs:

```
Backend code performs transport-level handling only: format, encoding, declared type, order,
offsets, hashes, image location, size and compatibility. It never decides what is MD&A, a risk
factor, a footnote, a financial statement, an exhibit or a signature block.
```

**Every field the inventory produces is in the permitted list, and that is not a coincidence — it
is the design constraint.** An offset is an offset. A `table` element is a syntactic construct the
filer put in the bytes, in the same sense that a member's declared media type is something the
filer put in the SGML envelope; recognising one is reading transport, not interpreting disclosure.
The inventory can say Apple's 10-Q contains 41 `table` elements. **It cannot say how many financial
tables Apple filed, and it does not try.**

**The two prefills, and why they are still not judgements.** `truth.suggest` proposes
`MECHANICALLY_EMPTY` for a table element in which no cell carries a single non-whitespace
character, and `MECHANICALLY_DUPLICATE` for one whose source slice is byte-identical to an earlier
element's. On this filing that is 8 empty and 7 duplicate of 41. Both are statements about bytes a
reviewer can verify in one glance, both are recorded as **suggestions with the evidence attached**,
and **neither is applied until a person accepts it** — `BenchmarkTruth.table` returns
`REQUIRES_REVIEW` for any judgement still flagged `suggested`.

**The counter-example that shows the line is real.** The deleted accession classifier ruled that a
courtesy PDF "duplicated" the primary document and suppressed a filed source range on that
judgement (ADR-0017). That was a semantic call wearing a transport costume. The inventory records
that two members have the same SHA-256 and **drops neither**; what follows from sameness is a
reviewer's decision, not a rule in code.

**Why this is not the ADR-0017 parser returning.** That parser produced *the authoritative
structure* of a filing and the product then displayed it. This produces *a denominator against
which a model's structure is checked*. It has no output a user reads as the meaning of a filing, it
names nothing, and if it vanished the parse would still exist — only the ability to say what the
parse missed would go with it.

---

## 4. The required set is a HUMAN judgement, versioned, and scoped to exactly one filing

**Decision.** Which inventory items a parse is REQUIRED to represent is decided by a person, one
item at a time, recorded as data with the reviewer and the timestamp on it, versioned, and scoped
to one accession at one `source_set_sha256`. `packages/completeness/truth.py` is that record.

**Why a person and not code.** The inventory says there are 41 table elements. Some are financial
statements; some are Workiva's page-layout scaffolding; some are the same rendering twice. **A
ledger that treated all 41 as required content would report every parse as incomplete forever. One
that guessed which eight are layout would be backend code deciding what filing content means**,
which invariant 14 and section 21 rule 1 both forbid. There is no third option that is honest.

**Why the default is `REQUIRES_REVIEW`.** Every span, table and image starts unclassified, and an
unclassified item is in neither `REQUIRED_*` nor `EXCLUDED_*`. It is not excused and it is not
demanded — **it blocks the gate until somebody looks at it.** A default of "material" would
silently make every layout table a required parse target and produce a permanent false failure. A
default of "layout" would silently excuse a model from a real financial statement and produce a
false complete, which is the defect `rules.md` section 21 rule 5 exists to prevent.
`REQUIRES_REVIEW` is the only default that is honest about the state of the evidence, and the
pressure it creates is the correct pressure.

**Why versioned and never edited.** `BenchmarkTruth.with_judgement` returns a NEW document at
`version + 1` and the previous one stays on disk — the same supersession rule `rules.md` invariant
7 applies to accepted summaries. A completeness figure computed against version 3 is meaningless if
version 3 can be edited into version 4 under the same name.

**Why generalising it would repeat the ADR-0016 drift, exactly.** The repository has already
narrowed its product twice on measurements of Apple: first "the footnotes are the product", then a
complete-filing deterministic parser. Both passed every gate that existed, because the tests were
green and the measurements were real — they were measurements of one issuer, filed by one filing
agent, in two of six transport eras. **Apple's layout tables are Workiva's layout tables.** A rule
derived from them is a rule about a filing agent, and `rules.md` section 21 rule 14 forbids stating
it as a claim about filings. Every truth document therefore carries a `scope_note` saying so, and
`HUMAN_APPROVED_COMPLETE_FOR_THIS_FILING` is scoped in its own name — to one filing, one source
hash, one model, one model version, one region or profile, one prompt version, one settings set and
one protocol.

---

## 5. A coverage claim carries two verbatim anchors, never a byte offset

**Decision.** A model claims coverage of a source region by quoting its first stretch and its last
stretch verbatim, plus optional intermediate anchors. The backend locates both quotes in the
preserved bytes and the pair bounds an interval. **A model is never asked for a byte offset, a
character position, a line number or a percentage.**

**Why.** A model handed an artifact as text cannot count characters in it. Ask for an offset and it
will produce one, and **a fabricated offset resolves to the wrong place while looking exactly like
a real one** — it is a number in range, of the right shape, that a validator can only check by
trusting it. A quote either occurs in the preserved bytes or it does not, and that check runs
against the bytes SEC published rather than against the model's arithmetic. This is the same
reasoning that made source references quotes rather than offsets in the very first parser prompt;
this decision extends it from citations to coverage.

**Why two anchors give a denominator when a citation does not.** A resolved citation locates a
point. Two resolved anchors bound a *region*, and the union of every bounded region can be measured
against the union of every visible span in the inventory. `packages/completeness/intervals.py` does
that arithmetic, and its own docstring records the limit of it: **it proves the boundaries are real
and proves nothing about what is between them.** A model can claim a huge interval and say nothing
about its contents, which is why the ledger reports interval coverage BESIDE the span-level
accounting rather than instead of it, and why the gate requires both.

---

## 6. The anchor ladder has six levels and only four of them count

**Decision.** `packages/coverage_validation/references.py` searches six levels, in order, and
records which one hit:

```
1  EXACT                  character for character
2  UNICODE_NORMALISED     NFKC applied PER CHARACTER, so every output character maps back to one
                          input position
3  WHITESPACE_NORMALISED  runs of whitespace collapsed to one space
4  HYPHEN_NORMALISED      Unicode dashes and minus signs to ASCII, soft hyphens dropped, curly
                          quotes folded to straight
5  CASE_INSENSITIVE       a HUMAN-REVIEW CANDIDATE
6  APPROXIMATE            a HUMAN-REVIEW CANDIDATE: head and tail both occur, in order, close
                          enough together to be the same passage
```

**Levels 1 through 4 count as mechanically resolved. Levels 5 and 6 never count as proof, by
default, ever.** They locate something a reviewer can look at. Counting a case-folded near-match as
proof is how a citation rate starts flattering the model that produced it, and this repository has
already published one number that flattered a model by accident.

**Why four levels and not three.** Phase 2.1's twelve unresolved GPT OSS references were, on
inspection, small transcription defects over content demonstrably present in the parse — a
capitalised first letter, a non-breaking hyphen, a dropped space, an inserted word. Three of those
four classes now have a level. The fourth is level 6, and it is a candidate rather than a verdict.

**Why every level is searched in two spaces, and why entity decoding is the measurement that forced
it.** Each level runs over the preserved text as sent AND over the same bytes with markup tags
replaced by a space and character references decoded. The Apple filing measures why:

```
970 character references, and ZERO literal non-ASCII characters anywhere in the filing
the five most common: 655 of &#160;, 116 of &#8217;, 53 of &#8212;, 51 each of &#8220; and &#8221;
```

**Every apostrophe, non-breaking space, em dash and curly quote in this filing is an escape
sequence.** A model quoting a sentence back writes the CHARACTER. Without entity decoding in the
ladder, *every quote containing an apostrophe would have failed to resolve* — and the failure would
have been indistinguishable from a fabricated citation. A validator that reports invention when it
means encoding is worse than no validator, because it produces confident false accusations at
scale. Verified fixed: a quote containing a real em dash now resolves against a filing that
contains only `&#8212;`.

**The second space is not visible-content projection.** Nothing here changes what a model receives.
The model is still sent the complete compatible source set intact, in filed order, hash-verified.
Projection — backend code deciding what a model may SEE — remains an unapproved research option
under `rules.md` section 21 rule 7, and this decision does not touch it.

**Every offset reported is an offset into the ORIGINAL.** Each transform carries an index map built
in the same pass, and the resolution reports the original offset and the original matched LENGTH,
so a reviewer's highlight lands on the bytes that actually matched. Without that, a highlight lands
somewhere plausible and wrong, and it goes further wrong the more markup a filing carries — which
is exactly the filings where a reviewer most needs it. Levels are built LAZILY with identity
shortcuts, because eight eager transforms over a 732 KB document is ten million interpreter
iterations per artifact.

**`AMBIGUOUS` is its own outcome and is not resolved.** A quote occurring more than
`AMBIGUITY_THRESHOLD` times locates nothing in particular; counting it would inflate the rate with
references that point everywhere at once.

**The four new `Resolution` values are ADDITIONS.** Every value Phase 2 and Phase 2.1 recorded
still means exactly what it meant, so preserved evidence stays readable and re-deriving an old run
cannot silently change its counts.

---

## 7. A structured table contract is now mandatory, and the validator refuses to check meaning

**Decision.** The parser prompt families ask for a STRUCTURED TABLE: cells with grid positions, row
and column spans, the original cell text, an optional normalised value, a unit and a period label
in the model's own words, continuation links, image dependency, and explicitly unresolved cells.
`packages/multipart/tables.py` reads one; `packages/completeness/tables.py` validates it against
the source element it names.

**Why it became mandatory.** `table_count` was **ZERO in all seven Phase 2.1 runs.** Not one of the
five candidates emitted a structured table from a financial filing, on either the 1996 10-K405 or
the 2025 10-Q/A. No prompt in that phase asked for one, so it measures unprompted behaviour rather
than capability — and it left the largest open question of the proof untouched, because **a filing
parser that cannot preserve a table structure has not parsed a financial filing.** The Apple
benchmark makes the stake concrete: 41 table elements, 18 of them carrying 20 or more non-empty
cells.

**Narrative repetition of a number is not a table.** Phase 2.1's candidates carried tabular
material as node content and as source quotes, and the numeric validator confirmed 339 of 340 and
317 of 317 reported numbers occurred verbatim in the preserved bytes. That proves a number appears
in the filing. **It does not preserve which row, which column and which period it belonged to, and
those three facts are what a table IS.**

**What the validator checks, all of it against the preserved bytes.** The identifier is unique
within the parse; the source member it names was actually submitted; the source table element it
names exists in the mechanical inventory; its anchors resolve inside that element's byte range; the
grid has no two cells at one position and no zero or negative span; every cell's original text
occurs in that element's slice. **A cell that is neither found in the source nor declared
unresolved is a cell the model supplied from somewhere other than this filing, and that is the one
thing the validator refuses.**

**What it is forbidden to check, and it would be very easy to.** The title. The type. The unit. The
period label. Whether the header row is really a header. Whether the normalised `value` matches the
`text`. `rules.md` section 21 rule 2 forbids a universal filing taxonomy without explicit user
approval, and **a table schema is the most tempting place in this entire system to build one**:
every financial filing does have an income statement, so a `type` field validated against a list of
table kinds would feel obviously correct and would be the first brick of the ontology that rule
forbids. `type`, `unit`, `period_label`, `title` and every row role are carried verbatim,
displayed, and never checked against anything.

**An unresolved cell is a PASS.** A model saying "this cell is illegible in the source" has done
the right thing under section 21 rule 5; the gate counts it as exposed rather than as broken. Every
unknown key survives in `extra`, because the point of running several candidates through a new
contract is to find out what they actually emit.

---

## 8. `MECHANICAL_COMPLETENESS_CANDIDATE` is fourteen conjunctive conditions, not a score

**Decision.** The strongest verdict backend code may reach is `MECHANICAL_COMPLETENESS_CANDIDATE`,
and it is reached only when **all fourteen** of these hold. Each condition reports its own verdict
and its own evidence:

```
 1  every compatible source member is accounted for
 2  every human-included visible span is covered or explicitly unresolved
 3  no source region is silently omitted
 4  every human-included data-bearing table has a structured table artifact
 5  every structured table passes validation or exposes an unresolved cell
 6  every image is accounted for
 7  no effective artifact is unparseable
 8  no scheduled required job remains nonterminal
 9  no active truncation remains without replacement work
10  reconciliation produces no new unique work
11  gap deduplication reports no repeated unresolved loop
12  cost accounting is settled or clearly held
13  all unresolved items are shown
14  human review has not rejected the artifact
```

**What passing means, stated before anything else because it will be misread otherwise: the result
carries ENOUGH EVIDENCE TO UNDERGO HUMAN COMPLETENESS REVIEW.** It does not mean the parse is
complete. It does not mean the parse is correct. It is not a score, not a ranking, and not a
recommendation. **A result can pass every one of the fourteen and be wrong about every number in
the filing, because not one of them inspects meaning.**

**Why conjunctive and not weighted.** A weighted score lets a strong showing on twelve dimensions
outvote a silently omitted financial statement. That is not a hypothetical failure mode; it is the
arithmetic of every scoring function, and the whole point of this ADR is that averaging is how a
missing region disappears. Each condition is a distinct way a parse can be unreviewable, and none
substitutes for another.

**Why transport is not a fifteenth condition.** A run that never reached a provider already fails
several conditions on its own. Transport state is folded into condition 8's evidence instead, so an
`INCOMPATIBLE` pairing does not acquire a condition of its own that would make it look like a
distinct kind of failure. Under INTACT_SOURCE_ONLY, incompatibility is a RESULT and is recorded as
one.

**The only stronger statement is a person's.** `HUMAN_APPROVED_COMPLETE_FOR_THIS_FILING` is set by
a reviewer, never derived, and never generalised past the filing it was recorded against.

---

## Alternatives Considered

**Keep counting resolved references and call it coverage.** Rejected, and it is the alternative
that was in force until this decision. It is cheap, it is already implemented, and its number moves
in roughly the right direction. It is also **structurally incapable of seeing an omission**, which
is the single failure `rules.md` invariant 6a names. `352/364` would still be `352/364` if the
model had skipped every financial statement in the filing.

**Let the backend classify tables and spans, so no human review is needed.** Rejected. It is the
tempting one, because eight of Apple's 41 table elements are empty of text and seven are byte
duplicates, and it feels as though a few more rules would sort the rest. Those two ARE mechanical
and they are recorded as suggestions. The remainder — which of the 18 substantive elements is a
financial statement and which is a layout grid — is a judgement about what filing content means,
which invariant 14 and section 21 rule 1 forbid in code. **The repository has built this exact
thing twice and deleted it twice**, and both times it passed every gate that existed. ADR-0016 and
ADR-0017 are the record.

**Use a judge model to score completeness.** Rejected. It reintroduces the defect at one remove: a
judge's verdict is a model assertion, and `rules.md` invariant 13 and section 21 rule 4 both
require coverage to be PROVED against the preserved bytes rather than asserted by any model. A
judge would also need the same intact source under the same INTACT_SOURCE_ONLY rule and would cost
roughly what a parse costs, so it would double the spend to produce evidence weaker than an
interval check. It would additionally make every completeness figure depend on a second model's
version, region and prompt.

**Score completeness as a single weighted number.** Rejected: see decision 8. It is the shape that
lets twelve good dimensions outvote a missing statement.

**Derive the required set once and reuse it across filings.** Rejected. It is a universal filing
taxonomy assembled incrementally, which section 21 rule 2 forbids without explicit user approval,
and it is the ADR-0016 drift with a different starting point. One issuer is a fixture, never a
specification.

**Ask the model for byte offsets instead of quotes.** Rejected: see decision 5. A fabricated offset
is indistinguishable from a real one until it is dereferenced, and by then it has been counted.

**Validate the semantic fields of a structured table — unit, type, period.** Rejected: see decision
7. It is the first brick of the forbidden ontology and it is the brick that looks most like
diligence.

---

## Consequences

**Easier.** For the first time the repository can answer "what did this parse never mention", and
can answer it with an exact count rather than an impression. A reviewer sees which spans, tables
and images are unaccounted rather than reading a rate. Two candidates become comparable on a
denominator neither of them supplied. A citation containing an apostrophe stops being reported as a
possible fabrication.

**Harder, and it is not a small cost.** The benchmark now requires **human classification of 1,750
visible spans, 41 table elements and 2 images before it produces a completeness figure at all**,
because everything unreviewed defaults to `REQUIRES_REVIEW` and blocks the gate. The structured
table contract and two resolvable anchors per coverage claim both increase output per part, which
increases the number of parts, which increases the number of calls, each re-sending the complete
intact source. **The hardened protocol raises cost; it does not lower it**, and the dry-run plan in
the Phase 2.2 record is a floor for that reason.

**Constrained.** The backend can never acquire a semantic opinion about which parts of a filing
matter, in this phase or a later one, without reversing this ADR in writing. No completeness figure
may be quoted outside the accession and `source_set_sha256` it was computed against. No mechanical
gate result may be presented as a quality judgement or used to rank a parser.

---

## Migration Impact

**Nothing already preserved is rewritten.** The four new `Resolution` values are additions; every
Phase 2 and Phase 2.1 value means what it always meant, and re-deriving an old run cannot silently
change its counts. The seven Phase 2.1 runs and the thirty Phase 2 runs remain readable exactly as
recorded, with their reference rates intact and now correctly labelled as reference rates.

Reversing this decision would mean deleting `packages/source_inventory`, `packages/completeness`,
`packages/multipart/tables.py`, the four added ladder levels and the structured-table prompt
family, and returning to a reference rate as the coverage figure. The preserved evidence would
survive, because it is exact request and response bytes on disk rather than an interpretation — but
the denominator would go, and with it the ability to count an omission.

**The human benchmark truth is versioned and superseded, never edited.** A future correction to a
classification produces version N+1 and leaves version N on disk, so any completeness figure stays
reproducible against the version it was computed with.

---

## Revisit Conditions

```
a second filing, from a different issuer, a different filing agent and a different transport era,
    is classified by a human — at which point the two required sets may be COMPARED, and any
    claim about filings in general still requires the measurement rules.md section 21 rule 14
    demands rather than a generalisation from these two
the fourteen conditions are measured against a real run and one of them proves to be
    unsatisfiable for a reason unrelated to completeness, which would make it a defect in the
    condition rather than evidence about the parse
a candidate model emits structured tables under the new contract and the table dimension turns
    out to be measuring the prompt rather than the model, which repeat runs would show
levels 5 and 6 of the ladder are reviewed by a human often enough to measure how many of them a
    person accepts; a high acceptance rate is an argument for a new level 5, never for counting
    the existing one as proof
the human classification cost of a single filing proves prohibitive at the span level, which
    would be an argument for a coarser inventory unit and NEVER for a mechanical default
```
