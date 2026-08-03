# Standard Content-Unit Summarization

> **RE-FOUNDED 2026-08-02 ON MEASURED EVIDENCE.** A representative corpus of **112 SEC issuers and
> 613 filings across six transport eras** was acquired and measured — dated Phase 1 evidence, not a
> permanent constant — and it refuted the assumptions the deterministic semantic parser rested on.
> The product is an orchestrator-driven, model-first SEC filing product: the backend acquires,
> preserves, transports, orchestrates and VALIDATES; a user-selected parsing model determines what
> a filing means. The user selects four models independently — parsing, image, summary, and
> analysis/chat. The current authorized input mode is `INTACT_SOURCE_ONLY`. The deterministic
> content ontology, migration `0003` and the local application database are withdrawn. Sections
> below that describe the withdrawn design are historical.
>
> **NO MODEL HAS BEEN INVOKED AND AWS IS NOT CONFIGURED.** Authoritative:
> `docs/adr/ADR-0016-corpus-first-model-first-architecture.md` and `roadmap.md`.

IMPLEMENTATION STATUS: PLANNED (Sprint 5); the gateway it depends on is IMPLEMENTED
OWNER PACKAGE: `packages/summarization`
PROMPTS: `prompts/footnote-summary/v1.0.0/` (footnote target); further targets versioned beside it
SCHEMA: `docs/llm/summary-schema.yaml`
ARCHITECTURE: `docs/adr/ADR-0016-corpus-first-model-first-architecture.md`
ARTIFACT SHAPE: `docs/api/openapi.yaml` (ParsedArtifact, SummaryArtifact)

> **Corrected in Sprint 4.1.** This document previously assumed the summarized corpus was the
> footnote set, that one canonical footnote was the only unit of work, and — through
> `docs/llm/cost-model.md` — that filing cost was footnote count times cost per footnote. All
> three were wrong: a 10-K's summarized surface is 67 required units, of which 13 are footnotes.

---

# CURRENT DIRECTION — AUTHORITATIVE. Everything below this section is historical.

**NO SUMMARY HAS EVER BEEN GENERATED.** This describes intended behaviour, not observed behaviour.

## Summarization consumes an ACCEPTED PARSE, not a filing

The summary model never sees the raw filing. It receives the accepted parsed artifact and its
supporting evidence, after coverage, citation and numeric validation has passed. A parse that
failed validation is not summarized.

## The summary is a SEPARATE artifact

It has its own id, its own version, its own lineage, and its own storage. It references the parsed
artifact versions it was grounded in.

```
REGENERATING A SUMMARY DOES NOT REQUIRE REPARSING while the accepted parse is unchanged.
SUPERSEDING A PARSE INVALIDATES dependent summaries rather than leaving them silently attached.
```

That separation is the whole point: choosing a different summary model, or a newer prompt, must not
cost another parse.

## What must be summarized

**Complete-content coverage extends beyond footnotes.** Every required node of the accepted parsed
artifact needs an accepted active summary before the filing is fully summarized — not the
footnotes, not the sections a model finds interesting.

**Every financial-statement footnote the accepted parse identifies remains an independent required
summary target.** Never merged into a single "Notes" summary. This is the one semantic guarantee
that survived the removal of the taxonomy, and it survived because merging is how content
disappears without anything reporting a failure.

There is **no fixed list of section kinds** to summarize. The parse says what the filing contains;
the summarizer covers it.

## Grounding and evidence

Original source references remain available from every summary. A summary is navigation and
explanation — it is **never evidence** for a material claim, and a number in a summary traces back
to the source it came from.

## Boundary

Model-visible synthetic content is unmarked plain text or exactly one unfenced YAML 1.2 document.
The intact original SEC artifact may be sent in whatever syntax SEC published, by provenance.

## Variability and versioning

Model output varies between runs. Summaries are versioned and superseded, never overwritten, and
the prompt version and model id are recorded on every one.


## Summary targets

**Every canonical content unit whose `summary_required` is true gets an accepted active summary.**
That flag is set from the unit's TYPE and its position in the filed hierarchy — never from a
materiality judgement, and never by a model.

| Target | Unit type | Notes |
|---|---|---|
| Filing summary | `FILING_ROOT` | Aggregate; built only from accepted child summaries |
| Part summary | `PART` | Aggregate over its Items |
| Item summary | `ITEM` | The main narrative target |
| Subsection summary | `SUBSECTION` | Only where the Item is large enough to need one |
| Cover-page summary | `COVER_PAGE` | Identity, filer status, incorporated documents |
| Financial-statement summary | `FINANCIAL_STATEMENT` | One per primary statement |
| **Footnote summary** | `FINANCIAL_STATEMENT_FOOTNOTE` | **One per footnote, independently. Unchanged.** |
| Schedule summary | `FINANCIAL_SCHEDULE` | |
| Exhibit summary | `EXHIBIT` | Human-readable exhibits |
| Certification summary | `CERTIFICATION` | |
| Consent summary | `CONSENT` | |
| Signature record | `SIGNATURE` | Structured signer list rather than prose, where the block is a signature table |
| Incorporated-reference status | `INCORPORATED_REFERENCE` | What is incorporated, from where, and whether resolved |
| Other disclosure | `OTHER_DISCLOSURE` | Anything human-readable with no more specific type |

```
THE INVARIANT

Every source block belongs to a required canonical unit, and every required unit is completely
represented by one or more accepted summaries.

Financial-statement footnotes additionally keep their own guarantee: exactly one canonical record
and exactly one active accepted summary EACH. The general rule does not replace it, and a
"Notes" summary covering thirteen footnotes satisfies neither.
```

## Unit of work

**One canonical content unit per model request, or one deterministic leaf chunk of one.** Not one
per filing, not one per paragraph, not one per TextBlock fact.

Batching several units into one request is permitted only after benchmark evidence shows it does
not increase omission or attribution error, and **never across unrelated Items**. The failure mode
it risks is exactly the one the product cannot tolerate: a model asked to summarize twelve
disclosures will summarize the interesting ones well and the routine ones thinly, or silently
merge two. Small sibling blocks may share a unit only where their filed hierarchy and meaning
justify it.

## Hierarchical chunking for oversized units

Item 1A Risk Factors and Item 7 MD&A both exceed a comfortable context on a large filer. Measured
on one FY2025 10-K: 106 source blocks each.

```
1  Create stable deterministic leaf chunks along filed block boundaries.
2  Summarize every leaf chunk.
3  Validate every leaf summary.
4  Build the unit summary from ACCEPTED child summaries plus required evidence.
5  Never silently truncate.
6  Never summarize only the first context window.
7  Never omit a child chunk because it appears routine.
8  Preserve chunk-to-source and aggregate-to-chunk lineage.
```

A unit whose aggregate was built this way records that fact, and the dashboard discloses it. An
aggregate over incomplete children is `PARTIAL`, never active.

## Input assembly

```
1  identity            cik, accession, form, period_end, unit id, hierarchy path, type, title
2  filed position      part number, item number, ancestor titles
3  unit narrative      the unit's own normalized text, or this chunk's span
4  child evidence      attached blocks; for a footnote, its policy and detail blocks
5  tables              structured, both compact and readable renderings
6  related facts       filed XBRL facts applicable to this unit
7  prior-period unit   the comparable unit, when available and within budget
8  instructions        coverage, citation, and no-outside-knowledge flags
```

Everything is normalized before assembly. Raw SEC HTML, inline XBRL, and XBRL instances never
reach the model. Assembly order is deterministic so the payload hash is stable, which makes the
idempotency key meaningful.

## Complexity classification

Drives the output target, not the decision to summarize. **Every required unit is summarized.**

```
routine    below the source-token threshold, no tables, classification routine  ->  75-200 words
moderate   one or two tables, or moderate source length                        -> 150-350 words
complex    several tables, or above the complex source threshold               -> 300-800 words
oversized  above the safe context budget                                       -> chunked, above
```

## Batch behaviour

Batches are packed **by measured payload bytes** with headroom, not by request count, because the
payload cap is usually the binding constraint. Batch requests expire silently, so a watchdog runs
on a schedule shorter than the expiry window and re-queues expired requests. Coverage counters
make a hole visible; the watchdog prevents it.

## Retry and repair

```
transient provider failure    bounded backoff, up to 3 attempts
boundary rejection            one repair attempt with a corrective instruction, then review
schema validation failure     one repair attempt naming the failing fields, then review
numeric validation failure    no repair; route to review
                              a model that misstated a number should not be asked to try again
citation validation failure   one repair attempt, then review
```

Numeric failures deliberately have no repair path. Re-prompting a model that produced a wrong
figure invites a differently wrong figure.

## Truncation detection

A response whose parse fails at the document end, or whose `stop_reason` indicates the output cap
was reached, is truncated. It is never partially accepted, because a truncated summary looks
complete to a reader.

## Persistence and supersession

Identity of a summary:

```
accession + content_unit_id + chunk_ordinal + content_sha256 + parser_version
          + prompt_version + model_provider + model_id + output_schema_version
```

`content_unit_id` replaces the former `canonical_footnote_id`; a footnote unit carries both, so a
footnote summary's identity is unchanged in substance. `chunk_ordinal` is null for a unit
summarized in one pass and set for each leaf chunk of an oversized unit, so a chunk and its
aggregate are separately addressable and separately supersedable.

A new version supersedes the previous by setting `superseded_at`. Accepted historical outputs are
never overwritten, so a prompt or model regression is recoverable by reactivating the prior
version.

## Reprocessing triggers

A new prompt version, a new model, a parser change altering source text, or a hierarchy change
altering the unit itself. Each is part of the identity above, so reprocessing is a consequence of
the key changing rather than a separate decision.

An aggregate summary is additionally reprocessed when any accepted child summary it was built from
is superseded — otherwise the parent would keep asserting a synthesis of evidence that no longer
exists.

## Model-visible format, unchanged

The boundary in `rules.md` section 3 and ADR-0013 applies to every summary target identically:

```
model-visible content is unmarked normalized plain text, or exactly one unfenced YAML 1.2 document
no Markdown        no JSON        no XML        no raw XBRL        no HTML
no provider tool schemas, and no native tool calling
```

Widening the summarized surface does not widen the content boundary.
