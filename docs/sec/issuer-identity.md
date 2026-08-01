# Issuer Identity and the Temporal Universe

IMPLEMENTATION STATUS: sec_identity IMPLEMENTED; issuer registry PLANNED (Stage 2 phase W-1)
OWNER PACKAGES: `packages/sec_identity`, `packages/issuer_registry`

## The core rule

CIK is the authoritative issuer identity. Ticker is a temporal alias and is never an identity.

## Verified traps

### CIK padding is inverted between hosts

```
data.sec.gov/submissions ....... CIK0000320193   zero-padded to ten digits
www.sec.gov/Archives ........... 320193          unpadded integer
```

A padded CIK against Archives produces a 301 redirect and a wasted round trip against a
single-digit-per-second budget. An unpadded CIK against data.sec.gov produces a 404.

### The accession appears in two forms in one URL family

```
folder segment ..... 000032019325000079          dashes removed
filename ........... 0000320193-25-000079.txt    dashes kept
```

Both forms occur in the same URL. One normalization module owns both.

### The accession prefix is not the issuer

`0001140361-26-025622` appears in Apple's filing list. The prefix `0001140361` is the filing
agent that transmitted it. Building an Archives path from the accession prefix 404s on every
agent-transmitted document. The CIK always comes from the filing record.

### Tickers are reused by different issuers

`BBBY` maps to CIK 886158 (Nasdaq, 2019 to 2023) and to CIK 1130713 (NYSE, formerly Overstock,
2024 onward). A ticker-to-CIK dictionary without a date silently merges two unrelated companies
and produces a chart splicing one company's revenue onto another's.

### Delisted issuers are renamed in EDGAR

CIK 886158's current name is `20230930-DK-Butterfly-1, Inc.`, a bankruptcy shell. Name matching
fails. `formerNames[]` from the submissions API is retained for reconciliation.

### Ticker snapshots are unstable

Three fetches of `company_tickers_exchange.json` within one session returned 10,432, 10,419, and
10,411 rows with three different `Last-Modified` values. CDN edges serve different versions
concurrently. Every snapshot is fetched two or three times and the results unioned; a single
response is never treated as authoritative.

### Tickers outnumber issuers

Roughly 4,342 Nasdaq ticker rows collapse to about 3,439 unique CIKs. Share classes, warrants,
and units share a CIK. Keying ingestion on ticker causes redundant fetching and renders a warrant
as though it were a company.

## Entity model

```
issuer                    cik (unique), legal_name, sic, fiscal_year_end, country, active
issuer_former_name        issuer_id, former_name, effective_start, effective_end, source
listing                   issuer_id, ticker, exchange, share_class,
                          effective_start, effective_end, is_current
listing_observation       source, observed_at, payload_sha256, raw_uri
excluded_filer            cik, name, exclusion_reason, evidence, reconsideration_status
issuer_relationship       from_issuer_id, to_issuer_id, kind, effective_date
                          kind in (merger, spinoff, successor, redomicile)
```

`listing` is uniquely constrained on `(ticker, exchange, effective_start)` and **never** on
`ticker` alone.

## Ticker resolution

Resolution is always as-of a date. A bare ticker resolves as-of today.

```
resolve(ticker, as_of) ->
    select issuer_id from listing
    where ticker = :ticker
      and effective_start <= :as_of
      and (effective_end is null or effective_end > :as_of)
```

Zero rows is not-found. More than one row is ambiguous and returns a disambiguation list rather
than an arbitrary pick.

## The active universe

The dashboard universe contains issuers with **at least one historical 10-K or 10-Q**. Everything
else is excluded and the reason preserved:

```
foreign_private_issuer_20f      files 20-F or 40-F instead
fund_n_csr                      registered fund
bdc_specialized                 business development company
shell                           no operations
never_filed                     no filings of any kind
unresolved_identity             CIK could not be resolved
filing_history_unavailable      discovery incomplete
```

Preserving exclusions rather than discarding them makes enabling a category later a flag change
rather than a re-derivation.

A delisted issuer that *did* file 10-Ks remains in the universe. The flag is computed over all
history, not over current listings.

## Survivorship

"All known Nasdaq tickers" does not exist as a downloadable artifact. SEC and Nasdaq publish
current state only and erase a company on delisting. The mitigation is a daily snapshot from
today onward, plus an Internet Archive backfill of historical snapshots. Until those accrue, any
screen over the universe is survivorship-biased, and that is recorded as a known limitation in
`roadmap.md` rather than left implicit.

## Tests

```
test_cik_padded_form                      test_accession_dashed_form
test_cik_archive_form                     test_accession_undashed_form
test_cik_rejects_boolean                  test_accession_round_trips
test_archive_url_uses_issuer_cik          test_accession_prefix_not_used_as_issuer
test_empty_primary_document_rejected      test_complete_submission_url_uses_dashed_accession
test_xbrl_zip_url_mixes_both_accession_forms
test_extracted_instance_url_is_derivable
test_quarterly_index_uses_gzip
```

All pass as of Sprint 1. PLANNED for Stage 2 phase W-1: ticker reuse resolution, former-name
reconciliation, snapshot union, and exclusion classification.
