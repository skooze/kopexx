# System Context

IMPLEMENTATION STATUS: acquisition, preservation and the LLM boundary are IMPLEMENTED; the
persistent store and the cache are PLANNED; the orchestrator and the review API are IMPLEMENTED as of Phase 2. See `techspecs.md` for
per-component status.

> **NO MODEL HAS BEEN INVOKED, AWS IS NOT CONFIGURED, AND NO APPLICATION DATABASE EXISTS.** The
> control-plane schema, the fact lake and the versioned serving datasets this document used to
> describe were deleted with the deterministic parser they served (ADR-0017). Persistence is
> designed from measured artifacts in Phase 4, not before them, so this document names the ROLE a
> store plays and not the product that will play it.
>
> **SUPERSEDED 2026-08-03 BY PHASE 2, ADDITIVELY.** The statement above was true when it was
> written and is kept for that reason (`rules.md` section 21 rule 16). It is no longer true:
> AWS IS configured, a real Bedrock adapter EXISTS in `packages/llm_gateway/providers/bedrock.py`,
> and SEC filings HAVE been sent to real models — three preserved filings across five candidates
> under two prompt versions. See `docs/sprints/PHASE-0002-parser-experiments-and-review-ui.md`.
>
> **WHAT IS STILL TRUE.** No application database exists. No Redis exists. No summary artifact, no
> image artifact and no chat session exists — Phase 2 ran the PARSING stage only, and the
> orchestrator raises rather than running another. Nothing is deployed.

## External systems

| System | Direction | What crosses | Trust |
|---|---|---|---|
| `www.sec.gov` | read | Filing documents, archives, quarterly indexes | Content untrusted |
| `data.sec.gov` | read | Submissions metadata | Content untrusted |
| `efts.sec.gov` | read | Full-text search | Untrusted; separate rate bucket |
| Model provider | write then read | Model-visible content and responses | Response untrusted |
| Browser | read and write | API requests and responses | Fully untrusted |

Kopexx writes nothing back to SEC. The only outbound side effect is a metered model invocation.

## Planes

```
INGESTION      discovery, acquisition, byte-exact preservation          outbound to SEC
ORCHESTRATION  runs, child filing jobs, stage sequencing, progress
LLM            parsing, and the optional image, summary and chat stages
VALIDATION     coverage, citation and numeric proof against preserved bytes
REVIEW         evaluation artifacts, approval, developer comments
SERVING        API and dashboard, reads stored artifacts only
```

**The serving plane never calls the LLM plane.** That separation is what makes a provider outage
invisible to a completed result, and it is the same property as "ordinary dashboard access never
invokes a language model".

**The validation plane never calls a model either.** Proof runs in backend code against the
preserved bytes. It is the one place where the backend is allowed to disagree with the parsing
model, and it does so on byte evidence rather than on a second interpretation.

## Failure domains

| Domain | Blast radius |
|---|---|
| SEC unavailable | Acquisition pauses; anything already preserved still processes; serving unaffected |
| Model provider unavailable | New runs cannot parse; approved artifacts still serve; dashboard unaffected |
| Persistent artifact store unavailable | Approval and reuse degraded; evaluation runs cannot record results |
| Object storage unavailable | Acquisition and raw retrieval fail; nothing new can be preserved |
| Redis unavailable | Cache misses only. The 24-hour cache is never authoritative, so nothing is lost |
| Preserved source corrupted or hash-invalid | That filing is re-fetched from SEC; a valid original is never silently overwritten |

The persistent artifact store will be the single point of failure once it exists. **It does not
exist yet**, and naming its technology before there are artifacts to shape it is the mistake
ADR-0017 unwound.

## Scaling boundaries

| Component | Scales by | Hard limit |
|---|---|---|
| Acquisition workers | Queue depth | **SEC rate limit, aggregate across all machines** |
| Parsing | Filings in the run | Provider quota, context limits, and the authorized cost ceiling |
| Optional stages | Selected stages only | Same, and zero when the selector is blank |
| API | Request rate | Store connections |
| Serving reads | Horizontal, freely | None; readers share no lock |

Adding acquisition workers past the rate limit adds nothing. That limit is the binding constraint on
backfill duration and no amount of parallelism moves it.

**Parsing does not scale on CPU.** It is one model invocation per filing carrying the intact source
set, so its constraints are the provider's — quota, context window, price — and a filing that
exceeds the selected model's limit is refused, never split.
