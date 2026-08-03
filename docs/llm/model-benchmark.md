# Summarization Model Benchmark

> **RE-FOUNDED 2026-08-02 ON MEASURED EVIDENCE.** A representative corpus of **112 SEC issuers and
> 613 filings across six transport eras** was acquired and measured — dated Phase 0 evidence, not a
> permanent constant — and it refuted the assumptions the deterministic semantic parser rested on.
> The product is an orchestrator-driven, model-first SEC filing product: the backend acquires,
> preserves, transports, orchestrates and VALIDATES; a user-selected parsing model determines what
> a filing means. The user selects four models independently — parsing, image, summary, and
> analysis/chat — and **only the parsing model is required**. The current authorized input mode is
> `INTACT_SOURCE_ONLY`. Sections below that describe the withdrawn design are historical.
>
> **UPDATED 2026-08-03.** The deterministic content ontology and the local application database are
> no longer merely withdrawn — the parser, the persistence layer and the migrations are DELETED, and
> no application database exists. **Grading a parsing model against a deterministic parse is now
> prohibited** (`rules.md` section 21 rule 15).
>
> **UPDATED 2026-08-03 BY PHASE 1.** AWS identity is verified and all five candidates have been
> reached. That is REACHABILITY, not a benchmark: seven one-word invocations proved transport,
> authorization and request format, and measured nothing about quality. **NO BENCHMARK HAS BEEN
> RUN.** The verified identifiers, regions, modalities, limits and prices are in
> `bedrock-capability-snapshot.yaml` and are not repeated here.
>
> **NO SEC FILING HAS BEEN SENT TO ANY MODEL.** Authoritative:
> `docs/adr/ADR-0016-corpus-first-model-first-architecture.md`,
> `docs/adr/ADR-0017-delete-the-rejected-parser-and-application-persistence.md` and `roadmap.md`.

---

# CURRENT DIRECTION — AUTHORITATIVE. Everything below this section is historical.

**NO BENCHMARK HAS BEEN RUN. NO MODEL HAS BEEN INVOKED. NO RESULT IS CLAIMED.**

This document describes what will be measured in Phase 2. It reports nothing, because nothing has
been measured. Any number below this line that looks like a result is a worked example or a
placeholder.

## The candidates

GPT OSS 120B, NVIDIA Nemotron 3 Super 120B, Qwen3 235B A22B, Llama 4 Maverick, Qwen3 VL 235B.

**All five were mapped, reached and priced on 2026-08-03.** Model IDs, versions, regions,
modalities, context and output limits, supported request formats and prices were DISCOVERED LIVE
and are recorded in `bedrock-capability-snapshot.yaml`. **No identifier in this repository is
trusted until discovery returns it, and none is hardcoded anywhere.**

Three facts from that discovery shape what Phase 2 can attempt:

```
context windows differ by 8x across the five, 128K to 1M, and output limits by 4x, 8K to 32K
one candidate cannot be invoked by model id at all and requires a cross-region inference profile
one candidate is not offered in the primary region, though its own model card says it is
```

Against dated Phase 0 evidence that 44 percent of primary corpus documents exceed ~200,000
estimated tokens, the context spread is the difference between a model that can take an intact
filing and one that cannot. That is measured now instead of assumed.

## What Phase 2 measures, per role

Benchmarks are per ROLE. A model good at parsing is not thereby the right summary model, and the
user selects each independently anyway.

```
PARSING       whether the provider accepts the intact artifact at all
              source coverage against preserved bytes
              citation fidelity — does every cited offset resolve
              numeric fidelity — does every reported number appear verbatim
              omission detection — what disappeared silently
              input tokens, output tokens, latency, cost
              variability across models, and across reruns of the SAME model
IMAGE         description usefulness, correct linkage to the source object
SUMMARY       grounding in the accepted parse, citation fidelity, cost
ANALYSIS      answer grounding, scope adherence, per-turn cost
```

## The corpus samples Phase 2 must use

Materially different, not five filings from one issuer — that is the mistake this whole correction
exists to undo:

```
historical plain-text or SGML      early HTML                pre-inline-XBRL
modern inline-XBRL                 small-business form       transition form
amendment                          young issuer              mature issuer
image-bearing filing               a large filing compatible with at least one available model
```

## The output contract is provisional

The parser request and response contracts are provisional until real responses reshape them. Raw
text or exactly one unfenced YAML 1.2 document, with the original-source exception for the intact
artifact. **The artifact format follows what the models actually return**, not the reverse.

## There is no oracle, and grading against one is prohibited

An earlier version of this section named the deterministic Apple parse — 43 canonical footnotes,
117 of 117 attachments, the table-ownership census — a **recall floor for grading a parsing model**.
That is withdrawn. The code is deleted and the practice is now forbidden: `rules.md` section 21
rule 15 and ADR-0017 section 3.

Grading a model against a deterministic parse makes the deterministic interpretation authoritative
again through the back door, which is exactly what ADR-0016 withdrew. It also generalizes one
issuer, one filing agent and two of six transport eras onto a corpus of 112 issuers, 75 SIC
industries and six eras — and a benchmark that is wrong about breadth is worse than none, because it
produces a number and a number gets believed.

**A parse is validated against the PRESERVED SOURCE BYTES, never against a second parse.** That
control needs no oracle, and it is stronger, because it does not require another interpretation to
be correct first.


IMPLEMENTATION STATUS: PLANNED — the first measurement is Phase 2
DECISION RECORD: `docs/adr/ADR-0006-model-selection-by-benchmark.md`
GATES: not yet written. The footnote-summary evaluation gates were deleted with the prompt they
       scored; real gates are derived from observed model behaviour.
DEEP ANALYSIS MODEL: `docs/llm/analysis-model-benchmark.md` — separate task, separate gates

## Principle

No model is selected until measured on a representative footnote corpus. The strongest available
model is not automatically right for a bounded, highly structured task; that is an empirical
question about numeric fidelity and instruction following.

Among models passing every gate, the **cheapest** is selected.

---

## Identity and budget preconditions

The benchmark runs under a least-privilege identity holding only the Bedrock actions and model
resources it needs. Broad administrator access to ease model discovery is prohibited; discovery is
a one-time convenience and the permission outlives it.

**DISCLOSED: Phase 1 discovery ran under an IAM Identity Center `AdministratorAccess` role**, the
identity supplied for that task. It was a one-time manual discovery producing a document, not a
running capability, and no CI job holds an AWS role. The requirement above is unchanged and binds
before any repeatable or automated invocation path. ADR-0018 section 7.

Permissions are separated for model discovery, standard-summary invocation, Deep Analysis
invocation, request/response object access, and cost metadata. **Deep Analysis and standard
summarization must be separately measurable and separately restrictable** even while sharing one
account — they have different cost and abuse profiles, and one permission covering both makes each
invisible inside the other.

Every run requires a hard invocation budget, a hard dollar budget, an explicit model allowlist, an
explicit region, a manual start, and no automatic retry that can exceed the budget. The workflow
that runs it is gated and cannot trigger implicitly on a push. A pull request from an untrusted
fork receives no role capable of invoking a billable model.

See `docs/security/aws-identity-and-secrets.md`.

## Two benchmarks, not one

The full corpus below is a serious measurement program: 120 gold-labelled footnotes, two
annotators, three-way splits, Wilson intervals. It is the right gate before spending real money
across ~170,000 filings. It is the **wrong** gate before summarizing a single footnote, because
it must be built in full before the pipeline produces anything at all.

The evaluation is therefore split.

### Tier 1 — Slice smoke benchmark (Sprint 5)

> **Corrected in Sprint 4.1 (ADR-0016).** This corpus was 15 canonical footnotes. That measures
> one content type and would have produced unit economics for roughly a fifth of the real
> summarized surface: Apple's FY2025 10-K has **67 required summary units**, of which 13 are
> footnotes. A cost figure extrapolated from the footnote subset would have been wrong in the same
> direction, and for the same reason, as the withdrawn 58-TextBlock estimate.

```
PURPOSE     Prove the pipeline end to end across the CONTENT TAXONOMY and measure real cost
            per content unit and per filing.
CORPUS      A stratified sample of required summary units from the vertical-slice filings,
            spanning every stratum below. Not fewer than 20 units, and the footnote stratum is
            never fewer than the 2 hard cases named below.
LABELS      Figures, units, scales, periods, and signs extracted from the filed source
            programmatically, then reviewed once by a human. Not full gold labels.
CANDIDATES  At least 2, spanning 2 capability tiers.
```

**Required strata.** Every one must appear; none may be the whole corpus.

```
cover-page metadata            Business (Item 1)
Risk Factors (Item 1A)         MD&A (Item 7)
market risk (Item 7A)          legal proceedings (Item 3)
cybersecurity (Item 1C)        controls and procedures (Item 9A)
a financial statement          a routine one-paragraph footnote
a complex table-heavy footnote a human-readable exhibit
a certification                a signature block
a historical filing section    an oversized unit requiring hierarchical chunking
```

**Footnotes must neither disappear from the benchmark nor constitute it.** They are the hardest
stratum and keep the two deliberately hard cases the original corpus named: the largest note and a
routine one-paragraph note.

Gates for tier 1 — deliberately narrower than production gates, because a smoke corpus cannot
establish a rate to three decimal places:

```
structured_output_validity    == 1.0     every response parses as one YAML 1.2 document
unit_omission_rate            == 0.0     every required unit in the corpus produces a summary
footnote_omission_rate        == 0.0     13 footnotes in, 13 summaries out, independently
chunk_coverage                == 1.0     every leaf chunk of an oversized unit is summarized
aggregate_lineage_validity    == 1.0     every aggregate cites only accepted child summaries
numeric_fidelity              == 1.0     any error on a corpus this size is a real defect
unit_and_scale_fidelity       == 1.0
citation_resolvability        == 1.0     every cited id exists and belongs to that unit or an
                                         approved child
qualitative_source_grounding  == 1.0     every narrative claim traces to a supplied block
boundary_violations           == 0       no prohibited format in either direction
recommendations_or_forecasts  == 0       no advice, no price prediction
```

Tier 1 also **measures and publishes**, replacing the placeholders in `docs/llm/cost-model.md`:
`T_src`, `T_tbl`, `T_out`, `R_retry`, observed `P_in` and `P_out`, and cost per source character,
per input token, per leaf chunk, per content unit, per footnote, per Part, per Item, per filing,
and extrapolated per issuer history.

**Passing tier 1 does not select a production model.** It proves the pipeline works, establishes
real unit economics, and produces the go/no-go the project currently lacks. A tier-1 result is
always reported as provisional.

### Tier 2 — Full pre-backfill benchmark

Everything below. Required before any multi-issuer backfill and before any cost commitment.
Its corpus is built incrementally from Sprint 5 onward rather than in one block, so it is ready
when breadth work begins.

---

## Full corpus construction

Minimum 120 canonical footnotes, stratified across three dimensions simultaneously so that a model
cannot pass by being good at one industry or one era.

Industries: software, industrial, retail, bank, insurer, REIT, utility, biotechnology,
acquisition-heavy.

Content types, stratified independently of footnote type: cover page, Business, Risk Factors,
Legal Proceedings, MD&A, market risk, controls and procedures, cybersecurity, other information,
financial statements, financial schedules, exhibits, certifications, signatures, and incorporated
references.

Footnote types: significant accounting policies, revenue recognition, debt, credit facilities,
derivatives and hedging, fair-value hierarchy, income taxes, valuation allowances, stock-based
compensation, pensions, leases, segment reporting, variable interest entities, noncontrolling
interests, litigation and contingencies, impairments, restructuring, going concern, subsequent
events.

Eras: inline XBRL 2019 onward, standalone XBRL 2009 to 2018, HTML without XBRL 2001 to 2008, plain
text before 2001.

Edge cases: very short routine notes, exceptionally large notes, poorly formatted HTML, amendment
partial content, notes with no tables, notes with many tables.

## Splits

```
development   40 percent   prompt iteration
validation    30 percent   model comparison
held-out      30 percent   final gate; used ONCE per candidate
```

The held-out split is not used during prompt development. A prompt tuned against the gate has
measured nothing.

## Gold labels

Each fixture carries a human-produced reference: the correct financial relationships, the correct
important facts with unit, scale, sign, and period, the correct period changes, and the correct
classification. Produced by one annotator and reviewed by a second, with disagreements resolved
and recorded rather than averaged.

Gold labels are versioned. A label found wrong is corrected and the affected scores recomputed,
never quietly patched.

## Scored dimensions

```
content_unit_coverage            canonical_footnote_coverage  omission_rate
chunk_coverage                   aggregate_lineage_validity   unsupported_claim_rate
numeric_fidelity                 date_fidelity                period_fidelity
unit_fidelity                    scale_fidelity               sign_fidelity
citation_precision               citation_recall              financial_relationship_accuracy
material_change_accuracy         accounting_policy_accuracy   risk_identification_recall
qualitative_source_grounding     structured_output_validity   hallucination_rate
concision                        readability                  latency_p50 / latency_p95
retry_rate                       cost_per_content_unit        cost_per_footnote
cost_per_item                    cost_per_filing              human_review_rate
```

## Production gates

A candidate must pass **every** gate. Failing one disqualifies it regardless of the others.

```
numeric_fidelity              >= 0.995
structured_output_validity    >= 0.99
citation_accuracy             >= 0.95
footnote_omission_rate        == 0.0
unsupported_claim_rate        <= 0.01
unit_fidelity                 == 1.0
sign_fidelity                 == 1.0
scale_fidelity                == 1.0
period_fidelity               >= 0.99
```

Unit, sign, and scale gates are exactly 1.0 because each failure is an order-of-magnitude or
directional error in a financial figure, and there is no acceptable rate for that.

## Statistical confidence

Report Wilson score intervals for every rate. A gate is passed only when the **lower bound** of
the interval clears it, so a small sample cannot pass a model by luck. If the interval is too wide
to decide, the corpus is too small and is extended rather than the gate relaxed.

## Serialization comparison

Historical. The harness that recorded token counts across plain text, YAML, Markdown, JSON and XML
was removed once ADR-0013 was decided; `packages/llm_gateway/token_counter.py` now offers a
character-ratio estimate only. The production path selects plain text or YAML regardless of any such
result, because the boundary is a correctness constraint and never was an optimization.

## Result storage

Results are committed alongside the fixtures: model identifier, region, prompt version, schema
version, corpus version, gold-label version, per-dimension scores with intervals, cost, latency
distribution, and the run timestamp. A result whose inputs are not fully identified is not a
result.

## Promotion and rollback

Promotion requires passing every gate on the held-out split and a cost comparison against the
incumbent. Rollback is activating the previous model identifier in configuration; summaries
produced by the regressed model are superseded, never deleted, because they are the evidence for
the post-mortem.

## Regression cadence

Re-run on every prompt version change, every candidate model addition, and on a schedule to detect
provider-side drift behind a stable model identifier.
