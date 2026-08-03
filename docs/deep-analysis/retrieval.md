# Deep Analysis Retrieval

---

# CURRENT DIRECTION — AUTHORITATIVE. Everything below this section is historical.

**NOT IMPLEMENTED.**

## Retrieval is application-orchestrated

The application decides what evidence to assemble. Native model tool calling is prohibited, and so
are native tool schemas in either direction. Where a bounded action protocol is used it is the
YAML one, and it is validated before anything executes.

## What retrieval may reach

Within the session's immutable scope only:

```
preserved original source ranges     accepted parsed nodes
summary artifacts                    image-analysis artifacts
numeric evidence
```

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


IMPLEMENTATION STATUS: PLANNED (Sprint 7; pgvector deferred to Stage 2 W-6)
OWNER PACKAGE: `packages/retrieval`
DECISION RECORD: `docs/adr/ADR-0007-pgvector-before-opensearch.md`

## Principle

Scope filtering is correctness. Ranking is quality. Filtering happens first, in the query builder,
never as a post-filter, because a post-filter has already paid the retrieval cost and has already
had the opportunity to leak.

## Hybrid ranking

```
score = w_lexical * ts_rank_cd(fts_vector, query)
      + w_semantic * (1 - (embedding <=> query_embedding))
      + w_recency  * recency_decay(period_end)
      + w_material * materiality_boost(classification)
```

Lexical search handles exact concept names, identifiers, and defined terms, which are common in
this domain. Semantic search handles paraphrase. Weights are configuration and are tuned against
the evaluation set, not guessed.

## Mandatory filters

Every query carries all of these. A query builder that omits one is a defect, not a performance
choice.

```
principal_id     = session.user_id
cik              = session.cik
accession        in session.allowed_accessions
content_unit_id  in session.allowed_content_unit_ids   when scope narrows below the filing
footnote_id      in session.allowed_footnote_ids       when scope_type = FOOTNOTE
period_end       between session.date_start and session.date_end
source_type      in requested types
```

### The searchable corpus is the whole filing

> **Corrected in Sprint 4.1 (ADR-0016).** Retrieval selects from **all** `filing_content_unit`
> rows in the authorized corpus — cover page, Parts, Items, narrative, statements, every footnote,
> schedules, exhibits, certifications and signatures — not from a footnote index. A retrieval
> layer restricted to footnotes cannot answer what management said about liquidity no matter how
> the question is phrased.

A narrower scope narrows `allowed_content_unit_ids` to one subtree. The filter set is the same
shape at every scope; only its contents change. That is deliberate — a second code path for a
second scope type is how a scope leak gets written.

## Two-stage evidence

```
stage 1  search the summary index          cheap, finds where to look
stage 2  retrieve original source content  authoritative, what conclusions rest on
```

Summaries are never the evidence for a material conclusion, **at any level of the hierarchy**. A
filing summary, a Part summary, an Item summary and a leaf-chunk summary are all stage 1. Stage 2
is mandatory before a material claim and retrieves source blocks, tables, or filed facts.

## Context packing

Retrieved evidence is packed to a token budget in priority order: original source content for
directly responsive content units, then deterministic facts and metrics, then summaries for
context. Packing never drops a citation anchor, because an unciteable claim is worse than a
shorter answer.

For an oversized unit, packing selects **leaf chunks by relevance**, never the first chunk by
position, and records which chunks were examined so the answer can disclose that it reasoned over
selected evidence.

## Retrieval audit

Every retrieval records query, filter set, candidate count, selected identifiers, scores,
reranking applied, latency, session, and the model request it served. This is what makes a scope
question answerable after the fact.

## OpenSearch promotion criteria

Move off PostgreSQL when any holds: p95 retrieval latency exceeds the interactive budget at the
measured corpus size; recall on the evaluation set falls below target with tuned weights; or
pgvector index maintenance measurably degrades control-plane write performance.
