# Runbook: SEC throttling

SEVERITY: high if sustained, because ingestion stops
OWNING PACKAGE: `packages/sec_client`

## Symptoms

Ingestion stalls. Logs show HTTP 403 with `throttle_kind=rate_limited`. The limiter reports
`COOLING_DOWN`.

## First: which 403 is it?

SEC returns 403 for two conditions requiring **opposite** responses. Check the classification in
the log record.

```
rate_limited            wait; the system handles this automatically
undeclared_automation   configuration defect; waiting will never fix it
```

## If rate_limited

This is self-healing. The client enters a 600-second cooldown and resumes.

Do NOT reduce the cooldown or restart the process to "retry sooner". SEC requires the request rate
to stay below threshold for ten full minutes; retrying sooner extends the block.

Investigate only if it recurs more than once per hour:

1. Confirm only one limiter instance is in use. The documented limit is aggregate across all
   machines, so two processes each at 6 requests per second is 12 and will be blocked.
2. Check `SEC_GLOBAL_RPS`. Lower it to 4 and observe.
3. Confirm `efts.sec.gov` traffic is on its own 1-per-second bucket.
4. Record the SEC reference identifier from the log; SEC asks for it plus the egress address.

## If undeclared_automation

The process will have raised and stopped rather than retrying. This is intentional.

1. Check `SEC_USER_AGENT`. It must identify the application and contain a contact email.
2. Confirm it does not contain a library default fragment. Startup validation catches these, so
   a running process with a bad User-Agent means the value changed after start.
3. Correct the value and restart.

Do not work around this by retrying. Blocked traffic helps no one and risks a longer block.

## Verification

```
make test-unit                  the classification tests must pass
```

Watch SEC request metrics for a clean run of at least fifteen minutes after resumption.
