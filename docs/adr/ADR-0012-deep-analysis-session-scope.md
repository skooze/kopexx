# ADR-0012: Deep Analysis scope is immutable and enforced server-side

STATUS: ACCEPTED
DATE: 2026-08-01
SPRINT: 1

## Context

Deep Analysis invokes a strong model over retrieved evidence. Two risks follow. A user in one
issuer's session could drive cost by asking about unrelated companies. Filing text is untrusted
input that may contain instructions attempting to redirect the model.

## Decision

A Deep Analysis session is created server-side and its scope is immutable for the session's
lifetime. Scope comprises the issuer CIK, an explicit allowlist of accession numbers, an optional
allowlist of footnote identifiers, and a date range.

The client sends only a session identifier and a message. CIK, tickers, accessions, footnote
identifiers, scope type, model identifier, and budgets are never accepted from the request body.

Every retrieval tool re-derives the allowlist from the session record on the server, per call. It
does not trust its arguments. A request for content outside the allowlist is a logged scope
violation.

Native tool calling is prohibited per ADR-0013, so retrieval is application-orchestrated or uses a
bounded YAML action protocol in which any scope the model proposes is ignored.

Filing content is delivered to the model as labeled source data with an explicit instruction that
instructions found inside it are to be ignored and reported.

## Alternatives Considered

Trust client-supplied scope. Rejected: it is the primary attack.

Rely on prompt instructions alone. Rejected: a prompt is a request, not a control.

Allow unrestricted retrieval with post-hoc filtering. Rejected: cost is incurred at retrieval and
invocation, so filtering afterwards does not prevent the abuse.

## Consequences

Cross-issuer comparison is impossible within one session by design; comparing issuers requires a
product decision about a distinct session type. Every tool call carries a scope lookup. Scope
rejections are auditable and can be alerted on.

## Migration Impact

Adding a legitimate multi-issuer session type later means a new scope type with its own allowlist
semantics, not a relaxation of enforcement.

## Revisit Conditions

Revisit when a genuine multi-issuer product requirement exists, at which point a new scope type is
added rather than the enforcement weakened.
