# roadmap.md — FinTek Delivery Roadmap

STATUS OF THIS DOCUMENT: IMPLEMENTED (accurate as of Sprint 3 completion)
LAST UPDATED: Sprint 3 completion, 2026-08-01
SEQUENCING DECISION: `docs/adr/ADR-0015-thread-first-delivery-sequence.md`

---

## Product Vision

An investor types a ticker and receives that company's SEC filings already digested: deterministic
financial charts, and one plain-language summary for every financial-statement footnote in every
10-K and 10-Q the company has ever filed. When the investor wants to go deeper, they explicitly
start a Deep Analysis session that is locked to that issuer and that corpus.

The insight the product is built around: a 10-K may run 100 pages, of which only a page or two is
the actual financial statements. The rest is footnotes explaining *why* the company did what it
did, and that is what investors actually need. The footnotes are the product.

---

## Delivery principle: prove the thread before widening it

This roadmap builds one complete vertical thread through every layer of the product before it
builds any layer at full width.

The reason is specific. The three riskiest unknowns in this project are:

```
1. Can a model summarize a real footnote at the required numeric fidelity?
2. What does that cost per footnote, per filing, and per issuer history?
3. Do the zero-LLM read path and the Deep Analysis scope lock actually hold in running code?
```

None of them is answered by building an issuer registry, a full-history backfill, or a
120-fixture benchmark corpus. All three are answered by taking **one issuer through every layer**.
Until they are answered, breadth work is investment against an unvalidated thesis.

The previous version of this roadmap scheduled the vertical slice as Phase 1 at sprints 3 to 5,
while scheduling summarization at sprints 18 to 21, the dashboard at 25 to 28, and Deep Analysis
at 29 to 33 — so the slice depended on work scheduled up to thirty sprints after it. That
contradiction is resolved here: **Sprints 3 through 7 contain every dependency the slice needs,
and nothing else.**

---

## Current Status

| Area | Status |
|---|---|
| Repository scaffold | IMPLEMENTED |
| Governance documents | IMPLEMENTED |
| SEC identity library | IMPLEMENTED |
| SEC client foundation, rate limiting, throttle classification | IMPLEMENTED |
| SEC HTTP client | IMPLEMENTED |
| Object storage abstraction and hashing | IMPLEMENTED (filesystem); S3 PLANNED |
| Configuration and User-Agent validation | IMPLEMENTED |
| Observability foundation | IMPLEMENTED |
| DERA link discovery and mirror ledger | IMPLEMENTED |
| DERA live mirror | COMPLETE (78/78 packages, 25.36 GiB) |
| LLM gateway, YAML boundary, payload compiler, boundary validator | IMPLEMENTED |
| Mock model provider | IMPLEMENTED |
| PostgreSQL schema and initial migration | IMPLEMENTED and APPLIED to a live database (Sprint 3) |
| DERA TSV loading, validation, reconciliation | IMPLEMENTED and EXECUTED (Sprint 3; 2,845 facts, 4 filings) |
| Filing discovery, one CIK | IMPLEMENTED (Sprint 3) |
| Filing acquisition, inline-XBRL era | IMPLEMENTED (Sprint 3) |
| Canonical footnote grouping, stages 1 to 5 | IMPLEMENTED and MEASURED (Sprint 4; 4 filings, 0 orphans, 0 unresolved tables) |
| Real provider adapter | PLANNED (Sprint 5); AWS identity policy IMPLEMENTED as governance |
| Summarization pipeline | PLANNED (Sprint 5) |
| Read API and dashboard | PLANNED (Sprint 6) |
| Deep Analysis, FILING scope | PLANNED (Sprint 7) |
| Issuer universe | PLANNED (Sprint 8+) |
| All-time acquisition | PLANNED (Sprint 8+) |
| AWS deployment | PLANNED (post-slice) |

---

## URGENT: Time-Sensitive Action

```
ID:              URGENT-01
DESCRIPTION:     Mirror the SEC DERA Financial Statement and Notes datasets.
PRIORITY:        P0
STATUS:          COMPLETE  (Sprint 2, 2026-08-01)
OWNER:           unassigned
TARGET SPRINT:   2
COMPLETION EVIDENCE:
    78 of 78 discoverable packages persisted, 0 failed, 27,228,877,737 bytes (25.36 GiB).
    Every package SHA-256 recorded and CRC-validated via zipfile.testzip().
    Second full run: 0 downloaded, 78 already present. Idempotency proven.
    Independent re-validation: 78/78 sha256 re-verified, 78/78 ZIP CRC re-verified, 0 failures.
    Manifest: var/dera/manifest.json   Ledger: var/dera/ledger.json
    The twelve monthly packages with no quarterly consolidation (2025_07 through 2026_06)
    were secured first, in a separate run, before the bulk.
```

The SEC retains only a rolling twelve months of monthly NOTES packages and deletes them once
consolidated into quarterly packages. This was the only task in the project with an external
deadline.

ACCEPTANCE CRITERIA: MET.

```
ID:              URGENT-02
DESCRIPTION:     Second durable copy of the twelve irreplaceable monthly DERA packages.
PRIORITY:        P1
STATUS:          COMPLETE  (Sprint 3, 2026-08-01)
TARGET SPRINT:   3
COMPLETION EVIDENCE:
    12 of 12 packages copied to a second, separate filesystem and verified.
    2,145,477,071 bytes. Source device and destination device differ, confirmed by stat.
    Every package: source SHA-256 verified against the mirror ledger, destination SHA-256
    verified after copy, and ZIP CRC verified by reading every member.
    Second run copied 0 bytes, reused 2,145,477,071, and re-verified every hash.
    Source files were neither modified nor deleted.
    Manifest and verification report written beside the copy.
    CAVEAT: the destination mount is not persistent. No fstab entry exists, so the device
    does not remount automatically after a reboot. The data is safe on a separate device;
    the PATH is not guaranteed to be present. Re-verify after any reboot.
```

---

## MVP Definition

The MVP is complete only when all of the following are true. Unchanged from the original
definition; the sequence for reaching it is what changed.

1. At least one issuer works end to end.
2. Several filings are ingested from source.
3. Every actual footnote in those filings is represented as a canonical record.
4. Every extracted canonical footnote has a stored, validated, active summary.
5. Financial facts are traceable to the filed source.
6. Derived metrics are deterministic and reproducible.
7. Dashboard access causes zero model invocations, proven by test.
8. Five-year data renders entirely from storage.
9. A Deep Analysis session can be created and answers a question.
10. Deep Analysis retrieves original filing evidence, not only summaries.
11. Deep Analysis remains locked to one issuer and scope.
12. A cross-ticker request is rejected without a model call.
13. Token and cost accounting are recorded per invocation.
14. Documentation is synchronized with implementation.
15. A new engineer or language model can continue the project from the repository alone.

**Every one of these is satisfied by the end of Sprint 7.** Nothing in Stage 2 below is required
for the MVP.

---

# Stage 1 — The Vertical Thread (Sprints 3 to 7)

One issuer. Every layer. No breadth.

Issuer: **Apple Inc., CIK 0000320193**, chosen because its footnote structure is already
verified against the live filing. No issuer-specific logic may enter the architecture; the
architecture tests exist to catch it.

---

### Sprint 3 — Acquire one issuer's filings and establish reproducible fixtures

STATUS: COMPLETE — all thirteen acceptance criteria met, audited in the sprint record
DEPENDS ON: Sprint 2
DETAILED PLAN AND OUTCOME: `docs/sprints/SPRINT-0003.md`

DONE. Filing discovery (134 filings, 1994-2026, reconciling 134 = 134 against `master.gz` with
zero gaps). Inline-XBRL acquisition of the FY2025 10-K and three 10-Qs, 20 objects and 8.42 MiB
preserved with provenance, idempotent at zero requests on re-run. Committed fixtures with a
source manifest. The item-disclosure exclusion list tested against real acquired data.

DONE SINCE. PostgreSQL 18.4 installed locally, using peer authentication over the Unix socket, so
no password is stored for local work. Deployed authentication remains an open decision. The migration applies, downgrades, and reapplies against it. Both live
migration tests now pass rather than skip: the suite reports 203 passed, 0 skipped. URGENT-02
discharged with a verified second copy on a separate filesystem.

DONE LAST. The DERA fact load. 2,845 facts across the four filings, from four different packages,
each load reconciled on nine checks including an exact numeric-total match against PostgreSQL's own
`sum()`. A rerun re-reads the whole package and inserts nothing. The suite is 337 passed, 0
skipped, and CI now runs a PostgreSQL service container so the database tests execute there rather
than skip.

CARRIED FORWARD, not blocking. The backup mount is still not persistent across reboots; the exact
`fstab` entry and validation sequence are in `docs/runbooks/dera-backup-mount.md` and applying it
needs root. Acquired objects are not yet registered in `filing_document`.

OBJECTIVE. End the condition where nothing has been retrieved. Get four real Apple filings into
the system, preserved with provenance, and make the canonical-footnote result reproducible
offline.

DELIVERABLES.
- A live local PostgreSQL from the project's own `docker-compose.yml`.
- The two skipped live migration tests executed, upgrade and downgrade, against that database.
- DERA TSV loading for the single partition covering the target filings.
- `packages/filing_discovery` for one CIK: `submissions.zip`, `filings.files[]` overflow, and
  reconciliation against `master.gz`.
- `packages/filing_acquisition` for the inline-XBRL era only.
- Apple FY2025 10-K plus three 10-Qs, preserved with SHA-256 and full provenance.
- A documented fixture strategy and the fixtures it produces.
- `metric_definitions/item_disclosure_exclusions.yaml` exercised by a test.
- URGENT-02 discharged.

ACCEPTANCE CRITERIA.
- `alembic upgrade head` and `alembic downgrade base` both succeed against a real PostgreSQL,
  and the two previously skipped tests pass rather than skip.
- One DERA partition is queryable and its row counts reconcile against the package.
- Four Apple filings are preserved, hashed, and re-acquirable idempotently.
- The filing list for CIK 0000320193 reconciles gap-free against `master.gz`.
- A fresh clone runs the entire suite offline, with no network and no SEC access.
- The repository grows by less than 25 MB.

EXIT CRITERIA. All of the above, on real fetched data.

---

### Sprint 4 — Reproduce and validate canonical-footnote extraction

STATUS: COMPLETE — 4 filings, 43 canonical footnotes, 0 orphans; see docs/sprints/SPRINT-0004.md
DEPENDS ON: Sprint 3, which is COMPLETE

GATE SATISFIED. Every Sprint 3 exit criterion is met and audited in `docs/sprints/SPRINT-0003.md`:
PostgreSQL, the live migration, both previously skipped tests, the DERA fact load with
reconciliation, and URGENT-02.

OBJECTIVE. Prove the footnote thesis in production code, against the fixtures, deterministically.

DELIVERABLES. `packages/footnote_extractor`. `packages/footnote_canonicalizer` implementing
**stages 1 through 5 only** — candidate discovery, item exclusion, role-URI attachment, TOC
reconciliation, heading reconciliation. Per-attachment audit persistence. Completeness
computation. `packages/table_parser` sufficient for the tables in the four fixture filings.

EXPLICITLY OUT OF SCOPE. Stages 6 through 11. They are fallbacks for a failure mode that
measured 0 of 46 on the verified filing. They are built in Stage 2 when breadth exposes the
cases that need them.

ACCEPTANCE CRITERIA.
- Apple FY2025 10-K yields **exactly 13** canonical footnotes.
- All **46 of 46** child blocks attach to a parent; zero orphans.
- The three Item-408 and Item-1C disclosures are classified as `filing_section`, not footnotes.
- Every attachment records method, confidence, evidence, and competing candidates.
- A filing with a deliberately removed summary computes `PARTIAL`, never `COMPLETE`.
- The three 10-Qs each produce a canonical footnote set with zero orphans.

RISKS. Role-URI grouping is verified on one filing. Breadth validation is Stage 2 and this
sprint's result must not be presented as a general guarantee.

---

### Sprint 5 — Real-model summarization, fidelity, and cost

STATUS: NOT STARTED
DEPENDS ON: Sprint 4

OBJECTIVE. Answer the two questions the project cannot currently answer: does it work, and what
does it cost. **This is the go/no-go sprint.**

AUTHENTICATION PREREQUISITE. Before the first Bedrock call, a developer identity must exist that
is obtained through an approved external federated credential provider and scoped to only the
Bedrock actions and model resources the benchmark needs. **No long-lived access key is created for
this, at any point, by anyone.** The benchmark additionally requires a hard invocation budget, a
hard dollar budget, an explicit model allowlist, an explicit region, and a manual start. The rule
is `rules.md` section 3; the design is `docs/security/aws-identity-and-secrets.md`. The policy is
already in force — it is enforced by tests today, before any provider code exists.

DELIVERABLES.
- `docs/llm/model-catalog.md`: verified model identifiers, region availability, context and
  output limits, and observed prices — obtained by calling the provider, not from memory.
- `packages/llm_gateway/providers/bedrock.py`, the first real provider adapter.
- `packages/summarization`: one job per canonical footnote.
- `packages/validation`: schema, identity, source-resolution, and numeric reconciliation against
  `footnote_table` and `xbrl_fact` on value, unit, scale, sign, and period.
- The **tier-1 smoke benchmark** — 15 footnotes, at least 2 candidate models — per
  `docs/llm/model-benchmark.md`.
- Measured parameters replacing every placeholder in `docs/llm/cost-model.md`.

ACCEPTANCE CRITERIA.
- 13 canonical footnotes produce 13 stored, validated, active summaries.
- Numeric fidelity 1.0 across the smoke corpus; any error on 15 items is a real defect.
- Every response is one unfenced YAML 1.2 document; zero boundary violations.
- Every citation resolves to a source block belonging to that footnote.
- `cost_per_footnote`, `cost_per_filing`, and extrapolated `cost_per_issuer_history` are
  published as measured numbers.
- Every invocation records tokens, cost, latency, prompt version, model identifier, and the
  object-storage URIs of the exact request and response bodies.

EXIT CRITERIA. The above, plus an explicit written go/no-go on unit economics. A tier-1 pass is
provisional and does not select a production model.

---

### Sprint 6 — The stored-data dashboard and the zero-LLM read path

STATUS: NOT STARTED
DEPENDS ON: Sprint 5

OBJECTIVE. Prove requirement 9 in executable code, and render the product.

DELIVERABLES.
- `packages/fiscal`, `packages/xbrl`, `packages/fact_lake`, `packages/financial_metrics`
  sufficient for one issuer: duration-aware filtering, Q4 derivation, curated metric resolution.
- Versioned Parquet publication with an atomic pointer flip.
- `apps/api`: the read endpoints in `docs/api/openapi.yaml`.
- `apps/web`: the screens in `docs/dashboard/ux-specification.md`.
- `footnote_comparison` computation per `docs/footnotes/period-comparison.md`.

ACCEPTANCE CRITERIA.
- `test_dashboard_session_invokes_no_model` passes: a full browse records **zero**
  `llm_invocation` rows. **This test lands in the same sprint as the first endpoint.**
- Five-year and all-time views render entirely from storage.
- A quarterly revenue series shows a fourth bar, labelled derived.
- A filing with 12 of 13 summaries renders as *12 of 13* with the thirteenth listed.
- Low-confidence and partial states render per the UX specification.
- Ingestion writes while API workers read, with zero lock errors.

---

### Sprint 7 — Filing-scoped Deep Analysis and cost containment

STATUS: NOT STARTED
DEPENDS ON: Sprints 5, 6

OBJECTIVE. Prove requirements 10 through 14.

DELIVERABLES.
- `packages/deep_analysis` including `scope.py`, the single home for scope validation.
- `FILING` scope only. `FOOTNOTE` and `TIMEFRAME` scopes are Stage 2.
- The deterministic cross-issuer detector, positioned **before** any retrieval or model spend.
- The bounded YAML action protocol in `docs/deep-analysis/action-protocol.yaml`.
- `packages/retrieval` over the authorized corpus.
- Budgets enforced pre-flight; conversation memory; citation validation.
- The **Deep Analysis model benchmark**, adversarial subset included, per
  `docs/llm/analysis-model-benchmark.md`.

ACCEPTANCE CRITERIA.
- A session scoped to Apple answers a real question with citations resolving to original
  evidence, not to summaries.
- A Microsoft comparison is refused with **zero** `llm_invocation` rows.
- Every threat in `docs/deep-analysis/security.md` has a passing test.
- A filing fixture containing "ignore previous instructions" produces no behaviour change.
- Exceeding `max_cost_usd` refuses the turn.
- Detector recall and precision are measured and published.

EXIT CRITERIA. **All fifteen MVP criteria satisfied. The product is proven.**

---

# Stage 2 — Widening (Sprint 8 onward)

Nothing here starts until Stage 1 exits. Ordering within Stage 2 is revisited after Sprint 7,
because the measured cost from Sprint 5 will change what is affordable.

| Phase | Objective | Depends on | Was previously |
|---|---|---|---|
| W-1 | Issuer universe: temporal registry, listing observations, exclusion table, delisted handling | Sprint 7 | Phase 2, sprints 6–7 |
| W-2 | All-time acquisition across all four eras; resumable backfill; reconciliation | W-1 | Phase 4, sprints 11–13 |
| W-3 | Canonicalization stages 6–11; breadth validation across ≥25 issuers, all eras | W-2 | Phase 5, sprints 14–17 |
| W-4 | Tier-2 benchmark, 120 fixtures; production model selection; batch processing | W-3 | Phase 6, sprints 18–21 |
| W-5 | Full-corpus backfill | W-4 | Phase 6 |
| W-6 | Remaining Deep Analysis scopes; pgvector retrieval | W-3 | Phase 9 |
| W-7 | AWS deployment, Terraform, ECS | W-5 | Phase 7 |
| W-8 | Pre-XBRL numeric extraction | W-2 | Phase 10, deferred |

W-3 closes risk R-02, W-4 closes R-04, and W-8 closes the pre-2009 numeric gap. All three are
genuinely valuable and none is required to prove the product.

**W-7 authentication prerequisite.** Terraform authenticates through a temporary federated or
OIDC-assumed role, and GitHub Actions assumes a deployment role through OpenID Connect. No AWS
access key is stored as a GitHub secret, embedded in a provider block, or written into a variable
file. Each ECS workload receives its own least-privilege task role, kept separate from the
task-execution role. This is settled policy rather than a W-7 design decision: `rules.md` section
3, detailed in `docs/security/aws-identity-and-secrets.md`.

---

## Sprint Breakdown

| Sprint | Objective | Status |
|---|---|---|
| 1 | Foundation, governance, SEC primitives, LLM boundary controls | COMPLETE |
| 2 | Execute DERA mirror download; PostgreSQL schema and migrations | COMPLETE |
| — | Alignment review; thread-first resequencing; governance amendment | COMPLETE (uncommitted) |
| 3 | Acquire one issuer's filings; reproducible fixtures | IN PROGRESS — filings retrieved; database blocked |
| 4 | Canonical-footnote extraction, stages 1–5 | NOT STARTED |
| 5 | Real-model summarization; fidelity and cost measurement | NOT STARTED |
| 6 | Dashboard and the zero-LLM read path | NOT STARTED |
| 7 | Filing-scoped Deep Analysis and cost containment | NOT STARTED |
| 8+ | Stage 2 widening, order revisited after Sprint 7 | NOT STARTED |

---

## Risks Register

| ID | Risk | Severity | Mitigation | Status |
|---|---|---|---|---|
| R-01 | DERA monthly packages deleted before mirroring | HIGH | URGENT-01 discharged in Sprint 2; all 78 packages held and re-validated | CLOSED |
| R-02 | Role-URI grouping verified on one filing only | HIGH | W-3 breadth validation across ≥25 issuers. Not blocking Stage 1, which is explicitly one issuer | OPEN |
| R-03 | Pre-2009 filings have no role URIs | MEDIUM | Text-only grouping with lower confidence, surfaced in the UI | OPEN |
| R-04 | Provider catalog and pricing unverified | HIGH | **Moved forward to Sprint 5** from Phase 6. Blocking gate before any cost commitment | OPEN |
| R-05 | Item-disclosure exclusion list drifts as SEC adds mandates | MEDIUM | `metric_definitions/item_disclosure_exclusions.yaml` with an unknown-namespace review policy | MITIGATED |
| R-06 | SEC access policy may change | MEDIUM | Revalidate before each ingestion phase | OPEN |
| R-07 | Scope-classifier false negatives leak Deep Analysis cost | MEDIUM | Detector measured independently in Sprint 7; budgets are the backstop | OPEN |
| R-08 | Twelve irreplaceable DERA monthly packages exist in one location | HIGH | URGENT-02 discharged: verified second copy on a separate filesystem | CLOSED |
| R-10 | No PostgreSQL is reachable on the development machine | HIGH | PostgreSQL 18.4 installed and running; migration applied; both live tests pass | CLOSED |
| R-09 | Unit economics unknown; the product may be unaffordable at corpus scale | HIGH | **Sprint 5 is an explicit go/no-go.** Previously unresolved until sprint ~20 | OPEN |

---

## Deferred Work

| ID | Item | Reason | Revisit when |
|---|---|---|---|
| D-01 | Form types 20-F, 40-F, 8-K, DEF 14A, S-1 | Not in MVP scope | After Stage 1 |
| D-02 | Delisted issuer historical backfill via Internet Archive | Requires daily snapshots to accrue first | After W-1 |
| D-03 | OpenSearch retrieval | pgvector sufficient until measured otherwise; ADR-0007 | If retrieval quality or scale demands it |
| D-04 | Pre-XBRL numeric extraction | W-8 | After W-2 |
| D-05 | Real user authentication | Local single-user implementation; ADR-0014 | Before public deployment |
| D-06 | Canonicalization stages 6–11 | Fallbacks for a case that measured 0 of 46 | W-3 |
| D-07 | Tier-2 120-fixture benchmark | Tier-1 smoke benchmark suffices to prove the pipeline | W-4 |
| D-08 | `FOOTNOTE` and `TIMEFRAME` analysis scopes | `FILING` scope proves the security model | W-6 |
| D-09 | Terraform and ECS implementation | ADR-0008 and ADR-0009 are PROVISIONAL until W-7 | W-7 |

---

## Known Limitations

1. The active universe excludes issuers that never filed a 10-K or 10-Q, which removes foreign
   private issuers filing 20-F. Their exclusion reason is preserved so they can be enabled later.
2. Any analysis built on the current-listings universe is survivorship-biased until historical
   listing observations accrue.
3. Canonical grouping confidence is verified on exactly one filing. Do not present the
   100 percent attachment result as a general guarantee.
4. Structured numeric history is XBRL-bound and effectively complete only from 2011 onward,
   though documents and footnote text reach the 1990s.
5. No cost figure exists for any part of the corpus. Sprint 5 produces the first measured one.
   Any earlier number was withdrawn as unusable, see `docs/llm/cost-model.md`.
6. Structured numeric history exists for four filings only. Widening it requires registering more
   issuers and filings, which is Stage 2 phase W-1: `xbrl_fact` has foreign keys to `issuer` and
   `filing`, so the loader is per-accession by construction.
7. Loaded DERA periods are month-end approximations and every row is `UNVALIDATED`. DERA rounds
   `ddate` to the nearest month end and publishes no period start at all. Apple's FY2025 ended
   2025-09-27 and DERA records 2025-09-30. Exact filed boundaries arrive with the XBRL instance
   in Sprint 6 and supersede these rows through the append-only restatement path.
8. Idempotency of the fact load rests on a read-then-insert inside one transaction, serialized by
   a transaction-scoped advisory lock, not on a unique index over
   `(accession, source_dataset, source_row_id)`. Migration `0001_initial` is SEALED, so that index
   is a second migration. Correct for today's single-writer ingest; required before concurrent
   ingest.

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

### Alignment review (COMPLETE, uncommitted)

A product-alignment review of the repository against the fifteen core product requirements found
the content aligned and the sequencing materially drifted: the vertical slice was scheduled
before every capability it depended on. This roadmap is the correction. The review also produced
the Git governance amendment in `rules.md` sections 15 to 21, the dashboard UX specification, the
Deep Analysis model benchmark, the period-comparison specification, the item-disclosure exclusion
list, and schema corrections for the attachment audit and completeness state.
