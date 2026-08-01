# Runbook: Deep Analysis abuse

SEVERITY: medium; cost impact, and a signal of a control gap

## Symptoms

Scope rejection rate spikes. One principal creates many sessions. Cost per principal exceeds the
expected distribution.

## Procedure

1. Query scope violations grouped by principal and by detected entity. A single principal probing
   many issuers is a different problem from many principals hitting one detector gap.
2. Check whether violations were caught by the deterministic detector before invocation, which
   costs nothing, or by the model afterwards, which costs a turn. A rise in the latter means the
   detector has a gap.
3. Confirm budgets and quotas actually engaged. If cost exceeded the cap, the enforcement point is
   defective and that is the priority, not the abuse.

## Immediate actions

Reduce the per-principal daily cost cap. Reduce the session creation rate limit. Terminate active
sessions for the principal if abuse is ongoing.

## Then

Add the missed alias or entity form to the deterministic detector and add a security test for it.
Every gap found in production becomes a test.

## What not to do

Do not widen scope to satisfy a user asking for a cross-issuer comparison. That is a product
decision requiring a new scope type with its own allowlist semantics, not a relaxation of
enforcement (ADR-0012).
