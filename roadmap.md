# roadmap.md — FinTek Delivery Roadmap

STATUS OF THIS DOCUMENT: IMPLEMENTED (accurate as of Sprint 1)
LAST UPDATED: Sprint 1

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

## Current Status

| Area | Status |
|---|---|
| Repository scaffold | IMPLEMENTED |
| Governance documents | IMPLEMENTED |
| SEC identity library | IMPLEMENTED |
| SEC client foundation, rate limiting, throttle classification | IMPLEMENTED |
| Object storage abstraction and hashing | IMPLEMENTED |
| Configuration and User-Agent validation | IMPLEMENTED |
| Observability foundation | IMPLEMENTED |
| DERA link discovery and mirror ledger | IMPLEMENTED |
| LLM gateway, YAML boundary, payload compiler, boundary validator | IMPLEMENTED |
| Mock model provider | IMPLEMENTED |
| Bedrock provider adapter | PLANNED |
| Filing discovery at scale | PLANNED |
| Document acquisition | PLANNED |
| Fact lake | PLANNED |
| Canonical footnotes | PLANNED |
| Summarization pipeline | PLANNED |
| Dashboard serving | PLANNED |
| Deep Analysis | PLANNED |
| AWS deployment | PLANNED |

---

## URGENT: Time-Sensitive Action

```
ID:              URGENT-01
DESCRIPTION:     Mirror the SEC DERA Financial Statement and Notes datasets.
PRIORITY:        P0
STATUS:          IN_PROGRESS (discovery implemented; bulk download not yet executed)
OWNER:           unassigned
TARGET SPRINT:   2
```

The SEC retains only a rolling twelve months of monthly NOTES packages and deletes them once
consolidated into quarterly packages. Data currently reachable only as a monthly package becomes
permanently unreachable if deleted before its quarterly consolidation is published. This is the
only task in the project with an external deadline.

ACCEPTANCE CRITERIA: every currently listed monthly and quarterly NOTES package is downloaded,
hashed, recorded in the mirror ledger, and verified restorable. Re-running the mirror downloads
nothing new.

EVIDENCE REQUIRED: mirror ledger rows with URL, SHA-256, byte size, retrieval timestamp, and
dataset period for every package.

---

## MVP Definition

The MVP is complete only when all of the following are true.

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

---

## Phases

Each phase lists objective, scope, deliverables, dependencies, acceptance criteria, tests,
documentation obligations, risks, and exit criteria.

### Phase 0 — Urgent Preservation and Project Foundation

STATUS: COMPLETE (delivered in Sprint 1, except the bulk DERA download itself)

OBJECTIVE. Establish durable project memory and the safety-critical primitives that everything
else depends on, and begin preserving data that is disappearing.

DELIVERABLES. Repository scaffold. Governance documents. ADR structure. Sprint structure. SEC
identity library. SEC client foundation with rate control and throttle classification. Object
storage abstraction. Configuration validation. Observability foundation. DERA link discovery.
LLM content-boundary controls. Docker Compose. CI foundation.

DEPENDENCIES. None.

ACCEPTANCE CRITERIA. Governance files exist and are mutually consistent. Identity round-trips
under property tests. Rate limiter holds the configured sustained rate. Throttle classification
distinguishes rate blocks from configuration errors. User-Agent validation fails closed. DERA
links are scraped, never generated. Model-visible payloads reject Markdown, JSON, XML, HTML, and
XBRL.

TESTS. See `docs/testing/strategy.md`, Sprint 1 section.

DOCUMENTATION. `rules.md`, `roadmap.md`, `techspecs.md`, `CHANGELOG.md`, `README.md`, ADR-0001
through ADR-0013, `SPRINT-0001.md`, runbooks for SEC throttling and the DERA mirror.

RISKS. DERA monthly deletion window is outside our control.

EXIT CRITERIA. Sprint 1 acceptance criteria pass and are recorded truthfully.

### Phase 1 — One-Issuer Vertical Slice

STATUS: NOT STARTED
TARGET SPRINT: 3 to 5
DEPENDS ON: Phase 0

OBJECTIVE. Prove the product thesis end to end on a single issuer, and prove the canonical
footnote correction in production code.

SCOPE. Apple Inc., CIK 0000320193, chosen because its structure is already verified. No
issuer-specific logic may enter the architecture.

DELIVERABLES. Filing discovery for one CIK. Acquisition of one modern 10-K and several 10-Qs.
DERA source loading. Fact extraction. Canonical footnote grouping. Verified note count. One
summary per canonical footnote. Stored summaries. One financial chart. All note summaries
rendered. One Deep Analysis session. Rejection of a cross-ticker request.

ACCEPTANCE CRITERIA.
- Apple FY2025 10-K yields exactly 13 canonical footnotes.
- All 46 child blocks attach to a parent; zero orphans.
- The three Item-disclosure blocks are classified as filing sections, not footnotes.
- 13 canonical footnotes produce 13 active accepted summaries.
- A dashboard session records zero model invocations.
- A Deep Analysis session scoped to Apple refuses a Microsoft comparison without a model call.

TESTS. Golden fixtures for the Apple 10-K. Property test asserting no completed filing lacks a
summary. Security test asserting cross-ticker refusal.

RISKS. Role-URI grouping is verified on one filing only. Phase 2 must validate breadth before
scale-out.

EXIT CRITERIA. All acceptance criteria pass on real fetched data, not fixtures alone.

### Phase 2 — Issuer Universe

STATUS: NOT STARTED
TARGET SPRINT: 6 to 7
DEPENDS ON: Phase 0

OBJECTIVE. Build the temporal issuer registry and determine the active universe.

DELIVERABLES. Temporal issuer registry. Historical listing observations. Exclusion table with
reasons. Delisted issuer handling. Filing-history completeness reconciliation against master
indexes.

ACCEPTANCE CRITERIA. Universe contains only CIKs with at least one historical 10-K or 10-Q.
Excluded filers are preserved with a reason. A ticker reused by two issuers resolves correctly by
date. A delisted former filer still resolves.

RISKS. Ticker snapshot instability across CDN edges requires multi-fetch union.

### Phase 3 — Fact Lake and Metrics

STATUS: NOT STARTED
TARGET SPRINT: 8 to 10
DEPENDS ON: Phase 2

DELIVERABLES. DERA ingest. Immutable facts. Curated metric definitions. Fiscal logic. Q4
derivation. Serving datasets.

ACCEPTANCE CRITERIA. Quarterly revenue for Apple, Costco, and Starbucks has no missing fourth
bar. No operating-cash-flow series mixes durations. Revenue resolves gap-free for issuers whose
dominant concept changes mid-history.

### Phase 4 — All-Time Acquisition

STATUS: NOT STARTED
TARGET SPRINT: 11 to 13
DEPENDS ON: Phase 2

DELIVERABLES. Era-aware acquisition across all four eras. Resumable backfill. Raw preservation.
Reconciliation against quarterly master indexes.

ACCEPTANCE CRITERIA. Apple resolves filings from 1994 with no gap against `master.gz`. A killed
and resumed backfill produces no duplicates and no gaps.

### Phase 5 — Canonical Footnotes at Scale

STATUS: NOT STARTED
TARGET SPRINT: 14 to 17
DEPENDS ON: Phases 1, 4

DELIVERABLES. DERA-based grouping. Hot-path extraction for filings newer than the latest DERA
drop. Historical parser. Table association. Completeness checks.

ACCEPTANCE CRITERIA. Grouping validated across at least 25 issuers spanning all four eras with a
documented confidence distribution and a populated review queue.

RISKS. Role URIs do not exist before 2009. Historical grouping is text-only and will have
materially lower confidence.

### Phase 6 — LLM Production Pipeline

STATUS: NOT STARTED
TARGET SPRINT: 18 to 21
DEPENDS ON: Phase 5

DELIVERABLES. Bedrock provider adapter. Batch processing. Model benchmark. Prompt versions.
Validation pipeline. Cost accounting. Repair path.

ACCEPTANCE CRITERIA. A model is selected by measured benchmark, not assumption. Numeric fidelity
at or above 99.5 percent. Zero omitted footnotes across the benchmark corpus.

### Phase 7 — Serving Architecture

STATUS: NOT STARTED
TARGET SPRINT: 22 to 24
DEPENDS ON: Phase 3

DELIVERABLES. Versioned Parquet publication. Atomic pointer flip. PostgreSQL control plane. API.
Cache.

ACCEPTANCE CRITERIA. Ingestion writes while API workers read, with zero lock errors.

### Phase 8 — Dashboard

STATUS: NOT STARTED
TARGET SPRINT: 25 to 28
DEPENDS ON: Phase 7

DELIVERABLES. Issuer search. Timeframe selection. Charts. Filing timeline. Every-footnote UI.
Source links. Processing coverage display.

ACCEPTANCE CRITERIA. Coverage renders honestly, showing partial states rather than hiding them.

### Phase 9 — Deep Analysis

STATUS: NOT STARTED
TARGET SPRINT: 29 to 33
DEPENDS ON: Phases 5, 7

DELIVERABLES. Session creation. Scope enforcement. Retrieval. Analysis model integration.
Conversation memory. Budgets. Citations. Abuse tests.

ACCEPTANCE CRITERIA. Every threat in `docs/deep-analysis/security.md` has a passing test.

### Phase 10 — Historical Numeric Extraction

STATUS: DEFERRED
DEPENDS ON: Phase 4

DELIVERABLES. Pre-XBRL statement table extraction. Deterministic parser. Model-assisted
extraction only where validated. Historical chart expansion.

RATIONALE FOR DEFERRAL. Documents and footnote summaries already reach the 1990s without this
work. Only numeric charts are XBRL-bound. This phase closes that gap and is valuable, but no
earlier phase depends on it.

---

## Sprint Breakdown

| Sprint | Objective | Status |
|---|---|---|
| 1 | Foundation, governance, SEC primitives, LLM boundary controls | COMPLETE |
| 2 | Execute DERA mirror download; PostgreSQL schema and migrations | NOT STARTED |
| 3 | Filing discovery and acquisition for one CIK | NOT STARTED |
| 4 | Fact loading and canonical footnote grouping for one filing | NOT STARTED |
| 5 | Summarization of every canonical footnote for one filing | NOT STARTED |

---

## Risks Register

| ID | Risk | Severity | Mitigation | Status |
|---|---|---|---|---|
| R-01 | DERA monthly packages deleted before mirroring | HIGH | URGENT-01 in Sprint 2 | OPEN |
| R-02 | Role-URI grouping verified on one filing only | HIGH | Phase 5 breadth validation across 25 issuers | OPEN |
| R-03 | Pre-2009 filings have no role URIs | MEDIUM | Text-only grouping with lower confidence, surfaced in UI | OPEN |
| R-04 | Bedrock catalog and pricing unverified | MEDIUM | Blocking gate before Phase 6 cost commitment | OPEN |
| R-05 | Item-disclosure exclusion list will drift as SEC adds mandates | MEDIUM | Reviewed config plus unknown-namespace review flag | OPEN |
| R-06 | SEC access policy may change | MEDIUM | Revalidate before each ingestion phase | OPEN |
| R-07 | Scope-classifier false negatives leak Deep Analysis cost | MEDIUM | Budgets are the backstop; violations logged and alerted | OPEN |

---

## Deferred Work

| ID | Item | Reason | Revisit when |
|---|---|---|---|
| D-01 | Form types 20-F, 40-F, 8-K, DEF 14A, S-1 | Not in MVP scope | After Phase 8 |
| D-02 | Delisted issuer historical backfill via Internet Archive | Requires daily snapshots to accrue first | After Phase 2 |
| D-03 | OpenSearch retrieval | pgvector sufficient until measured otherwise | If retrieval quality or scale demands it |
| D-04 | Pre-XBRL numeric extraction | Phase 10 | After Phase 4 |
| D-05 | Real user authentication | Local single-user interface implemented; see ADR-0014 | Before public deployment |

---

## Known Limitations

1. The active universe excludes issuers that never filed a 10-K or 10-Q, which removes foreign
   private issuers filing 20-F. Their exclusion reason is preserved so they can be enabled later.
2. Any analysis built on the current-listings universe is survivorship-biased until historical
   listing observations accrue. Recorded so it is never mistaken for full coverage.
3. Canonical grouping confidence is verified on exactly one filing. Do not present the
   100 percent attachment result as a general guarantee.
4. Structured numeric history is XBRL-bound and effectively complete only from 2011 onward,
   though documents and footnote text reach the 1990s.

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
