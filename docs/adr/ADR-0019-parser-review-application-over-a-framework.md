# ADR-0019 — The parser-review application, and the six decisions it forced

STATUS: ACCEPTED
DATE: 2026-08-03
PHASE: 2
SUPERSEDES: nothing
BUILDS ON: [ADR-0016](ADR-0016-corpus-first-model-first-architecture.md),
[ADR-0017](ADR-0017-delete-the-rejected-parser-and-application-persistence.md),
[ADR-0018](ADR-0018-verified-capability-snapshot-over-a-provider-adapter.md)

---

## Context

Phase 1 proved five models were reachable. Phase 2 had to find out whether any of them can read a
filing — and roadmap.md 2b says why that cannot be done from a terminal: **a parsed artifact cannot
be evaluated without looking at it beside the filing it came from.** So the first model experiments
and the first review surface had to be built together.

That forced six decisions that were not obvious in advance. Each is recorded here once.

---

## 1. The review application uses the standard library, not a web framework

**Decision.** `packages/review_api` serves the review UI on `http.server.ThreadingHTTPServer` with
a small router. Pages are rendered in Python. The stylesheet and the single script are module
constants served from their own routes. **No web framework, no ASGI server, no bundler, no npm, and
no new runtime dependency of any kind.**

**Why.** rules.md prohibits introducing a large framework without need. The need here is about
twenty routes, two static assets and one event stream, served to one developer on loopback.
A framework plus a server would have been three dependencies, a supply-chain surface and a
`pip-audit` obligation, bought for routing. The whole runtime dependency list is still
`ruamel.yaml` and `httpx`; the AWS SDK is an OPTIONAL extra, which is what now makes the phrase
"ordinary CI is AWS-free" mean the SDK is not even installed.

**Consequence.** Every handler is a function from a request to a response, so the entire API is
exercised in the test suite with no socket, no port and no timeout — which is what keeps the
zero-skip gate honest. The cost is that this server is not a production server, and it is not
claimed to be one: it binds to loopback and labels itself local development mode.

**Revisit when.** The beta UI in Phase 6 has real users, real concurrency or TLS. Nothing about
this decision constrains that one; it constrains the tool that made the first experiments possible.

## 2. A filing is rendered as escaped text, never as markup

**Decision.** The raw view shows the preserved bytes escaped inside a preformatted block. There is
no sanitizer and no sandboxed iframe.

**Why.** A filing is the authoritative source of everything this product says AND untrusted input
from the open internet. A sanitizer is a thing to get wrong; an iframe is a thing to configure
wrong. Escaping is neither. It also lets the content security policy be `default-src 'none'` with
no `unsafe-inline`, which is only possible because nothing from a filing ever reaches a markup
parser and because the stylesheet and script have their own routes.

**Consequence.** The raw view shows a filing as it was filed — tags and all — which for reviewing a
parse is better than a rendering, because the question being asked is what the MODEL saw.

## 3. Source references are verbatim quotes, not byte offsets

**Decision.** The parser prompt asks for a short verbatim quote per reference. The backend resolves
each one against the preserved bytes and records HOW it resolved: exactly, after whitespace
normalisation, after markup removal, ambiguously, or not at all.

**Why.** A model handed an artifact as text cannot count bytes in it. A fabricated offset resolves
to the wrong place while looking exactly like a real one; a fabricated quote does not occur. Three
searches rather than one because filings wrap prose across lines with arbitrary indentation and
inline XBRL interleaves markup inside a sentence — a model that reflowed a sentence it copied
correctly should not be recorded as having invented it.

**This is a search strategy over preserved bytes, not a projection of the input.** Nothing about
what is SENT changed; visible-content projection remains an unapproved research option.

## 4. Evaluation storage is a directory, and it is not the product database

**Decision.** `packages/evaluation_store` writes parent runs, child jobs, exact request and
response evidence, an append-only event log, comments and two independent state machines to an
ignored local directory through `packages/storage`.

**Why.** Review work has to survive a page reload. rules.md invariant 15 says persistence follows
measured model output, and a 24-table schema designed before a model had ever parsed a filing is
exactly what ADR-0017 deleted. So this holds no schema, no relational model, no index and no
representation of what a filing contains: a source set, a validation result and an image-coverage
report all arrive as opaque mappings written by the packages that own those concepts.

**Approval exists here; reuse does not.** A reviewer can mark an artifact APPROVED and that records
a judgement and nothing else. No search consults it, no cache is populated. Phase 4 designs that
gate, from artifacts that will by then exist.

## 5. Region routing is derived from the reviewed snapshot, and is always disclosed

**Decision.** A model runs in the preferred region when the snapshot verified it there, and
otherwise in the FIRST region the snapshot verified — with `in_preferred_region: false` and a
sentence naming both regions carried into the run plan, the child job, the request, the response,
the cost record and the artifact lineage.

**Why.** One approved candidate is not offered in the project's preferred region at all. The
product is explicitly allowed to run different models in different regions; it is not allowed to do
so quietly, because cross-region inference moves request content between regions and that is a
data-residency decision rather than a throughput one.

**No region literal exists in shipped source.** `verified_regions` became an ordered tuple rather
than a set for this: a set would make the choice depend on hash ordering, which is a different
region on a different interpreter run — an unreproducible bill.

## 6. A rejected response is evidence, not an exception

**Decision.** `LlmGateway.invoke` gained `strict_response=False`. In that mode a response that
fails the boundary check is RECORDED with its exact bytes and returned with no parsed value,
instead of raising.

**Why.** That response was bought and cannot be regenerated for free, and whether the prompt or the
model is at fault is exactly what a reviewer is there to decide. The response is still refused — it
is refused visibly rather than thrown away. `strict_response=True` remains the default and remains
the behaviour everywhere else.

The same reasoning made `ValidationStatus` deliberately omit a `COMPLETE` member, and made
`VALIDATING` unable to reach `FAILED` on a validation verdict.

---

## What this ADR does NOT decide

```
the final parsed-artifact contract      it stays provisional and is DERIVED from what models return
the persistence schema                  Phase 4, from measured artifacts
Redis or any cache                      not implemented, not designed
the production UI                       Phase 6
which parser advances to breadth        the user's decision, from the evidence Phase 2 produced
```

## Consequences to live with

1. **The token estimate is still a character ratio.** R-24 stays open. Phase 2 records the estimate
   beside the measured usage on every invocation, so the size of the gap is now data rather than a
   guess.
2. **Image input tokens are unverified.** Bedrock bills images as input tokens and publishes no
   conversion. A deliberately generous constant is charged in the pre-spend bound and is LABELLED
   unverified; the measured figure arrives with the first multimodal invocation.
3. **The `IDEA:` renderer marker is a dated EDGAR observation**, not a permanent constant. It is
   how SEC's own renderer output is told apart from the filer's documents inside one dissemination
   envelope, it is recorded with the accession it was measured on, and every disposition it
   produces appears in the run plan rather than being applied silently.
4. **A hand-written HTTP server is a security surface.** It is bound to loopback by default, it
   refuses to bind further without an authentication secret, and it bounds request size — but it is
   a development tool and is labelled as one.
