# ADR-0008: Use Terraform for infrastructure as code

STATUS: ACCEPTED
DATE: 2026-08-01
SPRINT: 1

## Context

An infrastructure-as-code tool must be chosen. The user asked that open architectural questions be
resolved with documented, reversible assumptions rather than blocking progress, so this decision
is made now and marked for revisit.

## Decision

Use Terraform. Infrastructure lives in `infrastructure/` and is not applied by application code.

Rationale. The infrastructure is a small, mostly static set of managed services: a container
service, a queue, a relational database, object storage, a cache, and model access. That shape is
well served by declarative configuration. Terraform's state and plan model makes the diff
reviewable before it is applied, which matters for a system holding financial data. It is also
provider-neutral, which keeps a future move less costly than a cloud-specific tool would.

CDK would be preferable if the infrastructure required significant programmatic generation. It
does not.

## Alternatives Considered

AWS CDK. Rejected for now: its advantage is expressing infrastructure as a program, which this
infrastructure does not need, and it couples the definition to one cloud.

Console-managed infrastructure. Rejected: not reproducible and not reviewable.

## Consequences

Infrastructure changes are reviewed as plans. A second language and toolchain enter the
repository. Environments are separated by workspace and variable file.

## Migration Impact

Reversing this means rewriting the infrastructure definitions. No application code changes.

## Revisit Conditions

Revisit if infrastructure requires substantial programmatic generation, or if the team's existing
expertise makes the other tool materially faster to operate safely.
