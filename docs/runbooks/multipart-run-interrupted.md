# Runbook: a multipart parse stopped partway

SEVERITY: low. Nothing is lost, nothing is retried, and nothing is spent by finding out.

A model-directed multipart parse is a dozen or more billable calls under one child filing job, and
a twenty-four-part parse is tens of minutes of provider time. It can stop partway for four reasons,
and **they need different actions**. Telling them apart is the whole point of this runbook.

## First: what is always true

```
every call that completed is preserved, with its exact request and exact response
nothing is re-invoked by opening a page, restarting a process, or reading this runbook
no partial content from a truncated call has entered the assembled parse
the assembled index reports INCOMPLETE_WORK rather than claiming assembly
```

## Identify which of the four it is

Open the call hierarchy: `/runs/{run_id}/jobs/{job_id}/multipart`. Every call shows its state.

| State | What happened | Action |
|---|---|---|
| `BLOCKED` with a `blocked_reason` | A spending ceiling refused the next reservation | see **1** |
| `INTERRUPTED` | The process died while the call was in flight | see **2** |
| `FAILED` with an error | The provider refused, non-retryably | see **3** |
| `TRUNCATED` | The response hit the output cap | see **4** — usually nothing to do |

---

## 1. A ceiling paused the branch

The reason names which of the three refused: the cumulative ceiling, the phase ceiling, or this
filing's own budget. A `budget.paused` event carries the same sentence.

**This is the system working.** Nothing was shrunk, dropped or downgraded to fit.

1. Decide whether the parse is worth more money. The hierarchy header shows what this filing has
   spent, what its budget is, and what the phase has spent against its ceiling.
2. If yes, raise the relevant ceiling in the environment and restart the application:
   `MULTIPART_FILING_BUDGET_USD`, `PHASE_COST_CEILING_USD`, or `COST_CEILING_USD`.
3. Press **Re-arm budget-paused work**.

> The filing's budget is recorded on the child job when the run is created, so raising the
> environment variable affects NEW runs. A run already created keeps the budget it was created with,
> which is deliberate: a ceiling that could be raised retroactively on a job in flight is not a
> ceiling.

**Do not** use **Resume interrupted work** for this. It is a different control on purpose — an
interrupted task was in flight when a process died, and a blocked one was refused by a spending
limit. Collapsing them would let a restart quietly re-arm work a limit had stopped.

---

## 2. The process restarted

Start-up marks every mid-flight child job and every mid-flight multipart task `INTERRUPTED` and
stops. **NOTHING is re-invoked**: a task that was RUNNING may or may not have been billed, and the
only honest thing to do is say so and wait for a person.

1. Confirm the completed calls are intact. They are: the hierarchy shows them `SUCCEEDED` with
   their costs and validation.
2. Press **Resume interrupted work**. Only the interrupted branch is reopened; a parse whose plan
   and four parts succeeded keeps all five and re-runs neither.

---

## 3. The provider refused

Read the error on the task. Three shapes come up:

**An expired AWS IAM Identity Center session.** `TokenRetrievalError: Token has expired and refresh
failed`. This is the most likely cause of a long parse stopping, because a parse can outlive a
session. It is classified NON-RETRYABLE and correctly so: a credential problem is not a transient
service error, and retrying spends money to learn nothing.

```bash
aws sso login          # requires a browser authorization; only a person can complete it
```

Then press **Resume interrupted work**, or **Retry this call** on the failed task. A retry mints a
NEW billable identity, which is what stops it being refused as a duplicate.

**Throttling or a transient service error.** The orchestrator already retried once, automatically,
with its own reservation. If it still failed, wait and retry the call explicitly.

**A validation or access error.** Do not retry: the same request will fail the same way. Read the
message, fix the configuration, and create a new run.

---

## 4. A call hit the output cap

**Usually nothing to do — this is the protocol operating.** The truncated response is preserved
exactly, marked `TRUNCATED`, and treated as evidence; its partial content never enters the parse.
A `REPLAN_TRUNCATED_PART` call is queued automatically, receives the intact filing again, and
proposes subparts covering the WHOLE original part.

Check the hierarchy for the replanning call and the subparts beneath it. If they completed, the
branch finished and the truncation cost one branch rather than the filing.

**It needs attention only when:**

- the branch reached `MULTIPART_MAX_DEPTH` and a `depth.limit` event says so. The branch is paused
  with its reason recorded. Raising the limit is an operational decision; the model asking to go
  deeper is information about the filing that belongs in the sprint record.
- the replanning call itself truncated. There is nothing to divide automatically at that point, and
  the parse carries the gap into review.

**Never** ask the model to continue the truncated response. It is prohibited, there is no code path
for it, and `TaskState.TRUNCATED` has no outgoing transition — so it is not merely discouraged,
it is impossible.

---

## When the parse genuinely cannot finish

Let it reach review with the gap visible. `INCOMPLETE_WORK` and an unresolved item in the assembled
view are the correct outcomes, and they are far better than a parse that claims coverage it does
not have. `rules.md` section 21 rule 5: uncertainty produces PARTIAL or REVIEW_REQUIRED, and a
false complete is a defect.
