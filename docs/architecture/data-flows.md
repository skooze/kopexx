# Data Flows

IMPLEMENTATION STATUS: PLANNED except where marked

## Ingestion to publication

```
issuer discovery              ticker snapshots, unioned across repeated fetches
   |
temporal registry             cik, listings with validity windows, exclusions
   |
filing discovery              submissions.zip + filings.files[] + master.gz reconciliation
   |
era-branched acquisition      IMPLEMENTED: URL construction; PLANNED: fetching
   |
raw preservation              object storage, sha256, headers, strategy
   |
era parser                    inline XBRL | standalone XBRL | HTML | plain text | PEM
   |
   +--> facts                 DERA NOTES primary, companyfacts freshness patch
   |       |
   |    fact lake             append only; is_latest_selected computed separately
   |       |
   |    metric resolution     curated concepts, per period, never per issuer
   |       |
   |    derived metrics       formula version and input fact ids recorded
   |
   +--> source blocks + tables
           |
        canonicalization      role URI, then TOC, then heading, then fallbacks
           |
        completeness gate     extracted == summarized, or PARTIAL
           |
        one summary job per canonical footnote
           |
        schema -> numeric -> citation validation
           |
        persisted summary, versioned, superseded not overwritten
                       |
              versioned Parquet publication
                       |
              atomic pointer flip
                       |
              dashboard reads stored data only     ZERO model calls
```

## Deep Analysis turn

```
browser sends { session_id, message }        nothing else is trusted
   |
load session server-side                     scope, budgets, model
   |
ownership check
   |
budget and quota check                       before any spend
   |
deterministic entity detector                out-of-scope refused here, free
   |
scope-filtered retrieval                     summaries index, then original evidence
   |
YAML evidence package                        compiled, boundary validated
   |
analysis model                               via the gateway, never directly
   |
YAML response                                boundary validated, safe parsed
   |
citation validation                          every cited id must resolve
   |
memory update                                only evidenced findings promoted
   |
response to browser                          JSON, outside the model boundary
```

## Serialization at each hop

```
SEC -> FinTek           HTML, XML, XBRL, TSV, ZIP        machine formats, parsed immediately
FinTek internal         typed Python objects
FinTek -> model         plain text or YAML 1.2 ONLY      the constrained boundary
model -> FinTek         plain text or YAML 1.2 ONLY
FinTek -> database      relational columns and JSONB
FinTek -> browser       JSON
```

Raw SEC markup never reaches a model. It is normalized into prose and structured values first.
