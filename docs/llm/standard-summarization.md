# Standard Footnote Summarization

IMPLEMENTATION STATUS: PLANNED (Sprint 5); the gateway it depends on is IMPLEMENTED
OWNER PACKAGE: `packages/summarization`
PROMPTS: `prompts/footnote-summary/v1.0.0/`
SCHEMA: `docs/llm/summary-schema.yaml`

## Unit of work

**One canonical footnote per model request.** Not one per filing, not one per TextBlock fact.

Batching several footnotes into one request is permitted only after benchmark evidence shows it
does not increase omission or attribution error. The failure mode it risks is exactly the one the
product cannot tolerate: a model asked to summarize twelve footnotes will summarize the
interesting ones well and the routine ones thinly, or silently merge two.

## Input assembly

```
1  identity            cik, accession, form, period_end, footnote id, number, title
2  parent narrative    the footnote's main text block
3  child blocks        every policy and detail block attached to it
4  tables              structured, both compact and readable renderings
5  related facts       filed XBRL facts referenced by the footnote
6  prior-period note   the comparable footnote, when available and within budget
7  instructions        coverage, citation, and no-outside-knowledge flags
```

Everything is normalized before assembly. Raw SEC HTML, inline XBRL, and XBRL instances never
reach the model. Assembly order is deterministic so the payload hash is stable, which makes the
idempotency key meaningful.

## Complexity classification

Drives the output target, not the decision to summarize. Every footnote is summarized.

```
routine    below the source-token threshold, no tables, classification routine  ->  75-200 words
moderate   one or two tables, or moderate source length                        -> 150-350 words
complex    several tables, or above the complex source threshold               -> 300-800 words
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
accession + canonical_footnote_id + source_sha256 + parser_version
          + prompt_version + model_provider + model_id + output_schema_version
```

A new version supersedes the previous by setting `superseded_at`. Accepted historical outputs are
never overwritten, so a prompt or model regression is recoverable by reactivating the prior
version.

## Reprocessing triggers

A new prompt version, a new model, a parser change altering source text, or a grouping change
altering the footnote itself. Each is part of the identity above, so reprocessing is a
consequence of the key changing rather than a separate decision.
