# AWS Identity and Secret Management

IMPLEMENTATION STATUS: this policy is IMPLEMENTED GOVERNANCE and is enforced by tests today.
The Bedrock provider adapter it constrains was PLANNED when that sentence was first written; it is
IMPLEMENTED as of 2026-08-03, in Phase 2, together with a browser-facing review application this
document had not previously had to consider. See "Phase 2, 2026-08-03" below. Workload identity on
AWS, trust policies, deployment roles, Secrets Manager use and Terraform remain PLANNED; nothing is
deployed.

**FIRST EXERCISED 2026-08-03, IN PHASE 1.** AWS was reached for the first time — control-plane
discovery and seven minimal model invocations — under temporary IAM Identity Center credentials
resolved by the AWS CLI's own provider chain. No static key exists, none was created, nothing under
the credential cache was opened, and no credential value appears in any tracked file, log or
evidence artifact. The account identifier, the local profile name and the role session stayed on the
host, out of Git, per the Configuration section below. Procedure:
`../runbooks/bedrock-capability-discovery.md`.

AUTHORITATIVE FOR: how Kopexx resolves AWS identity, and what may hold a secret.
MANDATORY RULE: `rules.md` section 3, AWS-IDENTITY-AND-SECRETS-INVARIANT.

---

## The principle

**Kopexx never creates, accepts, manages, persists, logs, or transports raw AWS credentials. AWS
SDKs resolve and refresh temporary credentials through an external federated provider, workload
role, or OIDC-assumed role.**

The distinction is worth stating precisely, because a looser version of it is wrong. An SDK
necessarily holds temporary credential material in process memory while it signs a request — that
is what signing is. What Kopexx application code must never do is *manage* those values: obtain
them itself, accept them as parameters, copy them out of the provider chain, write them anywhere,
or move them between processes.

Every AWS call this project will ever make is authorized by a temporary credential that something
else issued and something else refreshes: a federated login on a workstation, an IAM role attached
to a running workload, or a role assumed through OpenID Connect in CI. The application's job is to
construct a client and let the SDK resolve identity. It has no other job in this area.

The reason is not that long-lived keys are inconvenient. It is that a long-lived key is a secret
that must be created, transported, stored, rotated, revoked, and scanned for — six operations, each
of which can fail silently, forever, in a public repository. A temporary credential eliminates all
six by expiring on its own.

This is written before any AWS integration exists on purpose. A credential convention is nearly
impossible to remove once code depends on it.

---

## What is prohibited

No component of Kopexx may require, solicit, generate, persist, transmit, log, commit, or retrieve
long-lived AWS access keys for development, CI, deployment, or runtime.

```
AWS_ACCESS_KEY_ID                      root access keys
AWS_SECRET_ACCESS_KEY                  IAM-user access keys
AWS_SESSION_TOKEN, manually managed    access-key CSV downloads
credentials in URLs                    credentials in source code
credentials in Terraform variables     credentials in container images
credentials in task definitions        credentials committed, encrypted or not
credentials in .env                    credentials as CLI arguments
credentials in PostgreSQL              credentials in Redis
credentials in S3                      AWS access keys in Secrets Manager
```

The application must not accept raw credential values in constructors, configuration objects,
command-line options, API requests, or database records.

**Running an agent with `--dangerously-skip-permissions` does not permit it to create, inspect,
copy, export, print, rotate, or store AWS credentials.** That flag suppresses tool prompts. It
confers no authority over identity material, exactly as it confers none over Git.

---

## Terminology

These four are routinely conflated, and conflating them is how a service principal ends up being
treated as something a program can hold.

**IAM role.** An identity assumed by a human, a workload, an AWS service, or a federated
principal. Assuming it yields temporary credentials.

**AWS service principal.** An identifier such as an ECS or Lambda service principal, used *inside
an IAM role trust policy* to say which service may assume that role. **It is not a credential and
is never supplied to application code.** Code that tries to "use a service principal" is a
misunderstanding, not an implementation.

**Workload identity.** The IAM role a running workload receives: an ECS task role, a Lambda
execution role, an EC2 instance profile, a role assumed through web identity, or a role obtained
through IAM Roles Anywhere.

**Secrets Manager.** Storage for application secrets that IAM authorization cannot replace —
production database passwords, third-party API credentials, webhook secrets, private signing
material. **It is not where Kopexx's AWS access keys live, because Kopexx has none.**

---

## Human local development

1. Authenticate through an **approved external federated credential provider** that issues
   temporary credentials.
2. Prefer an AWS CLI or SDK profile managed outside this repository.
3. Non-secret configuration may be set: `AWS_PROFILE`, `AWS_REGION`, and optionally a role ARN.
4. Raw credential environment variables are never required.
5. Do not run `aws configure` to mint long-lived IAM-user keys.
6. Do not copy temporary keys from a portal into `.env`.
7. Do not paste credentials into a coding agent, a shell command, a prompt, a log, an issue, or
   documentation.
8. Let the SDK use its standard credential provider chain.
9. When no valid temporary identity is available, fail with a clear authentication error.
10. Never silently fall back to a different account or profile. A wrong-account success is worse
    than a clean failure, because the bill and the audit trail land somewhere nobody is looking.

### Why the provider is described abstractly

This repository is public. Where a developer's host offers an internal AWS access system, it is
treated as **an approved external federated credential provider** and nothing more. The repository
does not name it, document its URLs, role names, account aliases, commands, or procedures, and does
not depend on internal-only libraries or endpoints.

That is not only a disclosure concern. Naming one organisation's login system in tracked
documentation encodes an assumption that everyone working on the project belongs to that
organisation, and the project stops being buildable by anyone else. **Kopexx must remain usable
with standard public AWS authentication mechanisms.**

Host-specific setup notes belong outside Git — under the ignored `var/local-tools/`, or in personal
documentation.

---

## Bedrock provider requirements — Phase 2

**WRITTEN 2026-08-03, IN PHASE 2.** The adapter now exists. Every requirement below is met, and the
next section records how each one is held rather than merely asserted. The list stays in the
imperative and stays unchanged: it binds the next adapter as strictly as it bound this one, and a
requirement rewritten into the past tense stops constraining anything.

The adapter at `packages/llm_gateway/providers/bedrock.py` must:

- use the AWS SDK default credential provider chain;
- accept region and model identifiers as configuration;
- optionally accept a **non-secret profile name** for local development;
- never accept access-key or secret-key parameters;
- never construct an SDK client with explicit credential values;
- never read credential values from `.env`;
- never serialize credentials into invocation records;
- never log a full SDK session, credential object, or environment;
- never cache AWS credentials itself;
- let the SDK or the external provider refresh temporary credentials.

The prohibited construction, stated concretely so a reviewer recognises it:

```python
boto3.client(
    "bedrock-runtime",
    aws_access_key_id=...,       # prohibited
    aws_secret_access_key=...,   # prohibited
    aws_session_token=...,       # prohibited
)
```

Also prohibited: custom credential-file parsing, reading `~/.aws/credentials` directly, reading a
federation cache directly, parsing CLI credential output, shelling out for raw credential values,
persisting `Credentials` or frozen credential objects, passing credentials between processes,
sending them through queues, recording them in model-invocation audit rows, including them in
exception messages, and dumping all environment variables during diagnostics.

Create the client through a session or default construction, and let the chain resolve identity. A
profile may be selected through standard SDK configuration **without reading its underlying
values**.

### Preflight identity report

Before a benchmark runs, a preflight reports only safe identity metadata:

```
account identifier, where appropriate
assumed-role ARN, with session-specific portions handled safely
region
Bedrock model-access result
credential-provider category, when discoverable without exposing values
expiration time, when safely available
```

It must never report access-key identifiers, secret-access-key values, session tokens, credential
cache paths, signed request headers, or a full environment dump.

### The default suite requires no AWS identity, and still does not

The mock provider works with no AWS identity at all, and the default suite must never require one. A
test that silently needs AWS access is a test that will skip in every environment that lacks it —
the failure mode this project has already corrected twice.

**This survived Phase 1 intact.** A real provider was reached; not one test reaches it.
`tests/architecture/test_phase1_aws_boundary.py` fails the build if a test imports a provider SDK or
shells out to the CLI, if a shipped package acquires an AWS import or a region literal, if ordinary
CI gains an `id-token` permission or a credential step, or if the smoke tooling or its evidence
becomes tracked. The instrument that can spend money lives under the gitignored `var/local-tools/`
and refuses to run without an explicit opt-in flag.

---

## Phase 2, 2026-08-03

Phase 1 reached AWS once, by hand, with the CLI. Phase 2 built the code path — and a browser, and a
button that spends money. Both are IMPLEMENTED. This section records what that added to the attack
surface and what holds each part of it closed. It supersedes nothing above; every requirement stated
earlier still binds.

### The adapter is the only AWS-shaped module in the repository

`packages/llm_gateway/providers/bedrock.py` is the sole module that imports an AWS SDK.
`tests/architecture/test_architecture.py` fails the build if `boto3` or `botocore` is imported
anywhere in `packages/` outside the provider directory,
`tests/architecture/test_phase1_aws_boundary.py` additionally forbids the capability catalog the two
ways a package reaches AWS without importing an SDK — a subprocess to the CLI, and an HTTP client
aimed at an AWS endpoint — and `tests/architecture/test_phase2_boundaries.py` extends the SDK ban to
the browser-facing packages. One module is the entire review surface for this policy, which is the
property the policy was written to obtain.

**The client is constructed with a region and nothing else.** The factory takes one argument, that
argument is a region, and it passes one keyword to the SDK. No parameter on the factory, on the
provider, or anywhere in `packages/configuration` can carry an access key, a secret key, a session
token, a profile's contents or a credential file path — so the prohibited construction shown above
is not merely unwritten: there is no value anywhere in the process to write into it. Temporary
credentials are resolved and refreshed by the default provider chain, exactly as this document
required before any of the code existed.

**The region has no default, and a missing one fails closed.** `LlmSettings` raises
`MissingModelRegionError` for any non-mock provider configured without a region, and the client
factory raises again if an empty one reaches it. The reason is Phase 1 evidence: one approved
candidate is not offered in the project's preferred region at all, so a defaulted region would have
made a real model appear unavailable for a reason nobody could see in the code — the form-family
defect with a bill attached. Verified regions live in exactly one file,
`../llm/bedrock-capability-snapshot.yaml`, and are reached through `packages/model_catalog`; a
cross-region route is disclosed rather than taken silently. No region literal is repeated here,
because a capability recorded twice drifts.

**The SDK is an optional extra, so ordinary CI does not install it at all.** `boto3` is declared
under the `aws` extra and imported lazily inside the client factory. Ordinary CI installs the `dev`
extra, so "ordinary CI is AWS-free" now means the SDK is absent rather than merely unused, and
importing the adapter — which the architecture tests do — costs nothing and requires nothing. A host
without the extra gets a named error naming the extra to install, not an import traceback and not a
fallback to some other provider.

**No test reaches AWS, and none can.** The client factory is injectable, so the whole adapter is
exercised against a fake client with no identity, no network, no port and no skip. That is what
keeps the suite's property of having no environmental precondition, and what keeps `test-no-skips`
honest now that a real provider exists.

**What an invocation record holds.** The adapter writes the Converse arguments it built, and the
provider's response, to the gitignored evaluation store as transport evidence. That envelope is the
arguments, not the signed HTTP request: no authorization header, no security-token header and no
credential-provider state exists inside it to leak or to redact. Image bytes are replaced by their
SHA-256 and byte count, with the exact bytes preserved as a separate evidence object, so an envelope
stays reconstructible without carrying every artifact twice. What is recorded beyond that is the
safe operational set this document already names: region, provider request id, latency, token
counts, stop reason, success or failure.

**Cost control is implemented; cost is not yet measured.** The budget controls required above exist
— a cumulative spend journal that survives a restart, reservation before the call, settlement after
it, failed billable calls charged rather than forgiven, and one billable invocation at a time. Price
inputs are verified in the capability snapshot. The token counts they multiply are not, so any
dollar figure per filing is PENDING first measurement and must not be quoted as known.

### The review application, which is the exposure Phase 2 actually added

The review UI reads preserved SEC filings, shows run evidence, and has a control that spends money
against a real AWS account. On loopback that is a single-user developer tool. On a LAN it is an
unauthenticated remote control for someone else's bill. `packages/review_api/security.py` and
`packages/configuration.ReviewSettings` hold that closed:

- **Loopback is the default bind address**, and binding beyond it is a deliberate act.
- **Binding beyond loopback is refused without a development authentication secret.** The refusal
  is in the settings constructor, so the unsafe combination is unreachable by forgetting a flag
  rather than merely discouraged in prose. The secret comes from ignored environment state, has no
  default and no placeholder — an empty placeholder documents an unsafe design as the expected one
  — must be at least sixteen characters, and is compared in constant time, because a timing oracle
  on a short secret is a real oracle.
- **Sessions are server-side and in memory.** The cookie carries an opaque random identifier and
  nothing else: no role, no user record, no signed claim a client could forge or replay. A restart
  logs everybody out, which is correct here — a session that survives a restart survives a
  compromise, and there is nothing in a local tool worth the persistence machinery.
- **Every state-changing request carries a CSRF token bound to the session.** A browser on another
  origin can make the request; it cannot read the token.
- **No CORS header is emitted at all.** The absence is the policy. A permissive header added "for
  development" is how a permissive header reaches production.
- **A strict content security policy is applied to every response, without exception**:
  `default-src 'none'`, stylesheet and script served from the application's own origin, no
  `unsafe-inline`, framing denied, plus `nosniff`, `no-referrer` and `no-store`. The session cookie
  is marked `Secure` only when HTTPS is actually configured, because setting it over plain HTTP
  makes the browser discard the cookie and produces a login loop that reads as a bug rather than as
  the control it was meant to be.

**Escaping the filing rather than sanitising it is what makes that policy possible.** A preserved
filing is untrusted bytes from the open internet, and it is rendered as escaped text inside a
preformatted block — never as markup. Because no filing can contribute an element, an attribute or a
script, `script-src 'self'` is safe, no HTML sanitizer is needed and no sandboxed iframe is needed.
A sanitizer would have been wrong for a second reason as well: it rewrites the bytes, and the bytes
are the evidence coverage is proved against.

**The browser receives no credential, no endpoint and no filesystem path.** It receives model
labels, regions, states, counts, money, the preserved bytes of a filing and the exact bytes a model
returned. There is no browser-to-provider route, because no response carries anything a browser
could call a provider with — the entire model path is server-side through `packages/llm_gateway`.
`tests/architecture/test_phase2_boundaries.py` fails the build if a browser-facing module so much as
mentions a credential variable name or a provider endpoint.

**The default access log is silenced deliberately.** The standard library's HTTP server logs the
full request line, which carries the query string, which carries entity identifiers and search
terms. `packages/observability` is the single home for structured logging with centralized
redaction; a second, unredacted log written by the standard library beside it is exactly the defect
that rule exists to prevent, and the log is the one place nobody thinks to check.

### What Phase 2 did not add

No workload identity, no trust policy, no Terraform, no Secrets Manager use, no deployed service,
and no AWS role in any CI workflow — ordinary CI still grants `contents: read` and nothing else, and
`tests/architecture/test_phase1_aws_boundary.py` still fails the build if it gains an `id-token`
permission or a credential step. Only the parsing stage invokes a model: the image, summary and
analysis roles are routed but raise `StageNotAuthorizedError` rather than invoke, so no second
billable path exists to secure yet. Every section below remains PLANNED and binds when it is built.

---

## Workload identity on AWS

Each workload receives **its own least-privilege IAM role**. For the planned ECS architecture:

| Workload | Role |
|---|---|
| API | API task role |
| Ingestion worker | ingestion task role |
| Summarization worker | summarization task role |
| Publisher | publication task role |
| Scheduler | scheduler task role |
| ECS platform | task-execution role, **separate from every application role** |

One broad application role shared across all services is prohibited. The reason is blast radius: a
summarization worker compromised through filing content it parsed should not be able to publish a
dataset or read the API's secrets.

Application code uses the task role automatically through the provider chain. **AWS credentials are
never injected into ECS environment variables or task-definition secrets.**

**The task role, not the execution role, grants application permissions** — Bedrock invocation, S3
object access, SQS access, Secrets Manager reads, KMS decrypt, and CloudWatch application
operations where needed. The execution role is limited to ECS platform operations: pulling images
and delivering configured secrets. These two are confused constantly, and the result is an
execution role with application permissions that every task in the account inherits.

---

## Trust policies

A service principal belongs only in a trust policy, where an AWS service must assume a role. Every
trust policy must:

- name only the required service principal;
- avoid wildcard principals;
- restrict `sts:AssumeRole`;
- use source-account or source-resource conditions where the service supports them;
- prevent confused-deputy exposure;
- keep deployment roles separate from runtime roles;
- keep task roles separate from task-execution roles;
- **not trust the account root principal as a convenience shortcut**;
- not grant assumption to all principals in an organization without specific justification.

---

## CI and CD

GitHub Actions assumes a dedicated role through **OpenID Connect**. The following are never stored
as GitHub secrets: AWS access-key ID, AWS secret-access key, AWS session token.

The trust policy restricts assumption by repository, owner, branch or environment or protected
deployment context, intended audience, and required workflow context where supportable.

Roles are separated by purpose:

```
read-only Bedrock benchmark validation
artifact publication
infrastructure planning
production deployment
```

**A pull-request workflow from an untrusted fork receives no AWS role capable of modifying
resources or invoking billable models.** A fork can propose arbitrary workflow changes; a role that
can spend money is a role a stranger can spend money with.

**The ordinary unit-test workflow requires no AWS access**, and the current one does not have any.

**The real-model benchmark workflow is explicit, gated, budget-limited, and cannot run implicitly
on every push.**

---

## Unattended workloads outside AWS

Use a temporary-credential mechanism: IAM Roles Anywhere, OIDC web identity, or another approved
federation mechanism. **Do not solve an off-AWS workload by creating a long-lived IAM-user access
key.**

An exception requires all of: a written ADR, a documented inability to use temporary credentials,
explicit user approval, a rotation and revocation plan, a narrowly scoped IAM policy,
secret-scanning coverage, and a removal deadline. The default decision remains no long-lived IAM
users.

---

## Secrets Manager

Used only for secret material that IAM authorization cannot replace. For every secret:

- grant access to the exact workload role that needs it;
- scope access to the exact secret ARN or approved path;
- encrypt with an appropriate KMS key;
- limit `kms:Decrypt` to the intended role and context;
- retrieve at runtime;
- do not write the value to disk;
- do not copy it into general environment dumps;
- do not log it;
- do not return it through an API;
- do not persist it in an application database;
- define ownership and rotation;
- define failure behaviour when retrieval fails.

Where an AWS service supports direct secret injection, prefer the service integration over custom
retrieval code, provided it preserves rotation and least privilege.

**Do not store AWS access keys in Secrets Manager.** The role used to retrieve a secret must itself
come from the workload environment. Otherwise the design is circular: the workload needs embedded
AWS credentials in order to fetch AWS credentials, and the embedded ones are exactly what this
policy exists to eliminate.

---

## Configuration

Tracked configuration **may** contain:

```
AWS_REGION                             Bedrock model IDs
AWS_PROFILE (optional, local only)     role ARNs
secret ARNs or logical secret names    feature flags
non-secret endpoint names              budget limits
```

Tracked configuration **must not** contain:

```
access keys                            session tokens
secret values                          signed URLs containing credentials
console-login URLs                     internal federation URLs
credential cache paths                 internal AWS account aliases
personal account identifiers           production account IDs, unless the architecture
                                       explicitly requires a public, non-secret identifier
```

**`.env.example` carries no placeholder for `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, or
`AWS_SESSION_TOKEN`.** An empty placeholder is not neutral: it documents an unsafe authentication
design as the expected one and invites the reader to fill it in. `AWS_PROFILE` and `AWS_REGION`
serve local configuration instead.

---

## Logs and observability

`packages/observability` redacts credential-bearing field names centrally. Covered: access-key
fields, secret-key fields, session-token fields, authorization headers, security-token headers,
signed-cookie fields, presigned-URL query signatures, and secret values returned by Secrets
Manager.

Never logged: full STS responses, full Secrets Manager responses, full request headers, full
environment dictionaries, full boto configuration objects, credential-provider caches.

Safe operational fields, which is what a model invocation should actually record:

```
AWS service      region           model ID
role name, when not sensitive     request ID
invocation latency                token counts
dollar cost                       success or failure classification
```

---

## Least-privilege Bedrock

The Phase 2 developer identity and the future summarization role receive only the Bedrock actions
and model resources the benchmark requires. **Broad administrator access to make model discovery
easier is prohibited** — discovery is a one-time convenience, and the permission outlives it.

**DISCLOSED, 2026-08-03.** Phase 1 discovery ran under an IAM Identity Center `AdministratorAccess`
role, which was the identity supplied for that task. It was performed once, by hand, and produced a
dated document rather than a running capability; no CI job holds an AWS role and no code in
`packages/` can reach AWS at all. The rule above is not relaxed by that and binds before any
repeatable or automated invocation path is built. `../adr/ADR-0018-verified-capability-snapshot-over-a-provider-adapter.md`
section 7.

Permissions are separated for:

- listing or discovering available models;
- invoking standard summaries;
- invoking the larger Deep Analysis model;
- reading and writing model request/response objects;
- reading cost or invocation metadata.

**Deep Analysis and standard summarization must be separately measurable and separately
restrictable**, even while they share one AWS account. They have different cost profiles and
different abuse profiles, and a single permission covering both makes each invisible inside the
other.

The benchmark must have a hard invocation budget, a hard dollar budget, an explicit model
allowlist, an explicit region, a manual start, no automatic retries that can exceed the budget, and
complete non-secret audit metadata.

---

## Terraform and deployment — Stage 2

- Terraform authenticates through a temporary federated or OIDC-assumed role.
- Terraform state must not contain secret values where that is avoidable.
- Terraform variables must not carry AWS credentials.
- Provider blocks must not contain access keys.
- Runtime roles are created with least privilege.
- Deployment roles and application roles remain separate.
- Production deployment requires an approved environment.
- Infrastructure plans must not print secret values.
- Secret values are created or supplied through an approved secret-management process, never a
  committed variable file.

---

## Enforcement

`tests/architecture/test_aws_identity.py` fails the build when tracked files introduce unsafe
credential handling. It detects credential environment variables in tracked configuration, SDK
client constructors receiving explicit credential arguments, provider configuration models carrying
access-key fields, credential placeholders in `.env.example`, Terraform provider blocks with
credential arguments, Docker or ECS configuration injecting raw credentials, workflows storing
static keys, Bedrock code reading raw credential environment variables, Secrets Manager entries
intended to hold AWS keys, unredacted credential-bearing URLs, and full environment dumps in
application code.

The checks distinguish **unsafe configuration** from **security documentation that names the
prohibited fields** — this document names every one of them and must not fail the build it defines.
That is done with a narrow allowlist of specific paths, not by weakening the patterns.

Gitleaks remains enabled over history and the working tree, with its rules unchanged. No synthetic
test fixture may be accommodated by relaxing it.
