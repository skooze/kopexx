# Filing Discovery

---

# CURRENT DIRECTION — AUTHORITATIVE. Everything below this section is historical.

## What discovery must produce

The qualifying-family decision comes from the **reviewed inventory**, never from a pattern. 41
distinct 10-family form strings were enumerated across all 135 time-eligible EDGAR quarterly master
indexes from 1993Q1 through 2026Q3 and adjudicated into **22 included and 19 excluded**. Every
included form carries an authoritative SEC description read from a real filing-detail page and a
verified accession.

```
EXACT FILED STRINGS ARE PRESERVED. EDGAR writes 10KSB, not 10-KSB.
PREFIX MATCHING ALONE NEVER CLASSIFIES A FORM.
AN UNREVIEWED CANDIDATE FAILS CLOSED FOR REVIEW.
```

The defect this rule exists to prevent: a hand-written filter searched for the hyphenated strings
`10-KSB` and `10-QSB`, matched almost nothing, and concluded the small-business family was
"effectively absent". It is roughly 190,000 filings, and `10QSB` is the fourth most common form in
the entire family. Enforced by `tests/unit/test_form_family_contract.py`.

## Identity

Filing identity is `(CIK, accession)`. The accession alone is not unique — co-registration puts one
submission under more than one filer CIK, and a rule keyed on the accession rejects valid SEC data.
Ownership is resolved from the SEC archive path, never from the accession prefix, which is
frequently the filing agent's CIK: 361 of 613 corpus filings.

## Transport, not meaning

Discovery records transport facts only — declared type, size, order, format, era, addressability.
It does not classify content. **Pre-2001 documents are not individually addressable on EDGAR**: the
complete submission text file is the only retrievable artifact and every filed document lives
inside it, so no component may assume a per-document URL exists.


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
136 quarterly index DIRECTORIES exist from 1993 to 2026, totalling about 356 MB, of which
135 are populated. Measured 2026-08-02: 1993Q1 through 2026Q3 all carry filing records; the
SEC pre-creates the directory for the next quarter, so 2026Q4 exists but its master.gz is a
236-byte header-only stub with zero data rows. A scan must count contributing quarters, not
directories.

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
