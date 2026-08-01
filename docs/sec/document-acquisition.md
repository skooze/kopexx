# Document Acquisition

IMPLEMENTATION STATUS: PLANNED (Sprint 3, inline-XBRL era only; other eras Stage 2 W-2); URL construction IMPLEMENTED (Sprint 1)
OWNER PACKAGE: `packages/filing_acquisition`

## The decision table

Branch on the XBRL flags carried in the submissions record. This is the single highest-leverage
choice in the ingestion design.

| Condition | Fetch | Requests | Why |
|---|---|---|---|
| `isInlineXBRL = 1` (2019 onward) | `{accession}-xbrl.zip` | **1** | Bundle contains the narrative primary document AND the schema and all linkbases |
| `isXBRL = 1, isInlineXBRL = 0` (2009 to 2018) | `{accession}-xbrl.zip` plus `primaryDocument` | 2 | Bundle carries a standalone instance only; the narrative is separate |
| `isXBRL = 0` (2001 to 2008) | `primaryDocument` | 1 | HTML, no XBRL to recover |
| `primaryDocument = ""` (pre-2001) | complete submission `.txt` | 1 | The only addressable object |

### Why the bundle, verified

For Apple's 10-Q accession `0000320193-26-000020`, the `-xbrl.zip` is **166,630 bytes on the
wire** and contains ten members totalling 2,169,839 bytes raw, including `aapl-20260627.htm`, the
primary narrative document, at 1,018,209 bytes, plus three certification exhibits, the schema,
and the calculation, definition, label, and presentation linkbases.

The measured mean size of a complete submission `.txt` is **11,082,089 bytes** across a sample of
850. The bundle is therefore roughly a **33-fold byte reduction at identical request count**, and
it carries the narrative as well as the structure.

### Inline XBRL transformation is unnecessary

SEC publishes its own extracted instance at a derivable filename: the primary document stem with
`_htm.xml` appended. Verified HTTP 200 across four different filing agents. This removes any need
to implement `ix:nonFraction` scale, sign, and format handling, or `ix:continuation` resolution,
for the backfill path.

`packages.sec_identity.extracted_instance_url` constructs it.

### The schema carries statement classification

The `.xsd` inside the bundle declares role types. For Apple's 10-Q there are 49, distributed
`Disclosure: 42, Statement: 6, Document: 1`, and the six `Statement` roles are exactly the primary
financial statements. This makes `FilingSummary.xml` unnecessary for statement classification,
though it remains useful for report titles.

## Rejection assertions

An acquired object is rejected, not stored, when any of these holds. Storing a rejected object is
a silent corruption, which is worse than a failed fetch.

```
the response is a directory listing               HTTP 200 on a bare folder URL
the primary document name is empty                pre-2001; use the flat .txt path
a ZIP lacks its expected members                  truncated or wrong object
the body matches a known SEC error page hash
the content type contradicts the expected type
the accession in the content does not match the requested accession
an XBRL package contains neither an instance nor a narrative
```

## Provenance recorded per object

```
url                       sha256               acquisition_strategy
retrieved_at              size_bytes           parser_compatibility
http_status               content_type         retry_history
response_headers          source_dataset_version
```

## Size planning without probe requests

`submissions.size` is the exact byte count of the complete submission text, verified on three
filings. The whole download budget is therefore plannable with zero probe requests.

This matters because **HEAD against Archives returns no `Content-Length`**: the S3 objects are
gzip-transformed, so a pre-flight sizing pass built on HEAD silently yields `None`.

## Folder index traps

`index.json` for a filing folder carries two fields that mislead.

`type` is the renderer's **sprite icon filename** (`text.gif`, `compressed.gif`, `image2.gif`),
not a MIME type. Classify by filename suffix.

`size` is an **empty string** for three of Apple's 65 folder entries, so `int(item["size"])`
raises `ValueError` and any folder-size total computed from it under-counts.

`FilingSummary.xml`'s final `<Report>` is a sentinel with `LongName` of `All Reports` and **no
`HtmlFileName` child**, so Apple's 47 listed reports correspond to 46 real files and
`report.find("HtmlFileName").text` raises `AttributeError`.

Individually served `R*.htm` files still carry their SGML submission wrapper before `<html>`.

## Scale

Approximately 171,000 filings for the current Nasdaq universe across all time, roughly 30 to 50 GB
using the bundle strategy against roughly 1.9 TB for complete submissions. At six requests per
second the backfill is about eight hours, resumable.

The sample behind the filing count is fifteen issuers, giving a wide interval: the true total is
plausibly 86,000 to 257,000. Disk is sized at 1 TB rather than to the point estimate.

## Tests

IMPLEMENTED: URL construction across all four eras, empty primary document rejection, both
accession forms, issuer-versus-agent CIK.

PLANNED Sprint 3 and Stage 2 W-2: era branching against golden fixtures per era, directory-listing rejection at
the acquisition layer, ZIP member assertion, resumability under `kill -9`, and reconciliation of
acquired accessions against the quarterly master index.
