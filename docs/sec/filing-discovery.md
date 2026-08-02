# Filing Discovery

IMPLEMENTATION STATUS: IMPLEMENTED (Sprint 3) for one CIK; universe scale PLANNED (Stage 2 W-1). Identity and URL construction IMPLEMENTED (Sprint 1)
OWNER PACKAGE: `packages/filing_discovery`

## Sources, in order of authority

| Source | Role |
|---|---|
| `submissions.zip` | Bulk filing history for every filer; the backfill spine |
| Per-issuer submissions JSON | Incremental updates for one CIK |
| `filings.files[]` shards | History beyond the 1,000-entry cap |
| Quarterly `master.gz` | Independent reconciliation |
| Daily index | Same-day discovery |

## Traps

**`filings.recent` caps at 1,000 entries.** Roughly a third of issuers have older filings that
exist only in `filings.files[]` shards. Apple has 1,000 recent plus 1,238 older reaching back to
1994-01-26. Reading only `recent` silently truncates history, which is fatal given the all-time
requirement.

**`submissions.zip` is Zip64 with 984,730 members.** Stream member by member. Never expand it to
disk: 984,730 small files will exhaust the inode budget. Verified coverage: all 3,439 Nasdaq CIKs
present, with 1,055 overflow shards included.

**Use `master.gz`, not `.idx`.** The gzip form is roughly six times smaller for identical content.
All 136 quarterly indexes from 1993 to 2026 are present, totalling about 356 MB.

**Every `25-NSE` filing appears twice in the index**, once under the subject CIK and once under
the exchange's, carrying the same accession. Deduplicate on accession.

**Do not rely on** `filings.recent` alone, search-engine results, ticker lookup, the accession
prefix, the first filing row for a CIK, or companyfacts filing arrays.

## Form filtering

Core: `10-K`, `10-Q`. Also captured: `10-K/A`, `10-Q/A`, `10-KT`, `10-KT/A` as amendments and
transition reports. Deliberately out of MVP scope but form-extensible: `20-F`, `40-F`, `8-K`,
`DEF 14A`, `S-1`.

## Reconciliation

After discovery, the set of accessions per CIK is compared against the quarterly master indexes.
A discrepancy is recorded and investigated rather than resolved by preferring one source, because
which source is wrong is itself information.

## Watermarks

Per source and per CIK: last successful discovery timestamp, highest filing date seen, and the
content hash of the last payload. Incremental discovery starts from the watermark; a hash match
means nothing changed and no further work is scheduled.
