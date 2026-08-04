# ADR-0022 — Lossless source projection

STATUS: ACCEPTED
DATE: 2026-08-04
PHASE: 2.2
AMENDS: `rules.md` section 21 rule 7, and the ORIGINAL-SOURCE EXCEPTION in `rules.md` section 3
BUILDS ON: ADR-0016, ADR-0017, ADR-0020, ADR-0021

---

## Context

`rules.md` section 21 rule 7 has listed **visible-content projection** as an unapproved research
option since it was written, alongside the sentence that has stopped it twice:

> A lower token cost is not authorization.

That sentence was right both times it was applied, and it is right now. What has changed is that
the cost is no longer the argument.

### The measurement

Apple's 10-Q, accession `0000320193-25-000008`, the fixed completeness benchmark:

```
as SEC published it, markup and all      915,890 characters   ~254,000 tokens
the words a human actually reads         142,096 characters   ~ 39,000 tokens
                                         ─────────────────
markup overhead                                6.4x
```

Sent intact, the filing exceeds the **measured runtime context** of four of the five approved
candidates. The fifth, Qwen3 235B A22B at a measured 262,144, refused it: *"you requested 128 output
tokens and your prompt contains at least 262,017 input tokens"*. One hundred and twenty-eight output
tokens — a number that could not parse anything and existed only to measure — and it still did not
fit.

**Not one approved candidate was ever given the chance to parse this filing.** Every one of them
refused at the door, and the thing they refused was 84 percent
`<span style="color:#000000;font-family:'Helvetica',sans-serif;font-size:9pt">`.

### Why this is not the argument the rule was written to refuse

Rule 7 exists because of ADR-0016 and ADR-0017: this repository twice built something that decided,
in backend code, what a filing contained — and the second time it did so while passing every gate it
had. The deleted accession classifier ruled that a courtesy PDF "duplicated" the primary document
and suppressed a filed source range on that judgement.

The concern is **backend code deciding what matters**. It is not "the bytes change shape."

---

## Decision

**A lossless, offset-anchored projection of a preserved filing may be sent to a parsing model in
place of the filing's own bytes, when the run explicitly selects it.**

`packages/projection` produces ONE YAML document carrying:

```
blocks   every visible text span the mechanical inventory found, in document order, each with
         the member it came from and its character offset in that member
tables   every `table` element, as the GRID its own markup describes — row, column, row span,
         column span, cell text
images   every filed image, by identity, hash and dimensions. The BYTES still travel separately
         and intact to a multimodal parser; a projection cannot carry a JPEG.
```

Measured on the benchmark filing: 915,890 characters become 243,107, a 3.77x reduction, carrying
**1,750 of 1,750** visible spans, **41 of 41** table elements and **2 of 2** images.

### The five constraints that make this narrow

**1. It carries no judgement.** There is no title, no section, no type, no classification and no
statement that anything matters. A block is a run of characters at an offset. What any of it MEANS
is still the selected parsing model's decision, and `rules.md` invariant 14 and section 21 rule 1
are untouched — this transform changes SYNTAX and never MEANING.

**2. Lossless is CHECKED, not asserted.** `project` refuses to return a document that would not
carry every visible span, every table element and every image the inventory measured. It raises
`ProjectionIncompleteError` and the run refuses. An assertion in a docstring is not a check, and the
failure mode this rule was written about is exactly a projection that quietly dropped something.

**3. It is reversible, and that is what the offsets are for.** Every block records its member and
its character offset in that member. A model quoting a block is quoting characters that exist at a
known position in the bytes SEC published, and `packages/coverage_validation` resolves every citation
against those bytes — never against the projection. The projection is what the model reads; the
original is what every claim is proved against.

**4. The original is untouched, preserved and authoritative.** Nothing is rewritten, replaced or
superseded. `rules.md` section 21 rule 3 is unchanged.

**5. It is never the default and never silent.** `SOURCE_INPUT_MODE` is `intact` unless a run says
otherwise, the mode is recorded on the run, and a `MultipartSettings` that names anything else
raises. Which mode produced a measurement changes what the measurement means.

### What the tables buy, and why the cheaper option was rejected

Flattening the filing to plain prose costs about 39,957 tokens against the projection's 61,951. The
extra 22,000 tokens carry the table grids, and they are the most valuable tokens in the document.

Flattened, Apple's income statement reads `Total net sales 124,300 119,575`. There is no way to
recover that these are two period columns, which is which, or that the row is a total. **On a
financial filing that is not compression, it is data loss** — and it is precisely the "semantic
slicing" half of rule 7, arriving through the back door of a cheaper option.

The markup is not all noise. The `<table>` structure is signal, and the projection keeps it in the
one form that survives: a grid.

---

## Amendments

### `rules.md` section 21 rule 7

Visible-content projection is no longer unapproved. It is authorized in the single form specified
above: **lossless over everything human-readable, mechanically checked, offset-anchored, explicitly
selected, and carrying no semantic judgement.**

**STILL UNAPPROVED AND STILL BOUND BY RULE 7:** mechanical multipart INPUT, in which backend code
divides a filing and sends the pieces; any projection that DROPS content, summarises it, reorders
it, retitles it or classifies it; and any hybrid of those with this one. **A lower token cost is
still not authorization for any of them.**

### `rules.md` section 3, the ORIGINAL-SOURCE EXCEPTION

The exception said, in as many words:

> Never rewrite an original artifact into YAML to satisfy the synthetic-content rule.

That sentence is retained and narrowed. Its target was a caller trying to launder a preserved
artifact through YAML so it would pass the boundary validator — admitting by SYNTAX what may only be
admitted by PROVENANCE. A projection does not do that and does not claim to: **it is SYNTHETIC
content**, it goes through the payload compiler and the boundary validator like every other
synthetic component, and it is never presented as a preserved artifact. The original artifact
travels intact, or it does not travel.

---

## Alternatives considered

**Send the filing intact and add a larger-context model.** Genuinely available: Claude at 1M, Llama
4 Scout at 10M, Nova 2 Lite at 1M. Rejected as the *only* answer rather than on its merits — it
costs 4x the tokens forever, does nothing for the 12 percent of the measured corpus above ~1M
estimated tokens, and makes affordability depend on one vendor's context window. Nova 2 Lite was
added as a candidate anyway; the two are complements.

**Strip markup to plain text.** Cheaper by 22,000 tokens and destroys every table. Rejected above.

**Send SEC's own rendered `R*.htm` files.** EDGAR generates them and they are already in the
package. Rejected: they are SEC's Interactive Data renderer output, not the filer's document, and
`source_transport` correctly dispositions them `SEC_GENERATED_RENDERING`. Substituting a renderer's
view for the filed document is a provenance change wearing a compression costume.

**Do nothing.** The honest option, and it was the state of the world for one afternoon: record that
no approved candidate can parse a real modern 10-Q and stop. Rejected because the finding underneath
it is that the models were never the problem.

---

## Consequences

All seven candidates now fit the benchmark filing, with 58,000 to 192,000 tokens of context to
spare, and **every one of them is limited by its output cap rather than by its context**. That
reframes the whole protocol: multipart exists to work around an 8,000-token output ceiling, and a
64,000 or 128,000-token model expresses a filing this size in one or two responses.

The projection must be built before preflight, because a guard that sized the intact bytes while the
run sent the projection would authorize one request and issue another.

**A projected run and an intact run are not comparable.** They are different measurements of
different requests, and the mode is recorded on every run so nobody compares them by accident.

---

## Revisit conditions

- A projection is found that loses content the mechanical check did not catch. That is a defect in
  the check, and the authorization narrows until it is closed.
- The inventory's span or table extraction is shown to mis-measure a filing shape, since the
  projection is only as lossless as the inventory is complete.
- A candidate appears whose intact-source economics make the projection unnecessary.
- Anyone proposes extending this to drop, summarise, reorder or classify content. That is a
  different decision and it needs a different ADR.
