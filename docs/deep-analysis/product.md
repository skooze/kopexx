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
> **NO MODEL HAS BEEN INVOKED AND AWS IS NOT CONFIGURED.** Authoritative:
> `docs/adr/ADR-0016-corpus-first-model-first-architecture.md` and `roadmap.md`.

IMPLEMENTATION STATUS: PLANNED (Sprint 7; FILING scope only, remaining scopes Stage 2 W-6)
OWNER PACKAGE: `packages/deep_analysis`
DECISION RECORDS: ADR-0012 (session scope), ADR-0013 (content boundary)

## What it is

A deliberate, scoped, metered, auditable analytical session bound to one issuer. It is not a
general-purpose financial chatbot, and the architecture makes that a structural property rather
than a policy request.

## Entry points

From a content unit, a footnote, a Part, an Item, a filing, or a selected timeframe. The user may
supply an initial question or leave it blank, in which case a generic forensic analysis runs
(`docs/deep-analysis/default-analysis.yaml`).

## Scopes

> **Corrected in Sprint 4.1 (ADR-0016).** `FILING` scope previously read "every canonical
> footnote, financial facts, derived metrics, amendment patches, and relevant filing sections".
> That is a footnote corpus with an appendix, and it would have refused to answer what management
> said about liquidity, which risks it identified, or who signed the filing. `FILING` is now the
> **complete processed filing corpus**.

---

# CURRENT DIRECTION — AUTHORITATIVE. Everything below this section is historical.

**NOT IMPLEMENTED. NO SESSION HAS EVER BEEN CREATED AND NO MODEL HAS BEEN INVOKED.**

## Scope

A Deep Dive session is bound to **one entity and one timeframe**, fixed at creation and immutable
for the life of the session. Scope is loaded server-side from the session record; the client sends
a session id and a message and nothing else, so a tampered request cannot widen it.

It is a deliberate, scoped, metered, auditable feature. **It is not a general-purpose financial
chatbot.**

## The model

The **analysis/chat model, selected independently by the user** — not inherited from the parsing
model, the summary model or the image model.

## What it may retrieve

Everything the job produced, and the source underneath it:

```
original preserved source        accepted parsed artifacts
summary artifacts                image-analysis artifacts
numeric evidence (XBRL/DERA)
```

**It may always return to the original evidence.** A summary is never the sole evidence for a
material claim — that restriction exists because a summary is a derived product and derived
products can be wrong.

## What is recorded on every turn

Source references, cost, tokens, latency, model id, prompt version, and lineage. Every turn is
checked against turn, token and cost budgets **before** invocation.

## No rigid footnote-only scope

The earlier design scoped Deep Analysis to footnotes. That is withdrawn along with the rest of the
footnote-only product. Footnotes remain **independently retrievable wherever the accepted parse
recognized them**, which is a convenience, not a boundary.

## Browsing costs nothing

Reading a completed session, an existing summary, a parse or a source document invokes no model.


| Scope | Authorized data |
|---|---|
| `CONTENT_UNIT` | One canonical content unit — a section, subsection, statement, exhibit, certification, or other unit — its source blocks, tables, and approved child units |
| `FOOTNOTE` | One canonical footnote, its source blocks and tables, related facts and metrics, and the comparable prior-period footnote when explicitly included |
| `PART` | One Part of one filing and every unit beneath it |
| `ITEM` | One Item and every unit beneath it |
| `FILING` | One accession, **complete** — see below |
| `TIMEFRAME` | One CIK, a fixed accession list, and a fixed date range |

### What `FILING` scope authorizes

```
cover page                        every Part and every Item
narrative sections                financial statements
every financial-statement footnote, individually
tables                            filed XBRL facts and derived metrics
filed exhibits                    certifications
signatures and signer metadata    financial schedules
incorporated-reference records    processed referenced disclosure content
amendment patches                 original source evidence for all of the above
```

**What it does not authorize is unchanged**: any other issuer, any other filing, and any
incorporated document that has not been acquired and processed. An unresolved incorporation is
visible to the session as a *recorded dependency* — the session can say "Item 11 is disclosed in
the 2026 proxy statement, which this corpus does not contain" — and never as silence.

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

Nothing else is trusted. CIK, tickers, accessions, footnote identifiers, scope type, model
identifier, and budgets are loaded from the session record on every turn.

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
Summaries are the index. Original filing content is the evidence.
```

### The retrieval hierarchy

Retrieval descends this ladder and **must reach original evidence before any material claim**:

| Rung | What it is for | May it alone support a material claim |
|---|---|---|
| Filing aggregate summary | Locating which Part or Item is relevant | no |
| Content-unit summary | Locating which unit within it | no |
| Child-chunk summary | Locating which passage of an oversized unit | no |
| **Original source blocks** | The disclosure itself | **yes** |
| **Tables** | Structured figures with unit, scale and period | **yes** |
| **Filed XBRL facts** | Authoritative numeric values | **yes** |
| Adjacent hierarchy context | Disambiguating a cross-reference | no |
| Incorporated-reference records | Stating what is disclosed elsewhere | only as a statement about coverage |

**A summary is never the sole evidence for a material claim.** That rule predates this sprint and
is unchanged; what changed is that there are now summaries at several levels, and every one of
them sits on the non-evidentiary side of the line.

An answer that reasoned over selected evidence rather than the full authorized corpus says so.

### Questions a filing-scoped session must be able to answer

These are the acceptance shape for Sprint 7, and each one is unanswerable from a footnote corpus:

```
What risks did management identify?          What changed in MD&A?
What legal matters were disclosed?           What control weaknesses were reported?
What commitments appear in the footnotes?    Who signed the filing?
What certifications were filed?              Which exhibits materially affect the filing?
Where does management discuss liquidity?     What content is incorporated by reference?
```

## All-history analysis

A ten-year or all-history session does not inject every filing into one prompt. It uses
deterministic trend detection, changed-note detection, materiality indicators, anomaly selection,
representative period sampling, and hierarchical synthesis, then retrieves targeted original
evidence for what it found. The response discloses that it reasoned over selected evidence.
