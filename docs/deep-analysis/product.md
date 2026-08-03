# Deep Analysis Product

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
> **UPDATED 2026-08-03 (ADR-0017).** The analysis/chat model role SURVIVES and this specification
> is kept. What is gone is the vocabulary it was written against: canonical footnotes, content
> units, the fact lake, derived metrics and the 24-table schema were DELETED with
> `packages/persistence` and `packages/dera_notes`. Scopes and retrieval below are stated over the
> ACCEPTED PARSED ARTIFACT and the preserved original source instead. **This supersedes the
> sentence above about historical sections:** the withdrawn passages were corrected in place, so no
> part of this file is a historical appendix. Authoritative:
> `docs/adr/ADR-0017-delete-the-rejected-parser-and-application-persistence.md`.
>
> **NO MODEL HAS BEEN INVOKED AND AWS IS NOT CONFIGURED.** Authoritative:
> `docs/adr/ADR-0016-corpus-first-model-first-architecture.md` and `roadmap.md`.

IMPLEMENTATION STATUS: PLANNED (Phase 7)
OWNER PACKAGE: `packages/deep_analysis` — a RESERVED name (`techspecs.md` section 2). The
directory does not exist and is created by the change that writes its first module.
DECISION RECORDS: ADR-0012 (session scope), ADR-0013 (content boundary), ADR-0017 (deletions)

## What it is

A deliberate, scoped, metered, auditable analytical session bound to one issuer. It is not a
general-purpose financial chatbot, and the architecture makes that a structural property rather
than a policy request.

## Entry points

From a node in an accepted parsed artifact, from a filing, or from a selected timeframe. The user
may supply an initial question or leave it blank, in which case a generic forensic analysis runs
(`docs/deep-analysis/default-analysis.yaml`).

## Scopes

> **Corrected in Sprint 4.1 (ADR-0016), narrowed again on 2026-08-03 (ADR-0017).** `FILING` scope
> once read "every canonical footnote, financial facts, derived metrics, amendment patches, and
> relevant filing sections". That is a footnote corpus with an appendix, and it would have refused
> to answer what management said about liquidity, which risks it identified, or who signed the
> filing. `FILING` is now **everything the accepted parse produced for that accession, plus the
> preserved original source underneath it** — expressed in the parse's own node identities, not in
> a taxonomy the backend imposes.

---

# CURRENT DIRECTION — AUTHORITATIVE

**NOT IMPLEMENTED. NO SESSION HAS EVER BEEN CREATED AND NO MODEL HAS BEEN INVOKED.** The sections
that follow were written against the withdrawn design; they were corrected in place on 2026-08-03
rather than left as a historical appendix, so the whole file now reads as one specification.

## Scope

A Deep Dive session is bound to **one entity and one timeframe**, fixed at creation and immutable
for the life of the session. Scope is loaded server-side from the session record; the client sends
a session id and a message and nothing else, so a tampered request cannot widen it.

It is a deliberate, scoped, metered, auditable feature. **It is not a general-purpose financial
chatbot.**

## The model

The **analysis/chat model, selected independently by the user** — not inherited from the parsing
model, the summary model or the image model.

**The analysis/chat model is OPTIONAL.** Only the parsing model is required. A run with no analysis
model selected is a complete, valid run; Deep Analysis is simply unavailable for it, which the UI
states rather than silently substituting another role's model.

**A summary is not a prerequisite.** Deep Analysis works with or without one. When no summary
artifact exists the session retrieves the accepted parse and the original source directly, and it
says that no summary index was available rather than degrading quietly.

## What it may retrieve

Everything the job produced for the authorized scope, and the source underneath it:

```
original preserved source        the accepted parsed artifact
image-analysis artifacts         summary artifacts, WHEN ONE EXISTS
```

**It may always return to the original evidence.** A summary is never the sole evidence for a
material claim — that restriction exists because a summary is a derived product and derived
products can be wrong. Numeric evidence comes from the accepted parse and is proved against the
preserved source bytes; there is no local fact lake, and there has not been one since ADR-0017.

## What is recorded on every turn

Source references, cost, tokens, latency, model id, prompt version, and lineage. Every turn is
checked against turn, token and cost budgets **before** invocation. Every turn also carries the
visible parent run ID of the run whose artifacts it is reasoning over, so a transcript can be
traced back to the exact parse and model selections that produced it.

A session is bound to the exact artifact versions it was created over and records their approval
status, so a later approval, rejection or supersession cannot silently change what a completed
transcript rested on.

## No rigid footnote-only scope

The earlier design scoped Deep Analysis to footnotes. That is withdrawn along with the rest of the
footnote-only product. Footnotes remain **independently retrievable wherever the accepted parse
recognized them**, which is a convenience, not a boundary.

## Browsing costs nothing

Reading a completed session, an existing summary, a parse or a source document invokes no model.

## The scope types

There are exactly three. There is no scope keyed to a semantic category, because the backend has no
semantic categories to key one to.

| Scope | Authorized data |
|---|---|
| `NODE` | One node of one accepted parsed artifact and every node beneath it, plus the source ranges those nodes cite and any image artifact linked to them |
| `FILING` | One accession, **complete** — see below |
| `TIMEFRAME` | One CIK, a fixed accession list, and a fixed date range |

A `NODE` scope is named by the parse's own node id. Whether that node is a footnote, an Item, a
statement or something the filing calls nothing at all is the parse's business, not the scope
model's — which is why one scope type replaced the four that named categories the backend used to
decide.

### What `FILING` scope authorizes

```
every node of the accepted parsed artifact for that accession, individually
the preserved original source bytes those nodes cite
image-analysis artifacts for that accession
summary artifacts for that accession, when a summary model was run
```

**What it does not authorize is unchanged**: any other issuer, any other filing, and any referenced
document that has not been acquired and parsed. A dependency the parse recorded but the corpus does
not contain stays visible to the session as a *recorded dependency* — the session can say "the
parse reports this disclosure is made in a separate proxy statement, which this corpus does not
contain" — and never as silence.

## Scope locking, unchanged

Widening the scope vocabulary does not loosen the lock. All of the following remain exactly as
before:

```
scope is computed server-side and is immutable after creation
the client sends only a session identifier and a message
issuer, filing, model, and budgets are loaded from the session record on every turn
a cross-issuer request is refused deterministically, before retrieval, at zero cost
every retrieval is audited
every material claim carries a citation to original evidence
```

A narrower scope is a narrower authorization, never a different security model.

## Session lifecycle

```
CREATED -> ACTIVE -> (IDLE) -> EXPIRED
                  -> BUDGET_EXHAUSTED
                  -> CLOSED           user closed it
                  -> TERMINATED       operator action
```

A session is created server-side. Scope is fixed at creation and immutable thereafter. Sessions
expire after a configured idle period and a configured absolute lifetime. An expired session is
restorable as a read-only transcript; continuing the conversation requires a new session, which
re-derives scope from current data.

## What the client sends

```
session_id
message
```

Nothing else is trusted. CIK, tickers, accessions, node identifiers, scope type, model identifier,
and budgets are loaded from the session record on every turn.

## Budgets

Per session: maximum turns, maximum total input tokens, maximum total output tokens, maximum cost.
Per user: daily cost, concurrent sessions, sessions created per hour. Checked **before**
invocation. Exhaustion ends the session with a clear message rather than silently degrading.

## User-visible behaviour

A scope badge shows the issuer and period the session is locked to.

An out-of-scope request is refused in one sentence, states what can be done within scope, and
costs nothing when the deterministic detector catches it.

Every material claim carries a citation that links to the original SEC source.

Analyses that reasoned over selected evidence rather than the full corpus say so.

Suggested follow-ups are answerable within the existing scope.

No personalized investment advice, no buy, sell, or hold recommendations, no price predictions.

## Evidence discipline

```
A summary, when one exists, is the index. Original filing content is always the evidence.
```

### The retrieval hierarchy

Retrieval descends this ladder and **must reach original evidence before any material claim**:

| Rung | What it is for | May it alone support a material claim |
|---|---|---|
| Filing-level summary, when one exists | Locating which region of the filing is relevant | no |
| Node-level summary, when one exists | Locating which node within it | no |
| Chunk-level summary, when one exists | Locating which passage of an oversized node | no |
| **Preserved original source ranges** | The disclosure itself, as filed | **yes** |
| **Parsed nodes and tables the parse produced** | Text and structured figures, each citing a source range | **yes** |
| Image-analysis artifacts | What a filed graphic shows, linked to its source object | only with the source object it describes |
| Adjacent parse context | Disambiguating a cross-reference | no |
| Recorded dependencies on unacquired documents | Stating what is disclosed elsewhere | only as a statement about coverage |

**A summary is never the sole evidence for a material claim.** That rule predates ADR-0016 and is
unchanged. Two things changed around it: summaries may exist at several levels and every one of
them sits on the non-evidentiary side of the line, and **a summary may not exist at all**, because
the summary model is optional. Neither case relaxes the rule — the absence of a summary removes an
index, never a requirement.

A parsed node is evidence only insofar as it cites a source range that resolves in the preserved
bytes. A node with no resolvable source reference is treated as an unproved claim, because the
parse is a model product and the backend proves it rather than trusting it.

An answer that reasoned over selected evidence rather than the full authorized corpus says so.

### Questions a filing-scoped session must be able to answer

These are the acceptance shape for Phase 7, and each one is unanswerable from a footnote corpus.
They are questions a user asks, not categories the backend recognizes — each is answered from
whatever the accepted parse produced and the source ranges it cites:

```
What risks did management identify?          What changed in MD&A?
What legal matters were disclosed?           What control weaknesses were reported?
What commitments appear in the footnotes?    Who signed the filing?
What certifications were filed?              Which exhibits materially affect the filing?
Where does management discuss liquidity?     What content is incorporated by reference?
```

## All-history analysis

A ten-year or all-history session does not inject every filing into one prompt. It uses
deterministic trend detection, changed-disclosure detection, materiality indicators, anomaly
selection, representative period sampling, and hierarchical synthesis, then retrieves targeted
original evidence for what it found. The response discloses that it reasoned over selected
evidence.

Every one of those techniques is **selection**, never interpretation. They operate on values and
text the accepted parse already produced and choose what to look at more closely. None of them
decides what a passage means, and none is a licence for the backend to re-derive the semantics the
parsing model owns.
