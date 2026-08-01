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

## Normal operation

The mirror is resumable and idempotent. A completed run downloads nothing.

```
python scripts/mirror_dera.py
```

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
