# ADR-0001: DERA Financial Statement and Notes Data Sets as the primary structured source

STATUS: ACCEPTED
DATE: 2026-08-01
SPRINT: 1

## Context

Three candidate sources exist for structured financial facts and footnote text.

The `data.sec.gov` companyfacts API is the most convenient. Verification showed it is unusable as
a primary source. For one Apple 10-K the XBRL instance contains 57 occurrences of
`RevenueFromContractWithCustomerExcludingAssessedTax`; companyfacts returns 3, having silently
dropped every dimensional fact. It contains no company extension concepts at all, and extension
concepts are 91.4 percent of distinct tags in a recent quarter. It mixes 8-K facts into the same
array as 10-K and 10-Q facts. Its `frame` field carries the restated value rather than the
originally filed one, and its `fy` and `fp` fields describe the filing rather than the datapoint,
so grouping by fiscal period double-counts year-to-date facts alongside discrete quarters.

The DERA Financial Statement Data Sets are structurally sound but narrower than the NOTES sets.
Comparing one Boeing 10-K: the plain sets carry 623 numeric facts across 146 tags, the NOTES sets
carry 2,477 facts across 620 tags, and zero tags present in the plain sets are absent from NOTES.
Every plain-set accession for the sampled month also appears in NOTES.

The DERA NOTES sets additionally carry footnote narrative text with the filer's own titles,
presentation ordering, and disclosure metadata.

## Decision

Use the DERA Financial Statement and Notes Data Sets as the primary structured source for both
facts and footnote text. Do not ingest the plain Financial Statement Data Sets at all. Use
companyfacts and the submissions API only as a freshness patch for filings newer than the most
recent DERA publication, and as a reconciliation signal.

## Alternatives Considered

Ingest companyfacts as primary. Rejected: it silently discards dimensional facts and every
extension concept, which would produce income statements missing company-specific lines with no
error raised.

Ingest both DERA set families. Rejected: NOTES is a proven superset, so the plain sets add 5.2 GB
of download and a redundant schema for no additional coverage.

Parse every filing's XBRL ourselves for the backfill. Rejected as the primary path: SEC already
publishes the extracted result, and reproducing it across 170,000 filings is work with no
differentiating value. Retained for the hot path only, where DERA has not yet published.

## Consequences

The backfill becomes a bulk download and load rather than a per-filing parse. Extension concepts
and presentation ordering are available, which makes reconstructing a statement as filed
possible. A dependency is created on DERA publication cadence, which has been observed to slip
from the usual 13 days to 46 and 62 days, so the freshness patch is not optional.

## Migration Impact

Reversing this decision means building a per-filing XBRL parser for all eras and a presentation
linkbase resolver, then reprocessing the archive. The raw source preservation policy makes that
possible without re-fetching from SEC.

## Revisit Conditions

Revisit if DERA publication lag exceeds 90 days routinely, if a NOTES schema change removes
footnote text, or if measurement shows NOTES omits facts that appear in filings we have
independently parsed.
