# rules.md — Operating Contract for FinTek

STATUS: IMPLEMENTED. Authoritative since Sprint 1 and amended since: sections 15 to 21 by the
alignment review (`275db19`), the AWS identity and secrets invariant in section 3 by `60f3e00`, and
the sealed-migration and single-home records in sections 5 and 8 as the code they describe arrived.
Sections 15 to 20 may be strengthened without an ADR and may never be weakened — section 21.

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

Before running any Git history operation:

10. Read sections 15 through 20 of this file.
11. Stop and obtain explicit user approval for that specific commit, and separately for
    that specific push. No flag, setting, or prior approval substitutes for it.
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
11. **Never run a destructive database test against the application database.** See below.
12. **Never require, hold, or store a long-lived AWS access key.** See below.

### AWS-IDENTITY-AND-SECRETS-INVARIANT

```
Kopexx uses temporary AWS credentials obtained through federation or IAM roles.

Kopexx must never require, solicit, generate, persist, transmit, log, commit, or retrieve
long-lived AWS access keys for ordinary development, CI, deployment, or runtime operation.
```

Prohibited credential material:

```
AWS_ACCESS_KEY_ID                      root access keys
AWS_SECRET_ACCESS_KEY                  IAM-user access keys
AWS_SESSION_TOKEN, manually managed    access-key CSV downloads
credentials in URLs                    credentials in source code
credentials in Terraform variables     credentials in container images
credentials in task definitions        credentials committed, encrypted or plaintext
credentials in .env                    credentials passed as CLI arguments
credentials in PostgreSQL              credentials in Redis
credentials in S3                      AWS access keys in Secrets Manager
```

The application must not accept raw credential values in constructors, configuration objects,
command-line options, API requests, or database records.

**Running with `--dangerously-skip-permissions` does not permit an agent to create, inspect, copy,
export, print, rotate, or store AWS credentials.** That flag suppresses tool prompts. It confers no
authority over identity material, exactly as it confers none over Git.

Required mechanisms, one per context:

```
human development     an approved external federated credential provider, temporary credentials
workloads             IAM roles and temporary credentials
CI and CD             OIDC role assumption
non-AWS secrets       AWS Secrets Manager
credential resolution the AWS SDK default provider chain
authorization         least-privilege IAM policies, explicit trust policies
```

A SERVICE PRINCIPAL IS NOT A CREDENTIAL. It names which AWS service may assume a role, inside a
trust policy. Application code never receives one and never "uses" one.

SECRETS MANAGER IS NOT WHERE AWS KEYS LIVE. It holds secrets IAM cannot replace — production
database passwords, third-party API credentials, webhook secrets, signing material. The role that
reads a secret comes from the workload environment, or the design is circular: embedded AWS
credentials used to fetch AWS credentials.

`.env.example` carries no placeholder for any credential variable. An empty placeholder documents
an unsafe design as the expected one and invites the reader to fill it in.

Enforced by `tests/architecture/test_aws_identity.py`. Full design, including ECS task-role
separation, trust-policy rules, GitHub OIDC scoping, least-privilege Bedrock, and the Terraform
rules, is in `docs/security/aws-identity-and-secrets.md`. This section is the mandatory rule; that
document is the specification.

### TEST-DATABASE-ISOLATION-INVARIANT

```
Destructive database tests must never operate on the configured application database.

Migration upgrade and downgrade tests run ONLY against a dedicated disposable test database, and
must FAIL CLOSED if the test target cannot be proven separate.
```

A destructive test is any test that drops, truncates, or recreates schema objects. Today that is
the migration round-trip and the append-only trigger test; anything added later that runs
`alembic downgrade`, `DROP TABLE`, or `TRUNCATE` is one too.

**Two variables, two purposes, no fallback.**

```
DATABASE_URL        the application database. Holds real loaded facts.
TEST_DATABASE_URL   disposable. Destructive tests drop every table in it.
```

`TEST_DATABASE_URL` must never default to, fall back to, or be derived from `DATABASE_URL`. A
fallback works everywhere, quietly, until the day the application database has something in it.
Absent configuration is a failure, never a silent substitution and never a skip.

**Separateness is proven, not named.** `packages/persistence/engine.assert_disposable` parses both
URLs to a `DatabaseIdentity` — host, port, socket path, database name, and deliberately no
credentials — and refuses equality. String comparison is insufficient: `@localhost/fintek` and
`@127.0.0.1:5432/fintek` are different strings and the same database. Credentials are excluded on
purpose, so a destructive run cannot be authorized merely by connecting as a different user.

**The target must say what it is.** Its database name must carry `test` as a whole
underscore-delimited token, and must not contain `prod`, `production`, `live`, `master`, or
`primary` however else it is decorated.

**The application database is watched.** A session hook records the row counts of `issuer`,
`filing`, and `xbrl_fact` before the suite and compares them after. Any change fails the run,
whether caused by a dropped table or by a fixture row left behind.

WHY THIS IS AN INVARIANT AND NOT A CONVENTION. The migration round-trip test ran against
`DATABASE_URL` for one sprint. `make check` executed `alembic downgrade base`, dropped every
application table, deleted 2,845 loaded facts, and reported green. The suite was not wrong about
any assertion it made; it simply destroyed the thing it was testing beside. Skipping the test when
data is present prevents the deletion and leaves the test unrun, which is the other half of the
same failure.

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
pure logic          sec_identity, fiscal
  ^
parsers / facts / metrics / summaries
  ^
application services
  ^
api / worker / scheduler
```

Pure-logic packages must not import FastAPI, SQLAlchemy sessions, boto3, Redis clients, S3
clients, HTTP clients, or route objects. Infrastructure adapters may depend on pure-logic
interfaces; pure logic never depends on infrastructure.

`tests/architecture/test_architecture.py` enforces this against a named list of pure-logic
packages, and fails if a listed package does not exist. An earlier version scanned a
`packages/domain` directory that contained only a docstring, so it passed without reading a
single import.

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
| Footnote candidate and child-block discovery | `packages/footnote_extractor/` |
| Canonical grouping, exclusion, and completeness | `packages/footnote_canonicalizer/` |
| Table-to-footnote ownership | `packages/footnote_canonicalizer/` |
| Footnote table structure and cell provenance | `packages/table_parser/` |
| Fiscal period logic | `packages/fiscal/` — RESERVED, not yet created |
| Model invocation | `packages/llm_gateway/` |
| Bedrock SDK usage | `packages/llm_gateway/providers/bedrock.py` only — RESERVED, not yet created |
| Cost calculation | `packages/llm_gateway/cost_calculator.py` |
| Scope validation | `packages/deep_analysis/scope.py` — RESERVED, not yet created |

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

    # TODO(ROADMAP-W3-03, blocks-production=no): role URI grouping is verified on one
    # filing only. Validate across 25 issuers before Stage 2 W-3 scale-out.

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
- **An applied migration is sealed.** Once a migration has been applied to any database that is
  not disposable, it is never edited in place, never regenerated, and never deleted. Schema
  changes come as a new revision. Editing an applied migration leaves every database that already
  ran it silently diverged from the file that claims to describe it, and the divergence is
  invisible until something fails much later.

```
SEALED MIGRATIONS

0001_initial            applied to a live PostgreSQL on 2026-08-01 (Sprint 3). SEALED.
                        scripts/generate_initial_migration.py must never be run again: it
                        rewrites this file in place. It exists only as the record of how the
                        revision was first produced, in an environment that had no database to
                        autogenerate against.

0002_table_ownership    applied to the same live PostgreSQL on 2026-08-02 (Sprint 4). SEALED.
                        Adds footnote_table.ownership_kind, ownership_method, and
                        ownership_evidence, two check constraints, and the unresolved-ownership
                        index. A change to table ownership is revision 0003, never an edit here.
```

**The offline reversibility check must span every revision.** `make migration-check` generates
`upgrade base:head` and `downgrade head:base`. Both ranges are derived and neither names a revision
id. Alembic renders only the revisions inside the range it is given, so a hardcoded start silently
stops covering every migration added after it — which is exactly what happened between `0002`
arriving and the Sprint 4 closeout: the target exited 0 while generating none of `0002`'s downgrade
SQL. `tests/unit/test_migrations.py` fails if the recipe names a revision id.

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
CLAUDE.md
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

Section 18 makes this a commit-time gate, not only a post-sprint obligation.

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
9. Prepare the commit-approval report required by section 15 and stop. Do not commit.

### Definition of done

A sprint is complete only when every acceptance criterion passes, tests pass, documentation
matches implementation, roadmap status is updated, the changelog is updated, the sprint record
is written, required ADRs exist, known limitations are recorded, no duplicate logic was
introduced, no architectural invariant was violated, and rollback implications are documented.

Writing code is not completion.

Committing is not part of completion. A sprint reaches technical completion, then stops for
explicit commit approval under section 15. See section 20.

---

## 15. COMMIT-AUTHORIZATION-INVARIANT

```
No LLM agent, automation, script, or development assistant may create, amend, squash, rebase,
merge, cherry-pick, tag, delete, rewrite, or push Git history without first receiving explicit
user authorization for that specific operation.
```

Violation of this invariant is a governance failure, not a process preference.

### The permission flag does not authorize Git operations

`--dangerously-skip-permissions` permits tool execution without repeated operating-system,
shell-command, or file-edit approval prompts. It does **not** authorize:

```
creating a commit          amending a commit         merging
rebasing                   cherry-picking            tagging
pushing                    force-pushing             rewriting history
deleting branches          deleting tags
```

It does not override this rule. The same applies to any pre-approved Git entry in
`.claude/settings.local.json` or an equivalent tool-permission file: a tool-layer permission
suppresses the *prompt*, never the *authorization requirement* defined here.

### Permissions that do not imply Git authorization

None of the following authorizes a commit or a push, individually or in combination:

```
edit files                 run commands              implement a sprint
run tests                  modify documentation      prepare a commit
proceed with development   work autonomously         complete a task
finish a sprint            scaffold the repository   publish the project
prepare files for GitHub
```

### The commit-approval report

Before every proposed commit the agent stops and provides:

```
Repository path
Current branch
Whether the repository has any existing commits
Current HEAD, if one exists
Current remotes
Intended remote, if relevant
git status --short
Files proposed for inclusion
Files intentionally excluded
Summary of changes
Proposed commit subject
Proposed commit body
Commit kind: initial | new ordinary | amendment | merge | squash | cherry-pick | rebase-related
Validation commands executed
Result of every validation command
Checks that could not run
Exact reason for every skipped check
Known warnings
Known unresolved issues
Whether unrelated working-tree changes exist
Whether a push is also being requested
Proposed push remote and branch, when applicable
```

The agent then asks, verbatim:

```
Do you approve creating this commit?
```

The commit may be created only after an unambiguous affirmative answer to that specific
proposed commit.

### Approval does not generalize

Approval for one commit does not authorize any later commit. Approval to create a commit does
not authorize pushing it. Unless the user explicitly approves both together, the agent asks
separately:

```
Do you approve pushing commit <SHA> to <remote>/<branch>?
```

A push may occur only after an unambiguous affirmative answer for that specific push.

### Never treated as authorization

```
silence                              a prior commit approval
a prior push approval                general permission to proceed
general permission to work autonomously
permission to finish a sprint        permission to edit the repository
permission to prepare the project for GitHub
--dangerously-skip-permissions       a pre-approved Git entry in a settings file
```

### First commit

If the repository has no commits, these rules apply unchanged to the first commit. The agent
prepares and validates the proposed initial commit, presents the commit-approval report, and
waits for explicit approval before creating it.

---

## 16. PRE-COMMIT-VALIDATION-INVARIANT

```
No commit may be proposed until every known and applicable repository validation check has
been executed.
```

### Discovering the current suite

The agent discovers the validation suite by inspecting the repository, not by trusting a
remembered list:

```
rules.md          CLAUDE.md         README.md         Makefile
pyproject.toml    package.json      CI workflows      test configuration
sprint records    runbooks          validation scripts
build scripts     container configuration             developer documentation
```

An old hardcoded list must never override newer checks present in the repository.

### Required coverage

Every known applicable form of: unit, integration, contract, smoke, golden, property,
architecture, security, migration, and upgrade/downgrade migration tests; schema validation;
prompt validation; LLM content-boundary validation; regression tests; formatting; linting;
static analysis; type checking; secret scanning; dependency vulnerability scanning;
documentation validation; documentation-link validation; generated-file consistency checks;
build validation; frontend and backend build checks; container build or validation;
CI-equivalent checks; and any other repository-defined validation.

During development the agent may run focused subsets for speed. **A focused subset never
replaces the complete pre-commit suite.** Before proposing a commit, the agent runs the
complete known applicable suite.

### Blocking conditions

A commit may not be proposed or created when any of the following holds:

```
a required test fails                  formatting fails
linting fails                          type checking fails
static analysis fails                  a smoke test fails
a migration cannot upgrade as required a migration cannot downgrade as required
schema validation fails                prompt validation fails
LLM boundary validation fails          secret scanning finds unresolved material
dependency scanning finds an unresolved blocking issue
documentation contradicts implementation
generated artifacts are stale          a build fails
the working tree contains unexplained changes
a required check was silently skipped
the validation environment is broken and the result is unknown
```

### Gates may not be weakened to pass

Tests and validation gates may not be disabled, deleted, weakened, marked skipped, excluded
from coverage, bypassed, or rewritten solely to make a commit pass.

Correcting a demonstrably incorrect test or rule is permitted. The commit report must then
disclose: the original test or rule, why it was incorrect, what changed, why the replacement
still protects the intended behavior, and which tests validate the correction.

Never use any of the following to bypass a validation failure without separate explicit
authorization:

```
--no-verify              disabled Git hooks        test exclusions
coverage exclusions      changed CI rules          suppressed errors
ignored type failures    skipped migrations        disabled scanners
reduced quality thresholds
```

### When a check genuinely cannot run

If a required check cannot run because of a real external dependency or environment
limitation, the agent does **not** create the commit automatically. It reports the exact
command, the exact failure or blocker, which behavior remains unverified, and the risk of
committing anyway. It then asks whether to resolve the blocker, defer the commit, or approve a
one-commit exception.

An exception applies only to the exact proposed commit. A material exception is recorded in
the commit report, the current sprint record, `CHANGELOG.md` when appropriate, and the relevant
risk, issue, or known-limitation documentation.

---

## 17. TEST-DISCOVERY-INVARIANT

Before proposing a commit, compare the locally executed suite against every applicable CI
workflow. The local pre-commit suite must include every applicable check CI is expected to run.

When CI contains a check that cannot be reproduced locally, the agent must disclose the check,
explain why it cannot run locally, and state that the proposed commit is **not yet fully
CI-validated**. It must not describe such a commit as fully validated.

When a new test, linter, scanner, schema check, build step, migration check, or validation
command is introduced, update all applicable documentation and automation:

```
rules.md        README.md       techspecs.md        relevant runbooks
CI configuration                sprint records      developer-command documentation
```

Future agents discover the current suite from repository sources, never from an outdated
static list carried forward in conversation.

---

## 18. DOCUMENTATION-SYNCHRONIZATION-INVARIANT

Before proposing a commit, verify that every affected project-memory document accurately
reflects the current implementation. This extends section 13 with a commit-time gate.

Review and update when applicable:

```
rules.md            roadmap.md          techspecs.md        CHANGELOG.md
current sprint record                   relevant ADRs       README.md
runbooks            data dictionary     prompt documentation
API documentation   migration documentation                 deployment documentation
testing documentation                   operational documentation
```

A commit may not be proposed while documentation:

```
describes planned behavior as implemented
describes implemented behavior as merely planned
contains stale test counts
contains stale file paths
references nonexistent modules as implemented
contains unresolved references to prior chat messages
contradicts code or schema behavior
omits a material architecture or behavior change
```

Historical sprint records and historical changelog entries remain historically accurate. They
are not rewritten merely because current totals have changed.

---

## 19. GIT-SAFETY-INVARIANT

### Inspection required before any proposed commit

```
1.  Inspect the full working tree.
2.  Review staged changes.
3.  Review unstaged changes.
4.  Review untracked files.
5.  Review the complete staged diff.
6.  Review the staged filename list.
7.  Scan for secrets.
8.  Scan for inappropriate generated data.
9.  Separate unrelated changes.
10. Confirm the intended branch.
11. Confirm the intended remote, if any.
12. Confirm that no credentials, runtime storage, downloaded archives, model captures, local
    environment files, or generated datasets are being included unintentionally.
```

### Never commit

```
.env                    credentials             API tokens
AWS credentials         GitHub tokens           private keys
certificates            local database contents MinIO contents
Redis data              downloaded SEC archives mirrored DERA packages
model request or response captures              runtime logs
coverage output         virtual environments    cache directories
build output            editor state            local machine configuration
```

A file is not safe merely because it is already tracked. Verify, do not assume.

### Operations requiring explicit authorization for the exact operation

```
git commit              git commit --amend      git merge
git rebase              git cherry-pick         git tag
git push                git push --force        git push --force-with-lease
history rewriting       branch deletion         remote branch deletion
tag deletion            remote tag deletion
```

Force-push and history-rewriting operations additionally require a separate warning, a
description of what history will change, a description of who or what may be affected, and
explicit approval naming that operation.

```
Ordinary push approval is never force-push approval.
```

---

## 20. Sprint Completion and Git

A sprint may be technically complete before any commit exists. Completion of the work and
recording of the work are separate events with separate authorizations.

When sprint work is technically complete:

```
1.  Update all required documentation.
2.  Run the complete validation suite.
3.  Inspect the complete Git working state.
4.  Prepare the proposed commit report.
5.  STOP.
6.  Ask for explicit commit approval.
7.  Create the commit only after approval.
8.  Report the resulting commit SHA.
9.  Ask separately for push approval, unless commit and push were explicitly approved together.
10. Push only after approval.
11. Record the commit SHA and push result in the sprint record when appropriate.
```

Never report any of the following as done before it has actually occurred:

```
committed    tagged    pushed    published to GitHub    merged    released
```

---

## 21. Exception and ADR Process

Any deviation from these rules requires an ADR recording status, context, decision,
alternatives considered, consequences, migration impact, and revisit conditions.

Accepted ADRs are never silently rewritten. Supersede them with a new ADR that references the
one it replaces.

Sections 15 through 20 are exempt from this process in one direction only: they may be
strengthened without an ADR, but may not be weakened or removed by any agent under any
circumstance.
