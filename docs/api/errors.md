# API Error Taxonomy

IMPLEMENTATION STATUS: PLANNED — Phase 6, with a review-UI subset in Phase 2

> The envelope and the transport, identity, not-found and rate-limit codes are stable. **Codes for
> parsed, image, summary and analysis artifacts are deliberately absent**, because the artifact
> contract is derived from what real models return and no model has been invoked. Codes belonging to
> the deleted pipeline — dataset publication, footnote resources, footnote-classification filters —
> were removed here (ADR-0017). Adding a code for a resource that does not exist is how an API
> acquires a shape its data never had.

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
| 400 | `UNKNOWN_METRIC` | no | Metric identifier not recognized |
| 400 | `INVALID_RANGE` | no | Range is unparseable or inverted |
| 401 | `UNAUTHENTICATED` | no | No valid principal |
| 403 | `FORBIDDEN` | no | Principal may not access this resource |
| 403 | `SESSION_NOT_OWNED` | no | Session belongs to another principal |
| 403 | `SCOPE_VIOLATION` | no | Request falls outside the session's authorized scope |
| 404 | `ISSUER_NOT_FOUND` | no | No issuer for that identifier |
| 404 | `FILING_NOT_FOUND` | no | Accession not present |
| 404 | `RUN_NOT_FOUND` | no | No run for that parent run ID |
| 409 | `AMBIGUOUS_TICKER` | no | Ticker resolves to more than one issuer; details carry candidates |
| 409 | `SESSION_EXPIRED` | no | Session past expiry; start a new one |
| 413 | `MESSAGE_TOO_LARGE` | no | Message exceeds the configured maximum |
| 422 | `FILING_NOT_PROCESSED` | yes | Known filing, processing incomplete; details carry status |
| 422 | `MODEL_INCOMPATIBLE` | no | The selected model cannot take this filing intact; details carry bytes, estimated tokens and the discovered limit. **The system never substitutes a model** |
| 429 | `RATE_LIMITED` | yes | Per-principal API rate limit; `Retry-After` supplied |
| 429 | `QUOTA_EXCEEDED` | no | Daily cost or session quota exhausted |
| 429 | `BUDGET_EXHAUSTED` | no | Session budget exhausted |
| 500 | `INTERNAL_ERROR` | yes | Unexpected; request_id logged with a full trace server-side |
| 503 | `MODEL_UNAVAILABLE` | yes | Provider unavailable; model-invoking endpoints only |

`MODEL_INCOMPATIBLE` is a 422 and not a 503: the request is well-formed and the service is healthy.
The pairing is refused, it costs nothing, and only the user may choose a different model.

## Distinguishing "no data" from "not processed"

These are different answers and the API says which.

```
FILING_NOT_FOUND        we have no record of this accession
FILING_NOT_PROCESSED    we have it, processing is incomplete, here is the status
200 with an empty result   we processed it and the filing genuinely does not contain this
```

Collapsing these into one response is how a dashboard tells a user a company has no revenue when
in fact the pipeline has not run.

A parsed artifact that exists but is not yet APPROVED is neither of these. It is not an error at
all: it is returned with its review state, and it does not satisfy a search as a trusted result
until it is approved.
