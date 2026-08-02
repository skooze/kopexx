# Deployment Architecture

IMPLEMENTATION STATUS: PLANNED (Stage 2 phase W-7). Nothing is deployed. The local stack runs.
DECISION RECORDS: ADR-0008 (Terraform), ADR-0009 (ECS over Lambda)

## Local development — IMPLEMENTED

```
docker compose up      postgres, minio, redis
make check             format, lint, types, 626 tests, migration reversibility
```

No model credentials required. The default provider is an in-process mock.

## Production topology — PLANNED

```
                 CloudFront ---> S3 (web assets)
                      |
                     ALB
                      |
              ECS Fargate: api            autoscale on request rate
                      |
   +------------------+-------------------+
   |                  |                   |
Aurora PostgreSQL   Redis            S3 (raw + parquet)
   |                                      ^
   +---- ECS Fargate: worker -------------+   autoscale on queue depth
   |         (ingest, parse, summarize)
   +---- ECS Fargate: scheduler              single task
             |
           SQS + DLQ, EventBridge schedules
             |
        Model provider (VPC endpoint)
```

## Identity and secrets — PLANNED

AUTHORITATIVE: `docs/security/aws-identity-and-secrets.md`. Mandatory rule: `rules.md` section 3.

**Each workload gets its own least-privilege IAM role.** No credential is ever injected into an
environment variable or a task-definition secret; application code resolves identity through the
SDK provider chain.

| Workload | Role |
|---|---|
| API | API task role |
| Ingestion worker | ingestion task role |
| Summarization worker | summarization task role |
| Publisher | publication task role |
| Scheduler | scheduler task role |
| ECS platform | task-execution role, separate from all of the above |

One broad role shared across services is prohibited. The reason is blast radius: a summarization
worker compromised through filing content it parsed must not be able to publish a dataset or read
the API's secrets.

**The task role grants application permissions** — Bedrock invocation, S3, SQS, Secrets Manager
reads, KMS decrypt. **The execution role is limited to ECS platform operations**: pulling images
and delivering configured secrets. These two are confused routinely, and the result is an
execution role carrying application permissions that every task in the account inherits.

Terraform authenticates through a temporary federated or OIDC-assumed role. Provider blocks carry
no access keys, variables carry no credentials, and plans print no secret values. Deployment roles
stay separate from runtime roles.

## Networking

Private subnets for ECS, Aurora, and Redis. Public subnets carry only the ALB and NAT. VPC
endpoints for S3 and the model provider so that traffic does not traverse NAT. Security groups are
least-privilege and referenced by group, not CIDR.

## Environments

`local`, `dev`, `prod`, separated by AWS account. Terraform workspaces and per-environment
variable files. Region is configuration, never hard-coded, because model availability and pricing
vary by region.

## Worker types

| Worker | Scaling signal | Notes |
|---|---|---|
| Ingest | Queue depth | Capped so total request rate stays under the SEC limit regardless of task count |
| Parse | Queue depth | CPU bound |
| Summarize | Batch queue | Bounded by provider quota and budget |
| Publish | Event | Single task; publication is serialized |

The ingest cap is a hard constraint rather than a tuning parameter: the SEC limit is aggregate
across machines, so scaling ingest workers past it produces throttling, not throughput.

## Dataset publication

Write a new version directory to S3, verify against the previous version, then flip the pointer
row in PostgreSQL. Readers pick it up on next connection. Rollback is a flip back.

## Backups and recovery

Aurora automated backups with point-in-time recovery. S3 versioning on raw objects. Recovery
objective: control plane restore within one hour; the fact lake and serving datasets are
regenerable from preserved raw sources, which is slower but complete.

## Deployment and rollback

Rolling ECS deploys with health checks. Migrations run before the deploy and are reversible.
Rollback is the previous task definition plus, when a dataset was published, a pointer flip.

## Cost drivers

In descending order: model invocation, Aurora, Fargate task-hours during backfill, S3 storage for
raw filings and multiple dataset versions, and NAT egress. Backfill is a one-time burst; steady
state is dominated by model calls and Aurora.
