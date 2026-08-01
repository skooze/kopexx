# rules.md — Operating Contract for FinTek

STATUS: IMPLEMENTED (this document is authoritative as of Sprint 1)

---

## 0. MANDATORY READ-FIRST INSTRUCTION

```
Before planning or modifying this repository:

1. Read rules.md.
2. Read roadmap.md.
3. Read techspecs.md.
4. Read CHANGELOG.md.
5. Read the latest sprint record in docs/sprints/.
6. Read relevant ADRs in docs/adr/.
7. Search the codebase for reusable implementations before writing new ones.
8. Identify affected tests and documentation.
9. Do not rely on prior chat history as project memory.
```

This repository is the durable project memory. No conversation, ticket, or chat log is
authoritative. If this file disagrees with code, that is a defect: fix one or the other and
record the reconciliation in the sprint record.

---

## 1. Project Intent

FinTek is a financial filing and historical analysis platform.

### What the product does

1. Discovers all covered issuers (initially Nasdaq-listed issuers that have filed at least one
   10-K or 10-Q).
2. Retrieves every electronically available 10-K and 10-Q for those issuers, back to the
   earliest electronic filings in the 1990s.
3. Stores source filings and source datasets in controlled object storage.
4. Extracts authoritative structured financial facts.
5. Calculates normalized and derived financial metrics deterministically.
6. Identifies every actual financial-statement footnote in every filing.
7. Generates one concise standalone summary for every actual footnote.
8. Stores those summaries permanently and immutably (superseded, never overwritten).
9. Renders financial data, charts, filings, and footnote summaries from stored data.
10. Offers an explicit, scoped, metered Deep Analysis action.

### What the product does not do

Real-time market pricing, brokerage integration, trade execution, personalized buy/sell
recommendations, portfolio management, news scraping, social sentiment, earnings-call
transcription, options analytics, non-US filing systems, mobile applications, full valuation
modeling, or SEC form types beyond 10-K and 10-Q. These are non-goals for the MVP. The
architecture must remain extensible toward them without carrying their weight now.

### The three headline requirements

```
EVERY-FOOTNOTE REQUIREMENT
Every actual financial-statement footnote in every processed 10-K and 10-Q must have exactly
one canonical record and exactly one active accepted standard summary. Routine notes may have
shorter summaries. No note may be omitted, merged away, or skipped because a model judged it
immaterial.
```

```
NO-INFERENCE-ON-READ REQUIREMENT
Ordinary dashboard access never invokes a language model. Searching a ticker, opening a filing,
changing a timeframe, expanding a footnote, changing a chart, filtering notes, comparing stored
periods, or opening an existing summary must be served entirely from stored data.
```

```
DEEP-ANALYSIS-IS-SCOPED REQUIREMENT
Deep Analysis is a deliberate, scoped, metered, auditable feature. It is not a general-purpose
financial chatbot. It is bound to one issuer and one authorized corpus for its entire lifetime.
```

---

## 2. Source-of-Truth Hierarchy

When two sources disagree, the lower number wins.

```
1. The filed SEC source document
2. The immutable raw fact extracted from that document
3. The deterministic normalized fact (curated metric definition applied)
4. The deterministic derived metric (formula applied to normalized facts)
5. The stored LLM summary
6. A Deep Analysis interpretation
```

Levels 5 and 6 are never evidence for a financial value. They are navigation and explanation.
A number displayed to a user must always be traceable to level 1 through levels 2 to 4.

---

## 3. Non-Negotiable Invariants

Violating any of these blocks sprint completion.

1. **Never alter a filed value.** `xbrl_fact.value_as_filed` is append-only. Restatements append
   a new row; they never update an old one.
2. **Never merge unrelated issuers by ticker.** Ticker to CIK is temporal. `BBBY` maps to two
   different issuers depending on date.
3. **Never treat a summary as primary evidence.** Material conclusions cite source blocks,
   tables, or facts.
4. **Never call a language model on the ordinary dashboard path.**
5. **Never allow Deep Analysis to escape its authorized scope.** Scope is loaded server-side
   from an immutable session record, never from the request body.
6. **Never mark a filing complete with missing summaries.** Completeness is computed, not
   assumed.
7. **Never overwrite an accepted historical summary version.** Supersede it.
8. **Never store authoritative data only in Redis.**
9. **Never bypass SEC access controls.** All SEC traffic passes the shared rate limiter.
10. **Never silently accept parser uncertainty.** Low confidence routes to review, not to
    publication.

### LLM-SERIALIZATION-INVARIANT

```
No model-visible request content may contain JSON, JSON Lines, XML, XBRL, inline XBRL, HTML,
XHTML, Markdown, Markdown fences, Markdown tables, Markdown headings, Markdown links, Markdown
blockquotes, inline backtick formatting, native JSON tool schemas, or native JSON tool
arguments.

Every model-visible request must be unmarked normalized plain text or one unfenced YAML 1.2
document.

Every structured model response must be one unfenced YAML 1.2 document. Plain-text responses
are permitted only for explicitly unstructured tasks.

AWS SDK transport serialization is outside this boundary, but SDK request objects must never be
copied directly into model-visible content.

All model invocations must pass through the centralized LLM payload compiler and boundary
validator in packages/llm_gateway.

Native model tool calling is prohibited.
```

Violation of this invariant blocks sprint completion. See
`docs/llm/content-boundary.md` for the complete specification and
`docs/adr/ADR-0013-plain-text-or-yaml-llm-boundary.md` for the rationale.

---

## 4. Architecture Rules

### Dependency direction

```
domain
  ^
parsers / facts / metrics / summaries
  ^
application services
  ^
api / worker / scheduler
```

`packages/domain` must not import FastAPI, SQLAlchemy sessions, boto3, Redis clients, S3
clients, or HTTP route objects. Infrastructure adapters may depend on domain interfaces;
the domain never depends on infrastructure.

Circular imports are prohibited. Cross-package private imports (importing a name not exported
through a package's `__init__.py`) are prohibited.

### Data ownership

| Store | Owns | Must never own |
|---|---|---|
| S3 / MinIO | Raw filings, ZIPs, DERA archives, extracted instances, linkbases, table HTML, exact model request and response bodies | Queryable relational state |
| Parquet | Immutable fact lake, versioned serving partitions, source-block text | Mutable state |
| DuckDB | Query engine over immutable Parquet | Storage; concurrent writes |
| PostgreSQL | All control-plane state including the ingest ledger | Financial time series at scale |
| Redis | Cache, rate buckets, locks, single-flight, event fan-out | Anything authoritative |

### Prohibited

Giant route files. Giant worker files. Giant service classes. Catch-all manager classes.
A generic `utils.py`. Provider logic inside domain objects. SQL embedded throughout handlers.
Prompt strings embedded in application code. Reimplemented SEC identity logic. Reimplemented
fiscal logic. Reimplemented validation logic. Reimplemented cost logic.

---

## 5. Code Reuse Rules

Before writing a new function:

1. Search for an existing implementation (`rg` across `packages/`).
2. Identify the correct domain package.
3. Reuse or extend the existing public interface.
4. Do not copy and modify a similar function into another service.
5. Add tests to the shared implementation.
6. Update all callers.
7. Remove obsolete duplicates.

### Single-home rules (enforced by architecture tests)

| Concern | Sole owner |
|---|---|
| CIK normalization | `packages/sec_identity/cik.py` |
| Accession normalization | `packages/sec_identity/accession.py` |
| SEC URL construction | `packages/sec_identity/urls.py` |
| Fiscal period logic | `packages/fiscal/` |
| Model invocation | `packages/llm_gateway/` |
| Bedrock SDK usage | `packages/llm_gateway/providers/bedrock.py` only |
| Cost calculation | `packages/llm_gateway/cost_calculator.py` |
| Scope validation | `packages/deep_analysis/scope.py` |

Reuse must be domain-driven. Do not create abstraction layers that exist only to be layers.

---

## 6. Code Quality Rules

- Type annotations on every public function.
- Docstrings where behavior is non-obvious; not where the signature already says it.
- Defined error behavior. Raise typed errors from the package's `errors.py`; never bare
  `Exception`.
- Stable import paths through package `__init__.py`.
- No hidden global state.

### File and function size

These are review triggers, not lint failures.

- Prefer files under 300 to 500 logical lines.
- Require review before a file exceeds approximately 700 lines.
- Prefer functions under approximately 40 to 60 logical lines.
- Split by responsibility, not by line count.
- Require justification for deeply nested logic.

---

## 7. Commenting Policy

Comment the *why*, never the *what*.

Required comments:

- Financial invariants
- SEC format traps
- Historical-format edge cases
- Rate-limit behavior
- Non-obvious retry logic
- Period-selection logic
- Metric concept priorities
- Amendment handling
- Security boundaries
- Cost protections
- Data-provenance decisions
- Third-party library workarounds

Good:

    # SEC archive folder paths require the issuer CIK as an unpadded integer.
    # The accession prefix can belong to a filing agent and must not be used here.

Bad:

    # Convert CIK to int.

### Markers

Use sparingly, only where they carry information:

```
SEC-INVARIANT:
FINANCIAL-INVARIANT:
SECURITY-INVARIANT:
HISTORICAL-FORMAT:
LLM-MAINTENANCE:
```

### TODO format

Every TODO must state reason, owner or issue reference, intended resolution, and whether it
blocks production. Speculative TODOs are prohibited.

    # TODO(ROADMAP-P5-03, blocks-production=no): role URI grouping is verified on one
    # filing only. Validate across 25 issuers before Phase 5 scale-out.

---

## 8. Financial Data Rules

- **Provenance.** Every displayed number traces to `(accession, taxonomy, concept, context,
  unit, period)`.
- **Versioning.** Metric definitions are version-controlled YAML; changes bump a version and
  require a changelog entry.
- **Hashes.** Every acquired source object records a SHA-256.
- **Period correctness.** Duration-aware filtering is mandatory. Never mix 3, 6, 9, and
  12-month durations in one series.
- **Q4.** No Q4 10-Q exists. Q4 is derived as FY minus Q1 minus Q2 minus Q3, and is labeled as
  derived.
- **Units and scale.** Normalized at ingest and carried explicitly. Never inferred at display.
- **Amendments.** Patches, never replacements. The original filing remains retrievable.
- **Restatements.** Append a new observation; recompute selection separately.
- **Concept priority is a financial-accuracy artifact.** Changing the order of a metric's
  concept list changes reported growth rates. Review it like code.

---

## 9. SEC Access Rules

- A descriptive User-Agent containing a contact email is required on every request.
  Startup fails if it is missing, is a known library default, or lacks an email.
- One global token bucket for `www.sec.gov` and `data.sec.gov`, default 6 requests per second
  sustained, shared across all workers and processes.
- A separate bucket for `efts.sec.gov`, default 1 request per second.
- Throttling appears as HTTP 403 with an HTML body, not 429, and carries no `Retry-After`.
  Classify by response body. On a confirmed rate-threshold block, pause for a full 600 seconds.
  Exponential backoff starting at 1 second extends the block and is prohibited.
- An undeclared-automation 403 is a configuration error. Raise; do not retry.
- Never interpret a directory listing as filing content.
- Record the throttle reference identifier and egress identity on every block.

---

## 10. LLM Rules

- Prompt files live under `prompts/`, versioned, never inline in application code.
- Prompts are `.txt` or `.yaml`. Model-visible `.md` prompt files are prohibited.
- All model access goes through `packages/llm_gateway`.
- Structured output is YAML 1.2 parsed by the hardened safe parser.
- Citations are required for material claims.
- Numeric claims are validated against source tables and facts before publication.
- Every invocation records tokens, cost, latency, prompt version, model identifier, and the
  object-storage URIs of the exact request and response bodies.
- No hidden model fallback. A fallback must be logged and attributed.
- Cost and token budgets are enforced before invocation, not after.

### CIK quoting rule

```
YAML 1.2 core schema parses an unquoted 0000320193 as the integer 320193, silently destroying
the leading zeros that make it a valid CIK. Every CIK, accession number, fiscal period, version
string, and numeric-looking identifier emitted into YAML must be quoted.
```

Verified during Sprint 1. See `docs/llm/content-boundary.md`.

---

## 11. Deep Analysis Rules

- Session scope is immutable after creation.
- The client sends only a session identifier and a message. CIK, tickers, accessions, footnote
  identifiers, scope, model, and budgets are loaded server-side.
- Retrieval is application-orchestrated, or uses the bounded YAML action protocol in
  `docs/deep-analysis/action-protocol.yaml`.
- Native tool calling is prohibited.
- Filing text is untrusted data. Instructions found inside filing content are ignored and
  reported.
- Discussing a company named inside an authorized filing is permitted. Retrieving another
  issuer's data is refused.
- Every turn is checked against turn, token, and cost budgets before invocation.

---

## 12. Security Rules

- Least-privilege IAM with separate roles for API, ingestion, workers, and deployment.
- Secrets in a secrets manager, never in code or environment files committed to the repository.
- Session ownership is verified on every Deep Analysis request.
- Input validation at every boundary; output encoding on render.
- Prompt-injection defenses are tested, not assumed.
- Dependency, secret, and container scanning run in CI.
- Audit records for every model invocation and every scope rejection.

---

## 13. Documentation Rules

After every sprint, update every affected file among:

```
rules.md
roadmap.md
techspecs.md
CHANGELOG.md
docs/sprints/SPRINT-NNNN.md
relevant ADRs
README.md
relevant runbooks
docs/data-dictionary/README.md
prompt documentation
docs/api/openapi.yaml
```

Use only these implementation-status values:

```
IMPLEMENTED
IN_PROGRESS
PLANNED
BLOCKED
DEFERRED
DEPRECATED
```

Never describe planned behavior as implemented. A sprint is incomplete when code and
documentation disagree.

---

## 14. Sprint Protocol

### Before coding

1. Read `rules.md`, `roadmap.md`, `techspecs.md`, `CHANGELOG.md`, the latest sprint record, and
   relevant ADRs.
2. Search existing code for reusable implementations.
3. Identify impacted documentation.
4. Define sprint acceptance criteria.

### During coding

1. Keep changes scoped.
2. Reuse existing libraries.
3. Refactor duplication found in the touched area.
4. Add tests with the code.
5. Update comments for changed invariants.
6. Record architecture decisions as ADRs.
7. Keep migrations reversible.

### After coding

1. Run formatting, linting, type checking.
2. Run unit, integration, architecture, and security tests.
3. Update `techspecs.md`, `roadmap.md`, `CHANGELOG.md`.
4. Write the sprint record reflecting actual completed work.
5. Add or update ADRs.
6. Update README and runbooks.
7. Verify no stale documentation contradicts the code.
8. Record remaining risks and identify the next sprint.

### Definition of done

A sprint is complete only when every acceptance criterion passes, tests pass, documentation
matches implementation, roadmap status is updated, the changelog is updated, the sprint record
is written, required ADRs exist, known limitations are recorded, no duplicate logic was
introduced, no architectural invariant was violated, and rollback implications are documented.

Writing code is not completion.

---

## 15. Exception and ADR Process

Any deviation from these rules requires an ADR recording status, context, decision,
alternatives considered, consequences, migration impact, and revisit conditions.

Accepted ADRs are never silently rewritten. Supersede them with a new ADR that references the
one it replaces.
