# Deployment Architecture

IMPLEMENTATION STATUS: PLANNED. **NOTHING IS DEPLOYED AND AWS IS NOT CONFIGURED.**
DECISION RECORDS: ADR-0008 (Terraform), ADR-0009 (ECS over Lambda)

> **UPDATED 2026-08-03.** There is no local Docker stack, no application database, no Alembic
> migration and no dataset publication step: all four were deleted with the rejected parser and its
> persistence layer (ADR-0017). The **shape** of the deployment below — separate roles per workload,
> private subnets, a rate-capped acquisition worker — is unchanged and still binding. The **choice
> of datastore** is not: it is designed in Phase 4 from measured artifacts, and every store named
> below is a placeholder for a role, not a decision.

## Local development — IMPLEMENTED

```
make install           create the virtualenv
make check             format, lint, types, full test suite
make test-no-skips     the same suite, failing if any test skips
make coverage          the suite with the 85% coverage gate
```

**The suite has no environmental precondition at all** — no database, no container runtime, no
network, no credentials. That is deliberate: it previously needed two live PostgreSQL databases and
every database test skipped without them, which is a guard that quietly stopped being enforced. The
default provider is an in-process mock, so the whole LLM pipeline runs offline.

## Production topology — PLANNED, SHAPE ONLY

```
                 CloudFront ---> S3 (web assets)
                      |
                     ALB
                      |
              ECS Fargate: api            autoscale on request rate
                      |
   +------------------+-------------------+
   |                  |                   |
persistent store    Redis            S3 (preserved source + artifacts)
 (Phase 4 decision)  24h TTL cache        ^
   |                                      |
   +---- ECS Fargate: worker -------------+   autoscale on queue depth
   |         (acquire, parse, optional stages)
   +---- ECS Fargate: scheduler              single task
             |
           SQS + DLQ, EventBridge schedules
             |
        Model provider (VPC endpoint)
```

**Redis is never authoritative.** It holds approved artifacts for 24 hours over a persistent store
that remains the source of truth. Losing it costs latency and nothing else.

## Identity and secrets — PLANNED

AUTHORITATIVE: `docs/security/aws-identity-and-secrets.md`. Mandatory rule: `rules.md` section 3.

**Each workload gets its own least-privilege IAM role.** No credential is ever injected into an
environment variable or a task-definition secret; application code resolves identity through the
SDK provider chain.

| Workload | Role |
|---|---|
| API | API task role |
| Acquisition worker | acquisition task role |
| Model worker (parse and optional stages) | model-invoking task role, with its own allowlist |
| Scheduler | scheduler task role |
| ECS platform | task-execution role, separate from all of the above |

One broad role shared across services is prohibited. The reason is blast radius: a worker
compromised through the filing content it handled must not be able to reach the API's secrets or
overwrite a preserved original.

**Parsing and Deep Dive must be separately measurable and separately restrictable** even while
sharing one account. They have different cost and abuse profiles, and one permission covering both
makes each invisible inside the other.

**The task role grants application permissions** — Bedrock invocation, S3, SQS, Secrets Manager
reads, KMS decrypt. **The execution role is limited to ECS platform operations**: pulling images
and delivering configured secrets. These two are confused routinely, and the result is an
execution role carrying application permissions that every task in the account inherits.

Terraform authenticates through a temporary federated or OIDC-assumed role. Provider blocks carry
no access keys, variables carry no credentials, and plans print no secret values. Deployment roles
stay separate from runtime roles.

## Networking

Private subnets for ECS, the persistent store, and Redis. Public subnets carry only the ALB and NAT.
VPC endpoints for S3 and the model provider so that traffic does not traverse NAT. Security groups
are least-privilege and referenced by group, not CIDR. **No browser-to-provider path exists at any
tier.**

## Environments

`local`, `dev`, `prod`, separated by AWS account. Terraform workspaces and per-environment
variable files. Region is configuration, never hard-coded, because model availability and pricing
vary by region.

## Worker types

| Worker | Scaling signal | Notes |
|---|---|---|
| Acquire | Queue depth | Capped so total request rate stays under the SEC limit regardless of task count |
| Parse | Filings queued | Bounded by provider quota, context limits and the authorized cost ceiling. NOT CPU bound |
| Optional stages | Selected stages only | Same bounds; zero work when the selector is blank |

The acquisition cap is a hard constraint rather than a tuning parameter: the SEC limit is aggregate
across machines, so scaling acquisition workers past it produces throttling, not throughput.

Parse workers are almost entirely idle while waiting on a provider. Scaling them past the provider's
concurrency or the run's cost ceiling buys throttling and spend, not throughput.

## Backups and recovery

Point-in-time recovery on the persistent artifact store, once one exists. S3 versioning on preserved
source objects — **the preserved originals are the irreplaceable asset**, because every derived
artifact can be regenerated from them and they cannot be regenerated from anything.

Recovery objective: restore run and approval records within one hour. Parsed, image and summary
artifacts are regenerable from preserved source by re-running the recorded model, prompt and
settings, which is slower, costs real money, and is not guaranteed byte-identical — model output
varies between reruns. Approved artifacts are therefore backed up, not treated as reproducible.

## Deployment and rollback

Rolling ECS deploys with health checks. Rollback is the previous task definition. **There is no
migration step and no dataset pointer flip**; both belonged to the deleted persistence layer, and
whatever schema management Phase 4 introduces is designed then and recorded then.

## Cost drivers

In descending order: model invocation, the persistent store, Fargate task-hours during any backfill,
S3 storage for preserved source and artifact versions, and NAT egress. **Model invocation dominates
and is unmeasured** — no model has been invoked, so every figure in `docs/llm/cost-model.md` is a
placeholder. Backfill is a one-time burst and requires separate authorization; steady state is
dominated by model calls.
