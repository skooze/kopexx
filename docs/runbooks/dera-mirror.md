# Runbook: DERA mirror

SEVERITY: critical, because the loss is permanent
OWNING PACKAGE: `packages/dera_notes`
ROADMAP: URGENT-01

## Why this is urgent

SEC retains only a rolling twelve months of monthly NOTES packages and deletes them once
consolidated into quarterly packages. A period reachable only as a monthly becomes **permanently
unreachable** if deleted before its quarterly consolidation is published.

There is no recovery. If a monthly is lost, that period's footnote text and facts are gone from
this source.

## Status: mirrored 2026-08-01

The emergency mirror is COMPLETE. All 78 currently discoverable packages are held locally.

    listing     https://www.sec.gov/data-research/sec-markets-data/financial-statement-notes-data-sets
    discovered  78   (66 quarterly, 12 monthly)
    persisted   78
    failed      0
    bytes       27,228,877,737  (25.36 GiB)
    manifest    var/dera/manifest.json
    ledger      var/dera/ledger.json

The gap this run closed: quarterly coverage ends at 2025q2, while monthlies run 2025_07 through
2026_06. Twelve months of data had NO quarterly consolidation and were reachable only as
monthlies. Those twelve were downloaded first, in a separate 74-second run, before the bulk.

## Normal operation

The mirror is resumable and idempotent. A completed run downloads nothing and re-hashes every
file on disk rather than trusting the ledger.

```
python scripts/mirror_dera.py --size-only     probe sizes, download nothing
python scripts/mirror_dera.py --dry-run       discover and report
python scripts/mirror_dera.py --only-monthly  the irreplaceable packages first
python scripts/mirror_dera.py                 everything not already held
```

Verified idempotent: a second full run reported 78 discovered, 0 downloaded, 78 already present,
0 failed, in 82 seconds.

## Symptom: discovery returns nothing

`DeraDiscoveryError` is raised rather than an empty list, deliberately, because a silent empty
result is indistinguishable from "nothing new".

1. Fetch the landing page manually and confirm it still lists packages.
2. If the page layout changed, fix the extraction in `packages/dera_notes/discovery.py`.
3. **Never** work around it by generating filenames. Three 2010 packages carry irregular
   suffixes (`2010q1_notes_1.zip`, `2010q2_notes_0.zip`, `2010q3_notes_0.zip`) and a generated
   name 404s, recording a gap that does not exist.

## Symptom: a package that existed is now missing

Check the ledger for a recorded entry. If we mirrored it, we still have it in object storage and
the upstream deletion does not matter.

If we never mirrored it and it is gone upstream, record the gap explicitly in the roadmap known
limitations. Do not leave it as an unexplained hole.

## Symptom: a package hash changed

SEC republished it. Store the new version alongside the old one; do not overwrite. Record both in
the ledger and reconcile which one the loaded facts came from.

## Monthly versus quarterly reconciliation

Monthly packages are retained even after the quarterly arrives. Compare accession coverage between
the two. A quarterly missing accessions present in its monthlies is a finding worth reporting to
SEC and worth keeping the monthlies for.

## Verification

```
make test-unit          discovery and resumability tests
make test-integration   idempotency and provenance
```

Confirm every ledger entry has a URL, SHA-256, size, retrieval timestamp, and period.
