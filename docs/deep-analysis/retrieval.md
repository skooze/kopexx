# Deep Analysis Retrieval

IMPLEMENTATION STATUS: PLANNED (Phase 9)
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
footnote_id      in session.allowed_footnote_ids    when scope_type = FOOTNOTE
period_end       between session.date_start and session.date_end
source_type      in requested types
```

## Two-stage evidence

```
stage 1  search the summary index          cheap, finds where to look
stage 2  retrieve original source content  authoritative, what conclusions rest on
```

Summaries are never the evidence for a material conclusion. Stage 2 is mandatory before a material
claim.

## Context packing

Retrieved evidence is packed to a token budget in priority order: original source content for
directly responsive footnotes, then deterministic facts and metrics, then summaries for context.
Packing never drops a citation anchor, because an unciteable claim is worse than a shorter answer.

## Retrieval audit

Every retrieval records query, filter set, candidate count, selected identifiers, scores,
reranking applied, latency, session, and the model request it served. This is what makes a scope
question answerable after the fact.

## OpenSearch promotion criteria

Move off PostgreSQL when any holds: p95 retrieval latency exceeds the interactive budget at the
measured corpus size; recall on the evaluation set falls below target with tuned weights; or
pgvector index maintenance measurably degrades control-plane write performance.
