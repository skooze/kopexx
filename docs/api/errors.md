# API Error Taxonomy

IMPLEMENTATION STATUS: PLANNED (Sprint 6)

## Envelope

```
{
  "error": {
    "code": "SCOPE_VIOLATION",
    "message": "human-readable, safe to display",
    "request_id": "uuid",
    "details": {}
  }
}
```

This is browser-facing JSON and is outside the LLM content boundary (ADR-0013).

`message` never contains filing content, model output, internal paths, or stack traces.

## Codes

| HTTP | Code | Retryable | Meaning |
|---|---|---|---|
| 400 | `INVALID_REQUEST` | no | Schema validation failed |
| 400 | `UNKNOWN_METRIC` | no | Metric not in the definition registry |
| 400 | `INVALID_RANGE` | no | Range is unparseable or inverted |
| 400 | `UNSUPPORTED_FILTER` | no | A filter whose backing data is not yet computed, for example `classification=changed` before footnote comparisons are populated. Rejected explicitly rather than silently returning everything or nothing |
| 401 | `UNAUTHENTICATED` | no | No valid principal |
| 403 | `FORBIDDEN` | no | Principal may not access this resource |
| 403 | `SESSION_NOT_OWNED` | no | Session belongs to another principal |
| 403 | `SCOPE_VIOLATION` | no | Request falls outside the session's authorized scope |
| 404 | `ISSUER_NOT_FOUND` | no | No issuer for that identifier |
| 404 | `FILING_NOT_FOUND` | no | Accession not present |
| 404 | `FOOTNOTE_NOT_FOUND` | no | Footnote not present |
| 409 | `AMBIGUOUS_TICKER` | no | Ticker resolves to more than one issuer; details carry candidates |
| 409 | `SESSION_EXPIRED` | no | Session past expiry; start a new one |
| 413 | `MESSAGE_TOO_LARGE` | no | Message exceeds the configured maximum |
| 422 | `FILING_NOT_PROCESSED` | yes | Known filing, processing incomplete; details carry status |
| 429 | `RATE_LIMITED` | yes | Per-principal API rate limit; `Retry-After` supplied |
| 429 | `QUOTA_EXCEEDED` | no | Daily cost or session quota exhausted |
| 429 | `BUDGET_EXHAUSTED` | no | Session budget exhausted |
| 500 | `INTERNAL_ERROR` | yes | Unexpected; request_id logged with a full trace server-side |
| 503 | `MODEL_UNAVAILABLE` | yes | Provider unavailable; Deep Analysis only |
| 503 | `DATASET_PUBLISHING` | yes | A dataset flip is in progress; retry shortly |

## Distinguishing "no data" from "not processed"

These are different answers and the API says which.

```
FILING_NOT_FOUND        we have no record of this accession
FILING_NOT_PROCESSED    we have it, processing is incomplete, here is the status
200 with empty series   we processed it and the issuer genuinely did not report this metric
```

Collapsing these into one response is how a dashboard tells a user a company has no revenue when
in fact the pipeline has not run.
