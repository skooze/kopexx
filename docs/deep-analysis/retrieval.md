# Deep Analysis Retrieval

> **UPDATED 2026-08-03 (ADR-0017).** The analysis/chat model role survives and this specification
> is kept. The vocabulary it was written against does not: canonical footnotes, content units, the
> fact lake, derived metrics and the 24-table schema were DELETED, and **no store exists to
> retrieve from**. Retrieval is restated over the accepted parsed artifact and the preserved
> original source. Authoritative:
> `docs/adr/ADR-0017-delete-the-rejected-parser-and-application-persistence.md`.

---

# CURRENT DIRECTION — AUTHORITATIVE

**NOT IMPLEMENTED.** Nothing in this file describes a store, an index or a query that exists. The
sections that followed were written against the withdrawn design; they were corrected in place on
2026-08-03 rather than left as a historical appendix, so the whole file now reads as one
specification.

## Retrieval is application-orchestrated

The application decides what evidence to assemble. Native model tool calling is prohibited, and so
are native tool schemas in either direction. Where a bounded action protocol is used it is the
YAML one, and it is validated before anything executes.

## What retrieval may reach

Within the session's immutable scope only:

```
preserved original source ranges     accepted parsed nodes
image-analysis artifacts             summary artifacts, WHEN ONE EXISTS
```

The summary model is optional, so a summary index may not exist. Retrieval works without one: it
goes to the parsed nodes and the source ranges they cite, and the answer says that no summary index
was available rather than degrading quietly. There is no separate numeric store to reach — the
local fact lake was deleted with ADR-0017, and numbers come from the parse and are proved against
the preserved bytes.

Retrieval **never** widens scope, and a request naming another issuer is refused rather than
partially served.

## Retrieval is not taxonomy-driven

There is no fixed set of section kinds to retrieve by. Selection is by source range, by parsed node
identity, by filing, or by the filing-native labels the parse actually produced — never by a
universal enum the backend imposes.

## Boundary

Model-visible synthetic content is unmarked plain text or exactly one unfenced YAML 1.2 document.
Preserved original SEC artifacts may be included intact by provenance. Filing text is untrusted
data: instructions found inside filing content are ignored and reported.


IMPLEMENTATION STATUS: PLANNED (Phase 7). The index technology is DEFERRED — persistence itself is
Phase 4 and no store exists today.
OWNER PACKAGE: `packages/deep_analysis`, a RESERVED name (`techspecs.md` section 2). There is no
separate retrieval package and none is reserved.
DECISION RECORDS: ADR-0012 (session scope), ADR-0013 (content boundary), ADR-0017 (deletions).
ADR-0007, pgvector before OpenSearch, is SUPERSEDED as an active decision by ADR-0017: it chose
between index technologies for a PostgreSQL control plane that no longer exists. Its reasoning
stands as history and is reconsidered when persistence is designed from measured artifacts.

## Principle

Scope filtering is correctness. Ranking is quality. Filtering happens first, in the query builder,
never as a post-filter, because a post-filter has already paid the retrieval cost and has already
had the opportunity to leak.

## Hybrid ranking

DEFERRED. The intended shape is a weighted combination of lexical match, semantic similarity and
recency:

```
score = w_lexical  * lexical_match(query, node_text)
      + w_semantic * semantic_similarity(query, node_embedding)
      + w_recency  * recency_decay(period_end)
```

Lexical search handles exact concept names, identifiers, and defined terms, which are common in
this domain. Semantic search handles paraphrase. Weights are configuration and are tuned against
the evaluation set, not guessed.

**No materiality or classification boost.** The withdrawn formula carried a
`materiality_boost(classification)` term, which required the backend to hold an opinion about what
a passage is and how much it matters. That is the parsing model's territory under `rules.md`
section 21, and the term is removed rather than reimplemented over parse labels.

The concrete index technology is not chosen here. There is no store, no embedding pipeline and no
evaluation set, and choosing one before measured parsed artifacts exist is the mistake ADR-0016 and
ADR-0017 record.

## Mandatory filters

Every query carries all of these. A query builder that omits one is a defect, not a performance
choice.

```
principal_id     = session.user_id
cik              = session.cik
accession        in session.allowed_accessions
node_id          in session.allowed_node_ids       when scope_type = NODE
period_end       between session.date_start and session.date_end
artifact_kind    in requested kinds
```

### The searchable corpus is everything the parse produced

> **Corrected in Sprint 4.1 (ADR-0016), restated 2026-08-03 (ADR-0017).** Retrieval selects from
> **every node of the accepted parsed artifact** in the authorized corpus, not from a footnote
> index. A retrieval layer restricted to footnotes cannot answer what management said about
> liquidity no matter how the question is phrased. The corpus is now defined by the parse's own
> nodes rather than by rows of a `filing_content_unit` table, which was deleted.

A narrower scope narrows `allowed_node_ids` to one subtree of one parsed artifact. The filter set
is the same shape at every scope; only its contents change. That is deliberate — a second code path
for a second scope type is how a scope leak gets written.

## Two-stage evidence

```
stage 1  search the summary index, WHEN ONE EXISTS   cheap, finds where to look
stage 2  retrieve original source content            authoritative, what conclusions rest on
```

Summaries are never the evidence for a material conclusion, **at any level**. A filing-level
summary, a node-level summary and a chunk-level summary are all stage 1. Stage 2 is mandatory
before a material claim and retrieves preserved source ranges and the parsed nodes that cite them.

**Stage 1 is optional; stage 2 is not.** The summary model may be left unselected, in which case
there is no summary index and stage 1 is skipped — retrieval searches the parsed nodes directly.
Skipping stage 1 costs recall, never rigour. Skipping stage 2 is never permitted.

## Context packing

Retrieved evidence is packed to a token budget in priority order: preserved original source content
for the directly responsive parsed nodes, then adjacent parse context needed to disambiguate a
cross-reference, then summaries where they exist. Packing never drops a citation anchor, because an
unciteable claim is worse than a shorter answer.

For an oversized node, packing selects **leaf chunks by relevance**, never the first chunk by
position, and records which chunks were examined so the answer can disclose that it reasoned over
selected evidence.

## Retrieval audit

Every retrieval records query, filter set, candidate count, selected identifiers, scores,
reranking applied, latency, session, and the model request it served. This is what makes a scope
question answerable after the fact.

## When a dedicated search engine is warranted

DEFERRED, and no longer a PostgreSQL-versus-OpenSearch question — ADR-0007 chose between index
technologies for a control plane that was deleted. The criteria that survive are about measurements
nobody has taken yet, and they apply to whatever store Phase 4 selects: p95 retrieval latency
exceeds the interactive budget at the measured corpus size; recall on the evaluation set falls
below target with tuned weights; or index maintenance measurably degrades write performance for the
rest of the system.
