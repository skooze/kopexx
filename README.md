# FinTek

A financial filing and historical analysis platform. An investor types a ticker and gets that
company's SEC filings already digested: deterministic financial charts, and one plain-language
summary for every financial-statement footnote in every 10-K and 10-Q the company has ever filed.

A 10-K may run a hundred pages, of which only a page or two is the financial statements. The rest
is footnotes explaining *why* the company did what it did. The footnotes are the product.

---

## Read this before changing anything

```
1. rules.md            the operating contract
2. roadmap.md          where the project is and what comes next
3. techspecs.md        what the code currently does
4. CHANGELOG.md        what changed and why
5. docs/sprints/       the latest sprint record
6. docs/adr/           the decisions and their reasoning
```

The repository is the durable project memory. No conversation or chat log is authoritative.

---

## Status

Sprint 1 complete. Foundation, governance, SEC primitives, and the LLM content boundary.

```
104 tests passing
 94% coverage on the seven implemented packages
ruff format clean, ruff lint clean, mypy clean across 55 source files
```

Ingestion at scale, the fact lake, canonical footnote extraction, summarization, the dashboard,
and Deep Analysis are specified and not yet built. `techspecs.md` states the status of every
component.

---

## Quick start

```bash
make install          # virtualenv and dependencies
make check            # format, lint, types, tests
make up               # postgres, minio, redis
cp .env.example .env  # then set SEC_USER_AGENT
```

`SEC_USER_AGENT` must identify your application and contain a contact email. Startup fails
otherwise, deliberately: SEC denylists library-default user agents and answers them with HTTP
403, so generating that traffic is worse than not starting.

```bash
SEC_USER_AGENT="FinTek Research you@example.com" \
  python scripts/mirror_dera.py --dry-run
```

No model credentials are required. The default provider is an in-process mock that exercises the
full gateway path offline.

---

## Three properties that shape everything

### Every footnote gets a summary

Every actual financial-statement footnote in every processed filing has exactly one canonical
record and exactly one active accepted summary. Routine footnotes get shorter summaries. None is
omitted because a model judged it immaterial. Completeness is computed and displayed honestly:

```
Footnotes summarized: 23 of 24 — one footnote is awaiting review
```

### The dashboard never calls a model

Searching a ticker, opening a filing, changing a timeframe, expanding a footnote, or changing a
chart is served entirely from stored data. Summarization happens offline. A model provider outage
is not a product outage.

### Deep Analysis is scoped, metered, and auditable

It is bound to one issuer for its lifetime. The browser sends a session identifier and a message;
nothing else is trusted. Scope, budgets, and the model are loaded server-side. Retrieval tools
re-derive their allowlist from the session on every call and do not trust their arguments.

---

## The model content boundary

Model-visible content is **unmarked plain text or exactly one unfenced YAML 1.2 document**.
Markdown, JSON, JSON Schema, XML, XBRL, HTML, and native tool schemas are prohibited in both
directions. All model access goes through `packages/llm_gateway`.

AWS SDK transport JSON, browser API JSON, and PostgreSQL JSONB are outside this boundary and are
permitted. The distinction is between the envelope and the content.

Two verified facts drive the details. YAML 1.2 does not coerce `yes`, `no`, `on`, `off` into
booleans, where YAML 1.1 does, so `ruamel.yaml` in pure safe mode is used. And YAML 1.2 parses an
unquoted `0000320193` as the integer `320193`, destroying a CIK, so every identifier is quoted.

See `docs/llm/content-boundary.md` and ADR-0013.

---

## Layout

```
packages/          25 domain packages; 7 implemented
  sec_identity       CIK, accession, and URL construction — the single home
  configuration      settings with eager validation
  sec_client         rate limiting and throttle classification
  storage            object store and hashing
  observability      structured logging and correlation
  dera_notes         SEC dataset discovery and mirror ledger
  llm_gateway        the model content boundary
apps/              api, worker, scheduler, web            planned
prompts/           versioned .txt and .yaml — never .md
metric_definitions/  curated concept priority, reviewed like code
tests/             unit, integration, architecture, and fixtures
docs/              49 specification documents, 14 ADRs, 10 runbooks
scripts/           operational entry points
```

---

## Verified findings this design rests on

Everything below was confirmed by live measurement against SEC endpoints, not recalled.

| Finding | Consequence |
|---|---|
| Apple's FY2025 10-K has **13** footnotes, not the 58 TextBlock facts | The unit of work, and therefore cost, was corrected 4.5-fold |
| Role URI attached 46 of 46 child blocks on that filing | Deterministic grouping is possible; breadth validation still required |
| SEC throttling is a **403 with an HTML body**, not a 429 | Retry logic keyed on status code silently drops filings |
| Backoff from 1 second **extends** a rate block | The only correct response is a 600-second cooldown |
| `python-requests/2.31.0` receives 403 | User-Agent validation must fail closed at startup |
| A 30-request burst at 88/s all returned 200 | Never size a fetcher from burst behaviour |
| `filings.recent` caps at 1,000 entries | Reading only it silently truncates history |
| CIK padding is **inverted** between SEC hosts | One normalization module owns both forms |
| The accession prefix can be a **filing agent**, not the issuer | Building an Archives path from it 404s |
| `companyfacts` drops dimensional facts and all extension concepts | It cannot be the primary fact source |
| A `10-K/A` can be 545 KB against a 14 MB original | Amendments are patches, never replacements |
| No Q4 10-Q exists | Q4 must be derived, and labelled as derived |
| DuckDB cannot open a file another process holds read-write | Serving reads immutable versioned Parquet |
| Apple's 1994 10-K is retrievable, PEM-armored, 240,556 characters | All-time coverage is achievable |

---

## Contributing

`rules.md` is the contract. In particular: search for an existing implementation before writing a
new one; never reimplement CIK, accession, fiscal, or cost logic; keep prompts out of application
code; and never mark a sprint complete while code and documentation disagree.
