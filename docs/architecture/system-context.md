# System Context

IMPLEMENTATION STATUS: PLANNED for most components; see `techspecs.md` for per-component status

## External systems

| System | Direction | What crosses | Trust |
|---|---|---|---|
| `www.sec.gov` | read | Filing documents, archives, quarterly indexes, DERA datasets | Content untrusted |
| `data.sec.gov` | read | Submissions metadata, companyfacts | Content untrusted |
| `efts.sec.gov` | read | Full-text search | Untrusted; separate rate bucket |
| Model provider | write then read | Model-visible content and responses | Response untrusted |
| Browser | read and write | API requests and responses | Fully untrusted |

FinTek writes nothing back to SEC. The only outbound side effect is a metered model invocation.

## Planes

```
INGESTION   discovery, acquisition, preservation, parsing        outbound to SEC
CONTROL     issuers, filings, footnotes, summaries, jobs, sessions
DATA        immutable facts and versioned serving datasets
LLM         summarization and validation, offline and batched
ANALYSIS    Deep Analysis, interactive and scoped
SERVING     API and dashboard, reads stored data only
```

The serving plane never calls the LLM plane. That separation is what makes a provider outage
invisible to the dashboard.

## Failure domains

| Domain | Blast radius |
|---|---|
| SEC unavailable | Ingestion pauses; serving unaffected |
| Model provider unavailable | Summarization queues; Deep Analysis degraded; dashboard unaffected |
| PostgreSQL unavailable | Everything degraded; this is the single point of failure |
| Object storage unavailable | Ingestion and raw retrieval fail; cached serving continues |
| Redis unavailable | Cache misses and limiter falls back to conservative in-process pacing |
| A publication is bad | Pointer flip back; instant |

PostgreSQL is the acknowledged single point of failure, mitigated by managed multi-AZ deployment
rather than by adding another store.

## Scaling boundaries

| Component | Scales by | Hard limit |
|---|---|---|
| Ingestion workers | Queue depth | **SEC rate limit, aggregate across all machines** |
| Parsing workers | Queue depth | CPU |
| Summarization | Batch submission | Provider quota and budget |
| API | Request rate | Database connections |
| Serving reads | Horizontal, freely | None; readers share no lock |

Adding ingestion workers past the rate limit adds nothing. That limit is the binding constraint on
backfill duration and no amount of parallelism moves it.
