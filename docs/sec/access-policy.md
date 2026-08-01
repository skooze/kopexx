# SEC Access Policy and Rate Control

IMPLEMENTATION STATUS: IMPLEMENTED (rate limiting, throttle classification, User-Agent validation)
OWNER PACKAGES: `packages/sec_client`, `packages/configuration`

## Responsibility

Every HTTP request to an SEC host, paced within policy, identified correctly, and classified
correctly when refused.

## Inputs

A URL, a method, and optional headers, from any ingestion component.

## Outputs

A response body and headers, or a typed error carrying its own retry classification.

## Public interface

```
packages.sec_client
    SecRateLimiters(global_rps, efts_rps).for_host(host) -> TokenBucketLimiter
    TokenBucketLimiter.acquire() -> float          blocks, returns seconds waited
    TokenBucketLimiter.try_acquire() -> bool       does not block
    classify_403(body) -> ThrottleKind
    raise_for_403(body, egress_ip) -> SecClientError
    extract_reference_id(body) -> str | None
    looks_like_directory_listing(body, content_type) -> bool

packages.configuration
    validate_user_agent(value) -> str              raises InvalidUserAgentError
    SecAccessSettings(...)                         validates eagerly
```

## Prohibited dependencies

No package outside `sec_client` may issue an SEC request directly or construct its own limiter.

## Data owned

Rate-limiter token state, throttle events, reference identifiers, per-host request metrics.

---

## The verified findings this design rests on

All confirmed by live measurement on 2026-08-01.

### The limit is aggregate

SEC documents ten requests per second "regardless of the number of machines used to submit
requests". Sharding across containers, processes, or addresses does not multiply the budget. The
bucket is therefore shared, and in production it is backed by Redis rather than held per process.

Default sustained rate is **6 requests per second**, deliberately below the ceiling.

### Throttling is a 403, not a 429

SEC returns HTTP 403 with an HTML body and **no `Retry-After` header**. Middleware that
special-cases only 429 treats throttling as a permanent client error and **silently drops
filings**. Retry classification is therefore driven by the typed error, never by status code.

### Two different 403s require opposite responses

```
Request Rate Threshold Exceeded ....... wait 600 seconds, then resume     retryable
Undeclared Automated Tool ............. fix configuration, never retry    not retryable
```

They are indistinguishable by status code. Classification is by response body.

### Exponential backoff makes a rate block worse

Policy requires the request rate to remain below threshold for a full ten minutes before access
resumes. Retrying at 1s, 2s, 4s keeps the client above threshold and extends the block
indefinitely. The only correct response is a hard 600-second cooldown, which
`SecAccessSettings` enforces as a minimum.

### Library default User-Agents are denylisted

Measured: `python-requests/2.31.0` returns 403; a declared identity returns 200. The configured
User-Agent must contain a contact email and must not match any known library default. Startup
fails if it does not, because generating traffic that will certainly be blocked is worse than not
starting.

### A burst test proves nothing

A 30-request burst at roughly 88 requests per second returned 30 responses of 200. Bursts are not
blocked; sustained rate is enforced. Never size the fetcher from burst behaviour.

### efts.sec.gov is different

Full-text search returned HTTP 500 on the eighth of eight rapid requests while `data.sec.gov`
sustained twenty-five sequential requests cleanly. It gets its own bucket at **1 request per
second**.

### robots.txt provides no guidance

There is no `Crawl-delay` in `https://www.sec.gov/robots.txt`, and `data.sec.gov/robots.txt`
returns a raw S3 404. A crawler framework deriving politeness from robots.txt defaults to
unthrottled.

---

## Required headers

```
User-Agent: <application name> <contact email>
Accept-Encoding: gzip, deflate
```

`Accept-Encoding` matters: submissions JSON compresses roughly 5.8 to 1.

## Retry matrix

| Condition | Retryable | Policy |
|---|---|---|
| Rate threshold 403 | yes | Hard 600s cooldown, then resume |
| Undeclared automation 403 | **no** | Raise; alert; this is a configuration defect |
| Unrecognised 403 | yes | Treated as a rate block; pausing is cheap, hammering is not |
| 404 | no | Permanent; record and continue |
| 500, 502, 503, 504 | yes | Bounded exponential backoff, max 3 attempts |
| Connection reset, timeout | yes | Bounded exponential backoff |
| Directory listing where a document was expected | **no** | Raise; storing it is silent corruption |
| Corrupt or truncated archive | no | Raise; record for reprocessing |

## Rate-limit state machine

```
NORMAL
  -- 403 rate threshold --> COOLING_DOWN (600s)
  -- 403 undeclared automation --> HALTED (operator action required)

COOLING_DOWN
  -- cooldown elapsed --> NORMAL
  -- 403 during cooldown --> COOLING_DOWN (timer restarts)

HALTED
  -- configuration corrected and process restarted --> NORMAL
```

`HALTED` is terminal within a process lifetime. It is not recoverable by waiting, because waiting
does not fix a User-Agent.

## Configuration

```
SEC_USER_AGENT              required, validated at startup
SEC_GLOBAL_RPS              default 6.0, must be within (0, 10]
SEC_EFTS_RPS                default 1.0
SEC_THROTTLE_COOLDOWN_S     default 600, minimum 600
```

## Observability

Per host: request count, status distribution, throttle events, bytes transferred, wait time in
the limiter. Every throttle records the SEC reference identifier and the egress address, which is
what SEC asks for when reporting an access problem. An alert fires on any undeclared-automation
403 and on a cooldown exceeding one occurrence per hour.

## Failure modes

| Failure | Detection | Response |
|---|---|---|
| Missing or generic User-Agent | Startup validation | Fail to start |
| Sustained rate exceeded | 403 body classification | 600s cooldown; resume |
| Directory listing stored as a filing | Content assertion before persistence | Reject the object |
| Limiter bypassed by a new call site | Architecture review; per-host metrics | Fix the call site |

## Unit tests

```
test_sec_throttle_classification            rate-limit body yields a retryable error
test_undeclared_automation_classification   automation body yields a NON-retryable error
test_reference_id_is_extracted
test_unknown_403_is_treated_as_rate_limit
test_directory_listing_rejected
test_global_rate_limit                      6 requests at 6/s wait exactly 1.0s
test_efts_rate_limit                        separate slower bucket
test_sec_hosts_share_one_bucket
test_try_acquire_does_not_block
test_sec_user_agent_required
test_default_library_user_agent_rejected
test_settings_reject_short_cooldown
```

All twelve pass as of Sprint 1.

## Integration tests

PLANNED: a fixture-backed client exercising a full acquisition against recorded SEC responses,
including a 403 mid-run, asserting the run pauses and resumes without losing a filing.
