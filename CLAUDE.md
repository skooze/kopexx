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
rules.md                      the operating contract, read in full
roadmap.md                    what is built, what is planned, and in what order
techspecs.md                  what the code actually does today
CHANGELOG.md                  what changed and when
docs/sprints/SPRINT-NNNN.md   the latest sprint record
docs/adr/                     the decisions that constrain new work
```

Search `packages/` for an existing implementation before writing a new one.

---

## Git authorization is mandatory and non-negotiable

**The commit-authorization, push-authorization, pre-commit-validation, test-discovery,
documentation-synchronization, and Git-safety invariants in `rules.md` sections 15 through 20
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

## The three product properties

Every change is measured against these. They come from the user and are not negotiable.

```
EVERY actual financial-statement footnote in every processed 10-K and 10-Q has one canonical
record and one active accepted summary. Not selective, not merged, not model-chosen.

ORDINARY dashboard access never invokes a language model.

DEEP ANALYSIS is a deliberate, scoped, metered, auditable feature bound to one issuer. It is
not a general-purpose financial chatbot.
```

The insight the product is built around: a 10-K may run a hundred pages, of which only a page
or two is the financial statements. The rest is footnotes explaining *why* the company did what
it did. **The footnotes are the product.**

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

Sprints 1 and 2 built the foundation: SEC identity, HTTP client with rate limiting, object
storage, the LLM content boundary, the 24-table schema, and the complete DERA mirror.

**No SEC filing has been retrieved yet.** Sprints 3 to 7 are the vertical thread — one issuer
through every layer, proving all fifteen MVP criteria — before any breadth work. Read
`roadmap.md` and ADR-0015 before proposing anything that widens scope.

Sprint 5 is the go/no-go: it measures real cost per footnote for the first time. Do not treat
any cost figure as known before then; every parameter in `docs/llm/cost-model.md` is a
placeholder.

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
make migration-check  offline alembic upgrade and downgrade generation
```

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
