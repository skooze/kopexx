# ADR-0015: Prove one vertical thread before widening any layer

STATUS: ACCEPTED
DATE: 2026-08-01
SPRINT: Sprint 2 alignment review
SUPERSEDES: the phase ordering in the original `roadmap.md` (Phases 1 through 10)

## Context

A product-alignment review of the repository after Sprint 2 compared the fifteen core product
requirements against what the documents actually schedule. The content was aligned: every
requirement appeared, and the canonical-footnote correction had propagated correctly.

The sequencing was not. The roadmap contained a genuine vertical slice as Phase 1, targeted at
sprints 3 to 5, whose deliverables included "one summary per canonical footnote", "one financial
chart", "all note summaries rendered", "one Deep Analysis session", and "rejection of a
cross-ticker request". Its stated dependency was Phase 0 alone.

But `techspecs.md` scheduled summarization at Phase 6 (sprints 18–21), metrics at Phase 3
(8–10), the API at Phase 7 (22–24), the dashboard at Phase 8 (25–28), and Deep Analysis at
Phase 9 (29–33). Phase 1 could not deliver at sprints 3 to 5 what Phases 3 through 9 build at
sprints 8 through 33.

The sprint breakdown resolved the contradiction silently, by ending at Sprint 5 with
"summarization of every canonical footnote for one filing" and dropping the dashboard and Deep
Analysis deliverables. The vertical slice was therefore described in the roadmap and scheduled
nowhere.

Three consequences followed. Requirement 9, the zero-LLM read path, had no test site until
sprint 22. Requirements 10 through 14, the scope lock and cost containment, were unproven until
roughly sprint 30. And the unit economics of the entire product — the parameter that decides
whether it is viable at all — sat behind a 120-fixture benchmark scheduled for sprint 18 to 21,
with every parameter in `docs/llm/cost-model.md` still a placeholder.

At roughly two weeks per sprint, that is fourteen to sixteen months before learning whether the
core thesis works or what it costs.

## Decision

Deliver in two stages.

**Stage 1, Sprints 3 to 7: one complete vertical thread.** One issuer, Apple, taken through
every layer of the product — acquisition, preservation, fact extraction, canonicalization,
real-model summarization, storage, dashboard, zero-LLM read proof, and filing-scoped Deep
Analysis with cost containment. Every dependency the thread needs is scheduled inside Stage 1.
All fifteen MVP criteria are satisfied at the end of Sprint 7.

**Stage 2, Sprint 8 onward: widening.** Issuer universe, all-time acquisition, canonicalization
fallback stages, the full benchmark corpus, full-corpus backfill, remaining analysis scopes,
deployment, and pre-XBRL numerics. Nothing in Stage 2 is required for the MVP.

Three specific things move earlier as a result:

- **Provider catalog verification, model selection, and cost measurement move from Phase 6 to
  Sprint 5.** This is the go/no-go for the project's economics and it is answered in month two
  rather than month ten.
- **The zero-LLM dashboard test lands in the same sprint as the first read endpoint**, Sprint 6,
  rather than existing as an untested invariant for twenty sprints.
- **The scope-lock and cross-ticker refusal tests land in Sprint 7**, not sprint 30.

Three things are deliberately deferred and scoped down:

- Canonicalization stages 6 through 11 are fallbacks for a failure mode that measured 0 of 46 on
  the verified filing. Stage 1 implements stages 1 to 5 only.
- The benchmark splits into a 15-footnote tier-1 smoke gate in Sprint 5 and the full 120-fixture
  tier-2 program before backfill. A tier-1 pass is provisional and does not select a production
  model.
- Deep Analysis ships `FILING` scope only in Stage 1. That scope is sufficient to prove the
  security model; `FOOTNOTE` and `TIMEFRAME` follow in Stage 2.

## Alternatives Considered

**Keep the layered order and accept the timeline.** Rejected: it is a well-formed construction
plan and a poorly formed learning plan. It builds breadth against a thesis that has not been
validated once, and it defers the cost question past the point where the answer could still
change the design.

**Build the slice but keep the full benchmark as its gate.** Rejected: the 120-fixture corpus
with two annotators and three-way splits must be built in full before a single footnote is
summarized. It is the right gate before spending real money at corpus scale and the wrong gate
before proving the pipeline works at all.

**Prove the slice on a synthetic or fixture-only issuer.** Rejected: the failure modes that
matter — filer-specific role URI conventions, real numeric fidelity, real token counts, real
prices — only appear against real filed documents.

**Skip the dashboard in Stage 1 and prove the zero-LLM property by inspection.** Rejected: the
requirement is stated as "proven by test" in the MVP definition. An invariant with no executable
test is a comment.

## Consequences

Breadth arrives later. The issuer registry, all-time backfill, and 25-issuer breadth validation
that were scheduled for sprints 6 through 17 now begin after Sprint 7. Risk R-02, single-filing
grouping validation, stays open longer, which is acceptable because Stage 1 is explicitly one
issuer and the roadmap records that the 100 percent attachment result is not a general guarantee.

In exchange, every high-severity unknown is resolved by Sprint 7 instead of sprint 30, and a
negative result on unit economics arrives while the architecture can still respond to it.

The empty package stubs created in Sprint 1 for Stage 2 work are removed, because they reserved
names twenty sprints ahead of their code and made two architecture tests pass while enforcing
nothing. Packages are created when their code arrives; reserved names live in `techspecs.md`
section 2, which carries a status column.

## Migration Impact

None to data. `roadmap.md` is rewritten, `techspecs.md` phase references are updated, and
ADR-0008 and ADR-0009 move to PROVISIONAL because their implementation phase is now in Stage 2.

## Revisit Conditions

Revisit the Stage 2 ordering after Sprint 7, when measured cost from Sprint 5 will change what is
affordable. Revisit this decision entirely if Sprint 5 returns a negative go/no-go on unit
economics, because that outcome changes the product, not just the schedule.
