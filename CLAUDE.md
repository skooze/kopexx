# CLAUDE.md — Agent Operating Instructions for FinTek

This file is loaded automatically at the start of every Claude Code session in this repository.
It is a pointer to the authoritative rules, not a replacement for them.

---

## Read this first

**Before planning or modifying this repository, read `rules.md`.**

`rules.md` is the operating contract. This repository — not conversation history — is the
durable project memory. No chat log, ticket, or prior session is authoritative.

Then read, in order:

```
rules.md                                 the operating contract, read in full
roadmap.md                               what is built, what is planned, and in what order
techspecs.md                             what the code actually does today
CHANGELOG.md                             what changed and when
docs/sprints/SPRINT-NNNN.md              the latest sprint record
docs/architecture/product-definition.md  what the product is, authoritatively
docs/adr/                                the decisions that constrain new work
```

Search `packages/` for an existing implementation before writing a new one.

---

## Git authorization is mandatory and non-negotiable

**The commit-authorization, push-authorization, pre-commit-validation, test-discovery,
documentation-synchronization, Git-safety and product-direction invariants in `rules.md`
sections 15 through 21
are mandatory.**

**Running Claude Code with `--dangerously-skip-permissions` does not authorize any commit,
amendment, merge, rebase, cherry-pick, tag, push, force-push, history rewrite, branch deletion,
or tag deletion.**

**Always stop and request explicit user approval before each commit and each push.**

That flag suppresses repeated operating-system, shell-command, and file-edit prompts. It grants
no Git authority whatsoever. Neither does a pre-approved Git entry in
`.claude/settings.local.json`: a tool-layer permission suppresses the prompt, never the
authorization requirement.

### What is never authorization

```
silence                                  a prior commit approval
a prior push approval                    general permission to proceed
permission to work autonomously          permission to finish a sprint
permission to edit the repository        permission to prepare the project for GitHub
--dangerously-skip-permissions           a pre-approved Git entry in a settings file
```

### Before any commit

Run the complete applicable validation suite, verify documentation matches implementation,
inspect the full working tree, then present the commit-approval report specified in `rules.md`
section 15 and ask:

```
Do you approve creating this commit?
```

Approval for one commit authorizes only that commit. Approval to commit is never approval to
push. Ask separately:

```
Do you approve pushing commit <SHA> to <remote>/<branch>?
```

Ordinary push approval is never force-push approval.

A sprint may be technically complete before any commit exists. Never report work as committed,
tagged, pushed, published, merged, or released before it has actually happened.

---

## The four product properties

Every change is measured against these. They come from the user and are not negotiable.

```
EVERY human-readable source range in every processed filing is represented in the accepted parsed
artifact or explicitly marked unresolved. Every footnote the accepted parse identifies stays an
independent node and an independent required summary target. Nothing is merged away. Uncertainty
produces PARTIAL or REVIEW_REQUIRED, never a false complete.

THE SELECTED PARSING MODEL determines the filing's native semantic structure. The backend performs
transport handling and then PROVES coverage, citations and numbers against the preserved bytes.
Backend code never decides what any part of a filing means.

ORDINARY dashboard access never invokes a language model.

DEEP ANALYSIS is a deliberate, scoped, metered, auditable feature bound to one issuer and
timeframe. It is not a general-purpose financial chatbot.
```

Four models, chosen independently by the user for every job: a PARSING model, an IMAGE model, a
SUMMARY model, and an ANALYSIS/CHAT model. No role inherits another's model. No silent fallback.

Approved beta candidates: GPT OSS 120B, NVIDIA Nemotron 3 Super 120B, Qwen3 235B A22B, Llama 4
Maverick, Qwen3 VL 235B. **All five were mapped, reached and priced on 2026-08-03 (Phase 1).** The
verified identifiers, regions, modalities, limits and prices live in exactly one place —
`docs/llm/bedrock-capability-snapshot.yaml` — and `packages/model_catalog` is the only code that
reads them. Do not copy a model fact anywhere else; a capability recorded twice drifts.

**Reachable is not benchmarked, and benchmarked is not accurate.** Phase 1's seven one-word
invocations proved transport. Phase 2 measured real token counts, real cost and real format
behaviour over three filings — and measured NOTHING about whether a parse is correct. Validation
proves a citation resolves in the preserved bytes and a reported number occurs there; correctness
is a human judgement made in the review UI. Repeat-run variability was not measured either: no
filing was parsed twice by the same model, because a rerun is billable and none was authorized.

**One issuer is a fixture, never a specification.** The architecture is derived from a measured
corpus of 112 issuers and 613 filings across six transport eras — dated Phase 1 evidence, not a
permanent constant, and not from Apple. Two earlier versions of this file asserted a product scope
that had never been measured — first "the footnotes are the product", then a complete-filing
deterministic parser. Both were wrong for the same reason. See
`docs/adr/ADR-0016-corpus-first-model-first-architecture.md`.

## Read rules.md section 21 before changing product direction

`rules.md` section 21, PRODUCT-DIRECTION-INVARIANT, is seventeen mandatory rules written after the
repository drifted away from the stated product twice. It may be strengthened, never weakened.

The two that catch the most:

```
THE BACKEND DOES NOT BECOME THE AUTHORITATIVE SEMANTIC PARSER.
NO UNIVERSAL FILING TAXONOMY WITHOUT EXPLICIT USER APPROVAL.
```

Both drifts passed every gate the repository had at the time. The tests were green and the
measurements were real — they were measurements of Apple.

## Intact source only, on every invocation

`INTACT_SOURCE_ONLY` is the current authorized input mode. The complete relevant human-readable
source set goes to the model intact, or the filing/model pairing is INCOMPATIBLE and is refused
with an explanation.

```
no truncation                    no semantic slicing
no automatic model substitution  no silent fallback
no mechanical multipart INPUT    no visible-content projection
```

**MODEL-DIRECTED MULTIPART OUTPUT WAS APPROVED ON 2026-08-03 AND IS IMPLEMENTED.** One logical
filing parse may use many provider responses: a model-created plan, one call per part the model
names, model-created subparts, model-created reconciliation, and mechanical backend assembly. The
INPUT rule is unchanged — every one of those calls receives the complete compatible source set
intact, in filed order, hash-verified, including the complete image set for a multimodal parser.

Mechanical multipart INPUT, in which backend code divides a filing and sends the pieces, and
visible-content projection remain UNAPPROVED research options requiring separate user approval. A
lower token cost is not authorization for either. See ADR-0020 and `rules.md` section 21 rules 6,
7, 18, 19 and 20.

## Blind continuation is prohibited

```
No request may ask a model to continue, resume or carry on an interrupted response, and no code
may concatenate response fragments into one document.
```

A response that stops at the provider's output limit is preserved exactly, marked TRUNCATED, and
treated as EVIDENCE. Its partial content never reaches an accepted artifact. The unfinished work is
picked up by a model-directed REPLANNING call that receives the intact source again and covers the
WHOLE original part.

Enforced structurally: `TaskState.TRUNCATED` has no outgoing transition, and an architecture test
scans every evaluated string in `packages/` and every prompt file for continuation wording.

## Complete content is an invariant; deterministic parsing is not

`rules.md` section 3, COMPLETE-CONTENT-INVARIANT, is mandatory. Every human-readable source range
is represented in the accepted parsed artifact or explicitly unresolved, and coverage is proved by
the backend against the source bytes — never asserted by the model that produced the parse.

**Interpretation is the model's; proof is the backend's.** Do not write a semantic parser. Do not
decide in code what is MD&A, a risk factor, a footnote, an exhibit or a signature block.

---

## Kopexx never manages raw AWS credentials

**Kopexx never creates, accepts, manages, persists, logs, or transports raw AWS credentials.** AWS
SDKs resolve and refresh temporary credentials through an external federated provider, a workload
role, or an OIDC-assumed role. It must never require, solicit, generate, persist, transmit, log,
commit, or retrieve a long-lived AWS access key — not for development, not for CI, not for
deployment, not at runtime.

**`--dangerously-skip-permissions` does not permit creating, inspecting, copying, exporting,
printing, rotating, or storing AWS credentials.** That flag suppresses tool prompts. It confers no
authority over identity material, exactly as it confers none over Git.

Never paste a credential into a prompt, a shell command, a log, an issue, or documentation.

The mandatory rule is `rules.md` section 3, AWS-IDENTITY-AND-SECRETS-INVARIANT. The full design —
local federation, ECS task roles, trust policies, GitHub OIDC, Secrets Manager, least-privilege
Bedrock, Terraform — is `docs/security/aws-identity-and-secrets.md`. Read it before any work that
touches AWS.

---

## The LLM content boundary

```
Model-visible SYNTHETIC content is ONLY unmarked normalized plain text, or exactly one unfenced
YAML 1.2 document. JSON, JSON Lines, JSON Schema, XML, XBRL, inline XBRL, HTML, XHTML, Markdown,
and native tool schemas or arguments are prohibited in both directions. Native tool calling is
prohibited.

ORIGINAL-SOURCE EXCEPTION. A preserved SEC artifact is sent INTACT in whatever syntax SEC
published — plain text, SGML, HTML, XML, XBRL, inline XBRL, PDF, image. It is admitted by
PROVENANCE, not by syntax: the bytes must be identical to a preserved artifact whose SHA-256 is
recorded. Never rewrite an original artifact into YAML to satisfy the synthetic-content rule, and
never semantically slice or reconstruct it. The exception is one-directional: no model RESPONSE
may use it.
```

All model access goes through `packages/llm_gateway`. Browser-facing JSON in `docs/api/` is
outside this boundary — a browser is not a model. Provider-required JSON is permitted only as the
API transport envelope. Full specification in `docs/llm/content-boundary.md` and ADR-0013.

**No request or response contract is declared anywhere, and none may be invented.** The gateway
compiles an arbitrary mapping and validates its format; that is everything that can honestly be
asserted before a model has been reached. The footnote-shaped request contract that used to live
in `payload_compiler.py` was deleted with the parser that produced it.

---

## Where the project is

Sprints 1 and 2 built the foundation: SEC identity, HTTP client with rate limiting, object storage,
the LLM content boundary, and the complete DERA mirror. Sprint 3 retrieved the first filings.
Sprint 4 turned the footnote thesis into production code — 43 canonical footnotes across four Apple
filings, 117 of 117 child blocks attached, zero orphans. **That measurement stands as history. The
implementation is DELETED**, along with the application database, its migrations, and the DERA
mirror and fact loader. Git history is the archive. ADR-0017 says why, once.

The project is tracked in PHASES, not sprints. `roadmap.md` is authoritative.

```
Phase 0    Representative filing corpus                  COMPLETE
Phase 0.5  Repository cleanup and corpus reverification  COMPLETE
Phase 1    Secure AWS and model-access verification      COMPLETE 2026-08-03
Phase 2    Parser experiments AND the review UI, TOGETHER   COMPLETE 2026-08-03
Phase 2.1  Model-directed multipart parsing                 IMPLEMENTED AND PUBLISHED
                                                            2026-08-03; the five-model proof
                                                            is BLOCKED on an expired AWS SSO
                                                            session, not on a defect
Phase 2.5  BREADTH across all 22 substantive form strings   BLOCKED on a user decision about
                                                            which parser and prompt version advances
Phase 3-8  optional model stages, persistence and the approval gate, background population,
           beta UI, Deep Dive, breadth                   NOT STARTED
```

**FILINGS HAVE NOW BEEN PARSED BY REAL MODELS.** A parser-only orchestration path, a durable
evaluation store, a Bedrock runtime adapter, the four-role router, hash-locked prompt versions,
generic output validation and a working parser-review UI all exist and run. `make review` starts
the UI on `127.0.0.1`. Measured results, per-filing cost and the comparison are in
`docs/sprints/PHASE-0002-parser-experiments-and-review-ui.md`; the decision record is ADR-0019.

**STILL TRUE AFTER PHASE 2, AND NOT SMALL. NOTHING IS DEPLOYED. NO APPLICATION DATABASE EXISTS. NO
REDIS EXISTS. NO SUMMARY, IMAGE OR CHAT ARTIFACT EXISTS** — Phase 2 ran the PARSING stage only and
the orchestrator raises `StageNotAuthorizedError` rather than running another. An APPROVED artifact
records a judgement and activates no reuse: no search consults the evaluation store and no cache is
populated. Breadth across the 22 form strings has NOT been attempted.

**Cost figures are now measured for three filings and only three.** Three filings is not a
denominator; nothing in `docs/llm/cost-model.md` extrapolates to a corpus, and R-21 — whether any
candidate accepts a materially sized modern filing intact — is untouched, because by construction
the shared benchmark could only contain filings that fit.

**ONLY THE PARSING MODEL IS REQUIRED.** A parser-only run is a complete, valid run and is the first
functional workflow built. The image, summary and analysis/chat selectors may be left blank, and
the orchestrator runs only the stages the user selected — never silently selecting a blank model,
substituting another, adding a stage, or skipping a selected one.

**The parser-review UI is built WITH the first model experiments, not after them.** A parsed
artifact cannot be evaluated without seeing it beside the filing it came from.

Read `roadmap.md`, ADR-0016 and ADR-0017 before proposing anything that widens or narrows scope.

### What Phase 2 added, so you do not rebuild it

```
packages/evaluation_store   packages/source_transport   packages/coverage_validation
packages/prompt_registry    packages/orchestrator       packages/review_api
packages/review_web         packages/filing_acquisition/documents.py
packages/model_catalog/routing.py    packages/llm_gateway/providers/bedrock.py
prompts/parser/             tests/integration/          make review
```

### What Phase 2.1 added, so you do not rebuild it

```
packages/multipart                        the envelopes, generic validation, mechanical assembly
evaluation_store/tasks.py                 durable task records
evaluation_store/queue_states.py          11 task types, 14 states, a THIRD state machine
orchestrator/multipart_service.py         the scheduler and executor
orchestrator/briefs.py                    the synthetic YAML brief for one invocation
orchestrator/sizing.py                    the cap, the target, the headroom between them
review_web/multipart_view.py              hierarchy, per-call review, assembled index
prompts/parser/parser-multipart-*         six immutable families
docs/llm/prompt-caching-investigation.md  investigated; available for NO candidate
```

**THE FIVE-MODEL PROOF IS INCOMPLETE AND THE BLOCKER IS EXTERNAL.** One candidate produced a valid
24-part plan and four completed parts resolving 65 of 66 references; the AWS IAM Identity Center
session then expired mid-run. `aws sso login` on the host unblocks it. Nothing was retried,
substituted or lost. See `docs/sprints/PHASE-0201-model-directed-multipart-parsing.md` section 7.

**NO PARSER HAS BEEN SELECTED, RANKED OR PROMOTED**, and the single-response protocol remains
runnable so the two can be compared. Do not choose one.

**The review UI uses the standard library and adds no dependency.** No web framework, no ASGI
server, no bundler, no npm, no build step. `boto3` is an OPTIONAL extra, which is what makes
"ordinary CI is AWS-free" mean the SDK is not installed at all. Do not add any of them without
reading ADR-0019 first.

### What no longer exists, so you do not go looking for it

```
packages/footnote_extractor      packages/footnote_canonicalizer   packages/table_parser
packages/persistence             packages/dera_notes               migrations/  alembic.ini
scripts/                         metric_definitions/               artifacts/
docs/footnotes/                  prompts/footnote-summary/         docker-compose.yml
packages/filing_acquisition/inventory.py   — the accession document classifier
make migration-check  make db-*  make test-integration   — the targets that drove them
sqlalchemy  alembic  psycopg  pydantic                   — the dependencies they needed
```

Do not recreate any of it, in `packages/` or anywhere else. Do not park deleted code in `oracle/`,
`legacy/`, `deprecated/`, `benchmark/` or `tests/support/`. CI fails if any of the five deleted
packages imports, and an architecture test fails if a filing-form literal returns to runtime source.

Packages are created when their code arrives. Reserved names live in `techspecs.md` section 2
with a status column, and an architecture test rejects empty stub packages.

## Validation suite

Discover the current suite from the repository — `Makefile`, `pyproject.toml`,
`.github/workflows/ci.yml` — rather than from this list, which can go stale.

**The Makefile is the single definition of the suite. CI invokes the same targets**, so local
validation and GitHub Actions cannot drift apart. Never write a validation command directly into
the workflow.

```
make check           fmt-check, lint, typecheck, test
make coverage        tests with coverage and the 85% gate
make test-no-skips   the suite, failing if ANY test skips
```

**The suite has no environmental precondition at all** — no database, no network, no credentials.
That is why `test-no-skips` is the same suite as `test` and why a skip has no legitimate cause.
`make migration-check` and every `make db-*` target went with the database.

Paths, defined once in the Makefile:

```
PY_PATHS     packages tests     format and lint
MYPY_PATHS   packages           type check
```

`tests` is excluded from type checking so a test may use the loose idioms tests use without
weakening the check on the source that matters.

Not covered by `make check`, run before proposing a commit:

```
pip-audit --skip-editable                 dependency vulnerabilities, enforcing
gitleaks git . --log-opts="--all --full-history" --redact --exit-code 1
gitleaks dir . --redact --exit-code 1
```

**Gitleaks is a pinned CLI binary (8.30.1, checksum-verified), not a GitHub Action**, so the same
command runs locally and in CI. Install it from the official release if you need to reproduce the
security job. It scans all reachable commits plus the working tree; it does not use the push
event's commit range, which cannot resolve on a first push.

---

## Truthfulness

Do not claim a file exists unless you created or verified it. Do not claim a test passed unless
you ran it. Do not claim a command succeeded unless you observed its result. Report skipped
checks and the exact reason they were skipped.
