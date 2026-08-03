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
Maverick, Qwen3 VL 235B. **None is currently configured or accessible.** Model IDs, regions,
modalities, limits and prices are discovered live in Phase 1.5, which has not run. Never claim a
model is configured, reachable, benchmarked, or priced.

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

## Intact source only

`INTACT_SOURCE_ONLY` is the current authorized input mode. The complete relevant human-readable
source set goes to the model intact in one invocation, or the filing/model pairing is INCOMPATIBLE
and is refused with an explanation.

```
no truncation                    no semantic slicing
no automatic model substitution  no silent fallback
no mechanical multipart          no visible-content projection
```

Projection and multipart are unapproved research options requiring separate user approval. A lower
token cost is not authorization.

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
Model-visible content is ONLY unmarked normalized plain text, or exactly one unfenced YAML 1.2
document. JSON, JSON Lines, JSON Schema, XML, XBRL, inline XBRL, HTML, XHTML, Markdown, and
native tool schemas or arguments are prohibited in both directions. Native tool calling is
prohibited.
```

All model access goes through `packages/llm_gateway`. Browser-facing JSON in `docs/api/` is
outside this boundary — a browser is not a model. Full specification in
`docs/llm/content-boundary.md` and ADR-0013.

---

## Where the project is

Sprints 1 and 2 built the foundation: SEC identity, HTTP client with rate limiting, object storage,
the LLM content boundary, and the complete DERA mirror. Sprint 3 retrieved the first filings.
Sprint 4 turned the footnote thesis into production code — 43 canonical footnotes across four Apple
filings, 117 of 117 child blocks attached, zero orphans. **That measurement stands. Its role does
not: it is now a validation oracle, never the product.**

The project is tracked in PHASES, not sprints. `roadmap.md` is authoritative.

```
Phase 1    Representative filing corpus            COMPLETE
Phase 1.5  Intact-source compatibility             OPEN — blocks Phase 2
Phase 2    Model contract and parsing experiments  BLOCKED pending user authorization and live
                                                   Bedrock capability discovery
Phase 3-8  orchestrator, images, summaries, UI, chat, persistence   NOT STARTED
```

**NO MODEL HAS EVER BEEN INVOKED. AWS IS NOT CONFIGURED. NOTHING IS DEPLOYED. NO SUMMARY EXISTS.**
Do not treat any cost figure as known: every parameter in `docs/llm/cost-model.md` is a
placeholder, and the first real measurement is Phase 2.

Commit 1 — preservation, reusable infrastructure and test-database isolation — is committed,
pushed and CI-green. Commit 2 is the architecture and governance realignment. Commit 3, which
withdraws the rejected parser implementation, has not begun; the implementation files are still
present and still pass their tests, and that is deliberate.

Read `roadmap.md`, ADR-0015 and ADR-0016 before proposing anything that widens or narrows scope.

Packages are created when their code arrives. Reserved names live in `techspecs.md` section 2
with a status column, and an architecture test rejects empty stub packages.

## Validation suite

Discover the current suite from the repository — `Makefile`, `pyproject.toml`,
`.github/workflows/ci.yml` — rather than from this list, which can go stale.

**The Makefile is the single definition of the suite. CI invokes the same targets**, so local
validation and GitHub Actions cannot drift apart. Never write a validation command directly into
the workflow.

```
make check            fmt-check, lint, typecheck, test, migration-check
make coverage         tests with coverage and the 85% gate
make migration-check  offline alembic generation, base:head and head:base
```

Both migration ranges are derived and neither names a revision id. A hardcoded start silently
stops covering every migration added after it; a test reads the recipe out of the Makefile to
prevent that returning.

Paths, defined once in the Makefile:

```
PY_PATHS     packages tests scripts migrations     format and lint
MYPY_PATHS   packages scripts migrations           type check
```

`tests` is excluded from type checking on purpose: it exercises SQLAlchemy internals where
`Model.__table__` is typed as `FromClause`, and silencing that with blanket ignores would weaken
the check for the source that matters.

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
