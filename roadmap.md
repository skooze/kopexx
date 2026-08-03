# roadmap.md — Kopexx Delivery Roadmap

STATUS OF THIS DOCUMENT: IMPLEMENTED (accurate as of the 2026-08-02 corpus study)
LAST UPDATED: 2026-08-02 during the architecture and governance realignment, prepared against
published baseline `068eceb`.
ARCHITECTURE DECISION: `docs/adr/ADR-0016-corpus-first-model-first-architecture.md`
SEQUENCING PRINCIPLE: evidence before architecture; architecture before schema.

---

## Product Vision

An investor selects a company, a timeframe, and four models — a parsing model, an image model, a
summary model, and an analysis/chat model. The backend discovers and acquires the filings,
preserves the original SEC artifacts byte-for-byte, and **sends the complete compatible set of
relevant human-readable SEC-filed source documents intact to the selected parsing model**. It
validates what comes back against the preserved bytes, sends the accepted parse to the selected
summary model, and streams the results. Browsing completed results invokes no model.

**The backend orchestrates. It does not attempt to understand a filing semantically before the
model sees it.**

WHAT "THE COMPLETE COMPATIBLE SET" MEANS, AND WHAT IT DOES NOT

```
every original artifact remains BYTE-EXACT
machine artifacts are PRESERVED but are not automatically semantic parser input
duplicate renderings of the same content are NOT submitted redundantly
an unknown transport role FAILS CLOSED for review; it is never guessed at
no semantic slicing, projection, multipart processing, truncation, or automatic model
     substitution is authorized
```

The singular phrasing this replaced read as though only the primary document were sent. It is the
whole relevant human-readable set, or the pairing is incompatible.

---

## Why this roadmap replaced the previous one

The previous roadmap sequenced a deterministic semantic parser, a universal filing ontology and a
PostgreSQL schema ahead of ever calling a model — and validated all of it against five Apple
filings. A representative corpus was then measured. It refuted the design.

```
MEASURED 2026-08-02   112 issuers   613 filings   22 of 22 forms   6 eras   760 MB   0 throttles
                      135 time-eligible quarters scanned (1993Q1-2026Q3); 2026Q4 pre-created, empty

271 of 613  ~44%  of primary documents exceed ~200,000 estimated tokens
169 of 613  ~28%  exceed ~500,000
 71 of 613  ~12%  exceed ~1,000,000   largest: JPMorgan Chase 10-K, 12.9 MB, ~4.3M est tokens
1.28x to 24.11x   raw-to-visible character ratio, by transport format
1.03x median      human-readable source set as a multiple of the primary document (p90 1.34x)
4 to 283          files per filing package
0 to 1,115        table open-tags in a single primary document
120,120           EDGAR population of 10QSB, the 4th most common form in the family
```

**EVERY TOKEN FIGURE IN THIS DOCUMENT IS A CHARACTER-RATIO ESTIMATE** at 3.0 characters per token,
never a provider tokenizer count. Percentages are generated from the measured counts above and
rounded to the nearest whole percent: 271/613, 169/613 and 71/613.

Apple, the issuer the whole previous architecture was validated against, is roughly one eighth the
size of the largest filing in the corpus and sits in the easiest third of every distribution.

---

## Delivery principle: evidence, then contract, then schema

```
1. Measure a representative corpus.                      Phase 1
2. Learn what real models actually return from it.       Phase 2
3. Build the minimum orchestrator those results need.    Phase 3
4. Only then design persistence.                         Phase 8
```

Designing the database first is what produced migration `0003`: 22 unit types, six dispositions
and sixteen CHECK constraints describing an interpretation no model had ever produced.

---

## Current Status

| Area | Status |
|---|---|
| Repository scaffold, governance | IMPLEMENTED |
| SEC identity library | IMPLEMENTED |
| SEC client, rate limiting, throttle classification | IMPLEMENTED |
| Object storage abstraction and hashing | IMPLEMENTED (filesystem); S3 PLANNED |
| Configuration and User-Agent validation | IMPLEMENTED |
| Observability foundation | IMPLEMENTED |
| DERA mirror and fact loader | IMPLEMENTED (78 packages; 2,845 facts loaded historically) |
| LLM gateway, YAML boundary, payload compiler, boundary validator | IMPLEMENTED |
| Mock model provider | IMPLEMENTED |
| Filing discovery, one CIK | IMPLEMENTED |
| Filing acquisition and accession document inventory | IMPLEMENTED |
| Footnote extraction, canonicalization, table parsing | DEMOTED to validation oracle |
| Representative research corpus (112 issuers, 613 filings) | COMPLETE — Phase 1 |
| Commit 1: preservation, reusable infrastructure, test-database isolation | COMMITTED and PUSHED, CI green |
| Commit 2: architecture and governance realignment | IN PROGRESS |
| Commit 3: withdrawal of the rejected parser implementation | NOT STARTED |
| Empirical filing-diversity study | COMPLETE for the Phase 1 representative corpus; broaden only if later model experiments expose a material evidence gap |
| Corpus integrity assertions (hash, accession-to-CIK, identity) | IMPLEMENTED |
| Intact-input decision (Option A / B / C) | OPEN — Phase 1.5, blocks Phase 2 |
| Deterministic semantic parser and content ontology | WITHDRAWN (ADR-0016) |
| Local application database | REMOVED from the critical path |
| PostgreSQL schema for artifacts | DEFERRED to Phase 8 |
| Model catalog, four-role router | PLANNED (Phase 3) |
| Real provider adapter | PLANNED (Phase 2) |
| Parsed / summary / image artifacts | PLANNED (Phases 2, 4, 5) |
| Beta UI | PLANNED (Phase 6) |
| Deep Dive and chat | PLANNED (Phase 7) |

---

# Phase 1 — Representative Filing Corpus  (COMPLETE)

Acquire and measure real filings, across the COMPLETE SEC 10-K/10-Q reporting family, before
designing anything.

EXHAUSTIVE FORM-FAMILY DISCOVERY. Every time-eligible EDGAR quarterly master index from 1993Q1
through 2026Q3 — 135 quarters, zero unavailable, all populated and contributing. The SEC had also
pre-created a 2026Q4 directory; its index was a 236-byte header-only stub with zero data rows and
contributed nothing. 41 distinct 10-family form strings enumerated and adjudicated: 22 direct
substantive reports included, 19 near-matches excluded with a recorded reason. Every included form
carries an authoritative SEC description read from a real filing-detail page and a verified
accession. Qualifying-family logic is GENERATED from that inventory; an unreviewed future candidate
fails the gate.

DELIVERED
- 112 issuers, 613 filings, 760,174,532 bytes, every object SHA-256 verified, 0 throttle events.
- All 22 direct-report forms represented, including the small-business and transition families the
  first pass missed entirely.
- All six transport eras: pre-1996 SGML through current inline XBRL.
- 138 amendments; 313 annual and 300 quarterly; 42 small-business, 36 transition, 25 Item-405.
- Corpus integrity: 613/613 objects hash-verified, 0 missing, 0 duplicate (cik, accession) pairs,
  0 accession-to-CIK ownership mismatches, 0 authoritative-name contradictions.
- Human-readable source-set measured against filer-declared document tables on a 77-filing subset
  spanning every era, large financials, industrials, technology, young issuers, small-business
  forms, transition forms, amendments, image-heavy and PDF-bearing packages.

THE DEFECT THIS PHASE EXISTED TO CATCH. The first pass filtered on guessed hyphenated strings
`10-KSB` and `10-QSB`, matched almost nothing, and concluded the small-business family was
"effectively absent". EDGAR uses `10KSB` and `10QSB`. The real population is roughly 190,000
filings, and `10QSB` alone at 120,120 filings by 9,771 issuers is the FOURTH most common form in
the entire family. A guessed allowlist produced a confident, precise, inverted conclusion.

EXIT CRITERIA — MET. All eight family-discovery acceptance conditions pass.

# Phase 1.5 — OPEN: LIVE CAPABILITY DISCOVERY AND INTACT-SOURCE COMPATIBILITY  (BLOCKS PHASE 2)

STATUS: OPEN.

## Live Bedrock capability discovery

Nothing about the five candidates is known. Phase 1.5 discovers it:

```
which models are actually available          the exact model IDs and versions
regional support                             modalities, text and image
context limits                               output limits
supported request formats                    prices
```

PHASE 1.5 OWNS ALL NON-BILLABLE LIVE CAPABILITY DISCOVERY: actual availability, exact IDs and
versions, regions, modalities, context limits, output limits, supported request formats, official
pricing inputs, and intact-source compatibility. **Phase 2 CONSUMES that verified catalog; it does
not repeat the discovery.**

**No identifier, limit or price is trusted until discovery returns it**, and none may be recorded
anywhere as a settled fact before then.

Candidates, all UNVERIFIED and none currently configured or accessible: GPT OSS 120B,
NVIDIA Nemotron 3 Super 120B, Qwen3 235B A22B, Llama 4 Maverick, Qwen3 VL 235B.

**PHASE 1.5 PERFORMS NO BILLABLE MODEL INVOCATION WITHOUT SEPARATE EXPLICIT APPROVAL.** Capability
discovery is a catalog read. The first actual model experiment is Phase 2, and it is authorized
separately with a cost ceiling.

## Intact-source compatibility

CURRENT AUTHORIZED MODE: INTACT_SOURCE_ONLY.

For a filing and model pair:
- determine the complete relevant human-readable source set;
- determine actual provider compatibility once live capability discovery is authorized;
- if the complete intact source set fits, the model may be used;
- if it does not fit, that model is INCOMPATIBLE with that filing;
- the UI disables or rejects that pairing and explains why;
- another model may be selected ONLY by the user;
- no automatic projection, splitting, truncation, or model substitution occurs.

Original SEC artifacts are preserved byte-for-byte. Every relevant human-readable filed document
is sent intact. No visible-content projection. No semantic slicing. No mechanical multipart. No
silent truncation. No silent model substitution.

FUTURE OPTIONS REQUIRING SEPARATE EXPLICIT APPROVAL, none authorized:
- lossless mechanical multipart
- lossless reversible visible-content projection
- projection followed by multipart

The corpus measurements for those options are retained as RESEARCH EVIDENCE ONLY. They are not the
approved architecture. Option D in particular CONFLICTS with the intact-source requirement and must
not be implemented unless the user later authorizes that exception; its lower token cost is not
authorization.

# Phase 2 — Model Contract and Parsing Experiment  (the first real go/no-go)

Define a provisional flexible parser request and response, then run REAL parsing experiments
against materially different corpus samples and let the observed responses reshape the contract.

DELIVERABLES
- Provisional flexible parser request and response contracts, raw text or one unfenced YAML 1.2
  document, with the original-source exception for the intact artifact.
- Consume the verified Phase 1.5 model catalog and compatibility results. Discovery is NOT
  repeated here; Phase 2 begins from findings Phase 1.5 already established.
- Real parsing runs across all five candidate models over corpus samples that differ by era,
  industry, size, package shape and markup quality.
- Measurements: whether the provider accepts the intact artifact, input and output tokens,
  context compatibility, omissions, source coverage, citation fidelity, numeric fidelity, cost,
  latency, and response variability across models and across reruns of the same model.
- A revised elastic artifact format derived from what the models actually returned.

EXPLICITLY OUT OF SCOPE. Any rigid database schema. Any universal semantic taxonomy.

## The experiment has TWO levels

### Level 1 — BREADTH VALIDATION

At least one compatible approved parsing model must process representative intact filings covering:

```
all SIX transport eras                  standard annual and quarterly reports
transition forms                        small-business forms
Item-405 variants                       at least one amendment
young issuers AND mature issuers        at least one image-bearing filing
at least one large filing near a discovered context limit
```

**Attempt at least one intact parser trial for EVERY ONE of the 22 exact substantive form
strings**, where model compatibility and the approved cost ceiling permit it.

Any untested form must carry an explicit compatibility, availability or cost blocker recorded
against that exact form string. Another form is never silently treated as equivalent, and a
passing result is never invented.

### Level 2 — CROSS-MODEL COMPARISON

Run all available approved parsing candidates against a SMALLER SHARED BENCHMARK SET spanning
materially different eras, formats, sizes and issuers, measuring:

```
response structure      omission rate         source coverage
citation fidelity       numeric fidelity      cost
latency                 repeat-run variability
```

Every model is NOT required to process all 22 forms; context limits and cost make that
impossible for some. Level 2 is the comparison; Level 1 is the breadth, and neither substitutes
for the other.

ACCEPTANCE
- Level 1 breadth is met across all six transport eras, or every gap carries a recorded blocker.
- Every accepted parse passes coverage, citation and numeric validation against preserved bytes.
- Incompatibility is reported before invocation with bytes, tokens, limit and alternatives.
- Cost per filing is measured for the first time, per model, per era.
- Response variability is quantified, not assumed.

---

# Phase 3 — Minimum Orchestrator

Only what one safe parsing job requires.

- Four independent model roles and their selection records.
- Model capability discovery and the capability router.
- Intact-source compatibility checks with the no-slicing policy.
- Durable job state and resumption.
- Cost preview and explicit per-job authorization before any billable call.
- Object storage for originals, exact request bodies and exact response bodies.
- Minimal generic artifact metadata — identity, lineage, validation, tokens, cost, latency.
- Real-time progress streaming.

## The MINIMUM BETA CATALOG — required no later than Phase 3

The beta UI cannot be built on a catalog that does not exist until Phase 8. Phase 3 therefore
delivers the minimum local entity and filing catalog the product needs to operate, and Phase 6
completes the user-facing experience over it.

It must provide:

```
stable CIK identity                    current authoritative filer name
observed aliases                       current ticker where known
historical ticker observations WHERE AUTHORITATIVE EVIDENCE EXISTS
qualifying filing identities           exact filed forms, never normalized
earliest known qualifying filing       latest known qualifying filing
filing dates and report periods        local entity search
filing-bounded timeframe selection
incremental additions for the beta corpus and actively used entities
```

**NO FABRICATED HISTORICAL TICKER DATA.** Absent evidence is recorded as absent. A plausible
reconstruction is not an observation.

This is deliberately NOT the EDGAR universe. It is the entities the beta actually operates on,
grown incrementally. Full-universe population is Phase 8.

EXPLICITLY OUT OF SCOPE FOR PHASE 3. A broad semantic database. A universe-wide import. A
scheduler. Universe-scale alias reconciliation.

---

# Phase 4 — Image Workflow

- Multimodal parser path: one model, one call, images inline.
- Text parser plus separately selected image model.
- Non-semantic image inventory: location, dimensions, hash, containing document.
- Image-artifact linkage to source location and parsed artifact version.
- No duplicate image interpretation.

Corpus evidence, dated Phase 1, 2026-08-02: 187 of 613 filings carry at least one image, none
before 1996 and 80 of 108 in the current era; 11 carry PDFs; the largest package carries 108
images.

---

# Phase 5 — Summary Workflow

- Independently selected summary model.
- A separate summary artifact that references the accepted parse.
- Grounding validation against the parse and the original evidence.
- Regeneration without reparsing; supersession invalidates dependent summaries.

---

# Phase 6 — Functional Beta UI

- Completes the user-facing catalog experience over the Phase 3 minimum catalog: entity
  typeahead searching current name, former names, SEC filer name, current ticker, historical
  ticker and alias. An entity with no qualifying filing never appears.
- Timeframe selection bounded below by the entity's earliest known qualifying filing, so the
  control cannot offer a range the product cannot serve.

**PHASE 6 CANNOT BE COMPLETE UNTIL THE MINIMUM BETA CATALOG IS COMPLETE.** It depends on Phase 3
for the catalog, not on Phase 8.
- Four model selectors, capability-aware, with disabled states explained.
- Search button gated on validity, compatibility and budget.
- Live progress. Original view, clean parsed view, summary view, model and cost view.
- Persistent collapsible left search panel; light grey surfaces with translucent blue and green
  accents.

## MINIMUM AUTHENTICATION — a Phase 6 prerequisite to binding beyond loopback

Phase 6 produces a LAN-ACCESSIBLE beta, so Phase 6 owns the authentication that makes that safe.
It is not deferred to a phase that does not exist yet.

```
localhost-only operation until authentication is enabled
NO unauthenticated LAN exposure
server-side sessions
secure cookie behaviour where applicable
CSRF protection for state-changing browser requests
no provider credentials in the browser
no browser-to-Bedrock path
configurable bind address
```

Full multi-user identity management may remain deferred. Binding beyond loopback without the list
above may not.

---

# Phase 7 — Deep Dive and Chat

- Independently selected analysis/chat model.
- Immutable entity and timeframe scope, loaded server-side.
- Access to original evidence, not only summaries.
- Durable conversations, citations, per-turn budgets and cost controls.

---

# Phase 8 — Breadth and Persistence Optimization

Only after real model outputs are understood.

- Final PostgreSQL design, derived from accepted artifacts.
- Final Redis design.
- Derived indexes and search facets.
- Optional deterministic fast paths, where the corpus shows they are safe.

## CATALOG EXPANSION — Phase 8 only

Phase 8 EXPANDS the working minimum catalog built in Phase 3. It does not create it, and nothing
in Phase 6 waits for it.

```
complete EDGAR-wide entity population       complete historical qualifying filing acquisition
universe-scale alias and name-history reconciliation
scheduled incremental synchronization       durable checkpoints
amendment monitoring                        newly qualifying issuer discovery
performance optimization                    search-index optimization
large-scale backfill                        long-term operational scheduling
```

---

## Risks Register

| ID | Risk | Severity | Status |
|---|---|---|---|
| R-20 | Intact submission is unaffordable or impossible for a large fraction of filings. Dated Phase 1 evidence: 44% of primary documents exceed ~200k estimated tokens, 12% exceed ~1M | HIGH | OPEN. Phase 1.5 measures real limits; Phase 2 measures cost. The no-slicing policy makes it a visible failure, not a silent truncation |
| R-21 | No candidate model accepts a materially sized modern filing intact | HIGH | OPEN. Phase 2 |
| R-22 | The five user-approved candidate LABELS have not yet been mapped to verified Bedrock model IDs, versions, regions, modalities, limits or prices. They are labels, not provider identifiers | HIGH | OPEN. Phase 1.5 resolves the mapping |
| R-23 | Model parse output varies between reruns, weakening the completeness guarantee | HIGH | Mitigated by versioned candidate artifacts plus per-version coverage validation |
| R-24 | Token estimates are a character ratio, unfit for a compatibility gate | MEDIUM | Use provider token counting in Phase 2 |
| R-25 | Pre-2001 filing components are often not individually addressable through EDGAR; the complete-submission text may be the only retrievable source artifact, so the input contract must not assume a per-document URL | MEDIUM | Measured. Design constraint, not a defect. SUPERSEDES a withdrawn earlier finding that a third of filings declared no primary document, which came from index.json icon metadata; all 613 filings resolve one |
| R-26 | Malformed markup is normal before 2005 | MEDIUM | Measured. Transport tolerance required |
| R-27 | Corpus form-family coverage | HIGH | CLOSED. The initial guessed form filter missed small-business and transition forms. Exhaustive full-index discovery later identified and represented all 22 reviewed direct substantive form strings |
| R-28 | SEC identification must be validated before every acquisition run. The monitored contact remains outside tracked source and must never be replaced with a placeholder | MEDIUM | OPEN, operational. Enforced at startup by configuration validation |
| R-30 | Uniqueness rules keyed on accession alone reject valid EDGAR co-registrations | MEDIUM | CLOSED. Key is `(cik, accession)`; ownership verified from the archive path |
| R-29 | The configured SEC User-Agent contained a placeholder contact address, blocking acquisition | HIGH | CLOSED, historical. A real monitored contact was configured in the git-ignored `.env` and passed validation before the corpus was expanded. The address is not recorded in tracked source |
| R-06 | SEC access policy may change | MEDIUM | Revalidate before each ingestion phase |
| R-09 | Unit economics unknown | HIGH | Phase 2 produces the first measured figure |

---

## Deferred Work

| ID | Item | Revisit |
|---|---|---|
| D-20 | Final PostgreSQL schema | Phase 8 |
| D-21 | Redis data model | Phase 8 |
| D-22 | Entity-catalog SCHEDULER and universe-scale expansion | Phase 8. The minimum beta catalog itself is Phase 3 |
| D-23 | Parquet and DuckDB serving (ADR-0002) | Phase 8 |
| D-24 | pgvector retrieval (ADR-0007) | Phase 8 |
| D-25 | Terraform and ECS (ADR-0008, ADR-0009) | after the beta runs on LAN |
| D-01 | Form types beyond the 10-K and 10-Q families | after the beta |
| D-05 | FULL multi-user identity management (ADR-0014) | after the beta. The MINIMUM authentication and session protection required before binding beyond loopback is Phase 6 work, not deferred |

---

## Known Limitations

1. No model has ever been invoked by this project. Every cost figure is a placeholder.
2. The corpus is 613 filings out of millions. It is representative by construction, not complete.
3. Token counts throughout are character-ratio estimates, explicitly labelled as such.
4. The corpus represents all 22 reviewed direct substantive form strings, but its 613 filings
   remain a representative sample rather than the complete EDGAR population.
5. Structured numeric history remains XBRL-bound and effectively complete only from 2011.
6. No application database or active product persistence currently exists. PostgreSQL remains
   installed solely for isolated migration and persistence-integration testing through
   `fintek_test` and `fintek_integration_test`. Those are test infrastructure, not product
   persistence.

---

## Completed History

### Sprint 1 (COMPLETE)

Delivered the repository scaffold, all governance documents, thirteen ADRs, the SEC identity
library, the SEC client foundation with global and EFTS rate limiting and throttle
classification, configuration and User-Agent validation, object storage abstraction with hashing,
the observability foundation, DERA link discovery with a mirror ledger, and the complete LLM
content-boundary control set including the payload compiler, plain-text and YAML serializers, the
hardened YAML 1.2 safe parser, the boundary validator, the token comparison harness, and a mock
model provider. See `docs/sprints/SPRINT-0001.md` for the truthful record.

### Sprint 2 (COMPLETE)

Discharged URGENT-01 by mirroring all 78 DERA packages, built the SEC HTTP client required to do
it, added the 24-table PostgreSQL control-plane schema and its initial migration, and found and
fixed an unbounded YAML alias expansion vulnerability. See `docs/sprints/SPRINT-0002.md`.

### Alignment review (COMPLETE, `275db19`)

A product-alignment review of the repository against the fifteen core product requirements found
the content aligned and the sequencing materially drifted: the vertical slice was scheduled
before every capability it depended on. This roadmap is the correction. The review also produced
the Git governance amendment in `rules.md` sections 15 to 21, the dashboard UX specification, the
Deep Analysis model benchmark, the period-comparison specification, the item-disclosure exclusion
list, and schema corrections for the attachment audit and completeness state.

### Sprint 3 (COMPLETE, `2672222` · `1e9f343` · `bc9aeb6`)

Ended the condition where nothing had been retrieved from EDGAR. Discovered 134 Apple filings back
to 1994, reconciling gap-free against `master.gz`, and preserved four of them — the FY2025 10-K and
three 10-Qs — with SHA-256 provenance and offline fixtures. Installed a live PostgreSQL, applied
the sealed `0001_initial` against it, and ran the two live migration tests that had never once
executed. Loaded 2,845 DERA facts across those four filings with nine reconciliation checks each.
Discharged URGENT-02. See `docs/sprints/SPRINT-0003.md`.

### Sprint 4 (COMPLETE, `468d0f2`; hardened by `1d05199`)

Turned the 13-not-58 correction into production code. `footnote_extractor`,
`footnote_canonicalizer` stages 1 through 5, and `table_parser`, measured against the four
preserved filings: 43 canonical footnotes, 117 of 117 child blocks attached, zero orphans, zero
unresolved tables, and every attachment carrying method, confidence, evidence, and competing
candidates. Migration `0002_table_ownership` added. All 17 acceptance criteria met.

The closeout hardening that followed changed no behaviour and no measured result. It fixed three
checks that had stopped testing what they reported: the 10-Q results were measured but never
asserted, `make migration-check` had silently stopped covering `0002`, and CI ran on a deprecated
Node runtime. See `docs/sprints/SPRINT-0004.md`.
