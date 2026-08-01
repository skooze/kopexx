# ADR-0014: Ship a local single-user authentication interface, defer real accounts

STATUS: ACCEPTED
DATE: 2026-08-01
SPRINT: 1

## Context

Deep Analysis sessions are owned by a user, budgets are per user, and session ownership must be
verified on every request. None of that requires a full identity system to exist yet, but all of
it requires the concept of a user to exist in the model from the beginning, because retrofitting
ownership into an existing session table is a migration with a security-sensitive backfill.

The product owner asked that open architectural questions not block progress.

## Decision

Define an authentication interface and a principal concept now. Provide a local single-user
implementation for development that returns a fixed principal. Every session, budget, quota, and
audit record carries a principal identifier from the first migration.

Real authentication is a later, additive change: a new implementation of the same interface.

## Alternatives Considered

Build full authentication now. Rejected: it is not on the critical path to proving the product
thesis and would delay the vertical thread.

Omit the user concept entirely and add it later. Rejected: ownership checks are a security
control, and adding them after sessions exist means backfilling ownership onto rows whose real
owner is unknown.

## Consequences

Ownership checks are exercised from Sprint 1 even though there is only one principal.
Multi-user behaviour is unproven until a real implementation exists, so the cross-user access
test asserts the check runs rather than that a real identity system works.

This is a deployment blocker: the system must not be exposed publicly with the local
implementation active.

## Migration Impact

None to the schema. Replacing the implementation changes configuration and adds an identity
provider integration.

## Revisit Conditions

Revisit before any deployment reachable outside a development machine. Tracked as roadmap item
D-05.
