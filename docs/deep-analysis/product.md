# Deep Analysis Product

IMPLEMENTATION STATUS: PLANNED (Sprint 7; FILING scope only, remaining scopes Stage 2 W-6)
OWNER PACKAGE: `packages/deep_analysis`
DECISION RECORDS: ADR-0012 (session scope), ADR-0013 (content boundary)

## What it is

A deliberate, scoped, metered, auditable analytical session bound to one issuer. It is not a
general-purpose financial chatbot, and the architecture makes that a structural property rather
than a policy request.

## Entry points

From a footnote, a filing, or a selected timeframe. The user may supply an initial question or
leave it blank, in which case a generic forensic analysis runs
(`docs/deep-analysis/default-analysis.yaml`).

## Scopes

| Scope | Authorized data |
|---|---|
| `FOOTNOTE` | One canonical footnote, its source blocks and tables, related facts and metrics, and the comparable prior-period footnote when explicitly included |
| `FILING` | One accession: every canonical footnote, financial facts, derived metrics, amendment patches, and relevant filing sections |
| `TIMEFRAME` | One CIK, a fixed accession list, and a fixed date range |

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

The model uses stored summaries to locate relevant material, then retrieves original footnote
text, tables, and filed facts before drawing a material conclusion.

## All-history analysis

A ten-year or all-history session does not inject every filing into one prompt. It uses
deterministic trend detection, changed-note detection, materiality indicators, anomaly selection,
representative period sampling, and hierarchical synthesis, then retrieves targeted original
evidence for what it found. The response discloses that it reasoned over selected evidence.
