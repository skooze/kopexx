# Runbook — loading a filing's DERA facts

Loads one filing's numeric facts from a mirrored DERA NOTES package into `xbrl_fact`, then
reconciles what landed against what was read.

```bash
python scripts/load_dera_partition.py 0000320193-25-000079
```

Exit status is 0 only when the load completed **and** all nine reconciliation checks passed.

---

## Before you run it

```
a mirrored package containing the filing     var/dera/packages/, ledger at var/dera/ledger.json
a reachable PostgreSQL at DATABASE_URL       resolved by packages/persistence/engine
the schema applied                           make db-upgrade
```

The loader does not fetch anything from SEC. It reads a package already on disk and re-hashes it
before use, so a run needs no network.

To parse and validate without touching a database:

```bash
python scripts/load_dera_partition.py 0000320193-25-000079 --dry-run
```

---

## What it does, in order

1. **Selects the package** by reading each candidate's `sub.tsv`, newest period first. The package
   is never derived from a date — a filing belongs to the period it was SUBMITTED in.
2. **Re-hashes the archive** against the mirror ledger and refuses a mismatch. The download-time
   hash is not trusted; a file that rotted on disk would otherwise load silently.
3. **Registers the issuer and filing** from `sub.tsv`, if they are not already present.
   `xbrl_fact` has foreign keys to both.
4. **Reads, normalizes, and validates** every `num.tsv` row for that accession, resolving `dimh`
   against `dim.tsv`.
5. **Inserts** the rows whose natural key the database does not already hold, marks
   `dera_package.loaded_at`, and counts what is there — all in one transaction, under a
   transaction-scoped advisory lock on the accession.
6. **Reconciles** and prints a plain-text report.

A run takes about 30 seconds for a monthly package, almost all of it counting rows in the other
five members for provenance.

---

## Reading the report

```
rows for this accession
  matched in num.tsv              969
  accepted                        967
  rejected                        2

database
  inserted this run               967
  already present                 0
  total held                      967
```

`matched = accepted + rejected` always. That identity is the first reconciliation check and the
reason a rejection is counted rather than dropped.

**`rejected` is not an error by itself.** DERA emits rows with no value — the shape it uses for a
line-item label such as `CommitmentsAndContingencies`. Two per Apple filing is normal. The report
groups rejections by rule; investigate if a rule you do not recognize appears, or if the count is
a meaningful fraction of the rows.

---

## Failure: `hash mismatch`

```
2025_10_notes.zip hash mismatch: ledger has <a>, the file on disk hashes to <b>.
```

The archive changed since it was mirrored. **Do not delete the ledger entry to make this go
away.** Monthly packages are deleted upstream after quarterly consolidation, so a corrupted
monthly may not be re-downloadable. Restore from `/mnt/backup` — see `dera-backup-mount.md`, and
check the mount is actually mounted first — and re-verify before retrying.

## Failure: `no filing row for <accession>` / `sub.tsv does not list <accession>`

The accession is not in any mirrored package, or is misspelled. Check the dashed form. If the
filing is recent, the covering monthly package may not be mirrored yet: run
`python scripts/mirror_dera.py` first.

## Failure: `is missing required member(s)`

The archive is incomplete and the load fails closed. A short package would load partially and look
successful — the count would simply be lower, indistinguishable from a quiet month. Re-mirror it.

## Failure: a reconciliation check reports MISMATCH

The script exits 1 and names the check, the expected value, and the actual one. Nothing is rolled
back, because the load itself succeeded; what failed is the assertion that it was complete.

| Check | What a failure means |
|---|---|
| `database_row_count_matches_accepted` | rows were lost between validation and insert |
| `natural_key_is_unique_in_database` | idempotency is broken; a rerun would double-count |
| `numeric_total_matches` | a value was mangled, or a row lost or duplicated |
| `consolidated_split_matches` | dimensional facts leaked into the consolidated series |
| `every_dimension_hash_resolved` | the package is internally inconsistent |

Do not "fix" a mismatch by loosening the check. Find the row.

---

## The test suite can empty this database

`make check` runs `test_upgrade_then_downgrade_round_trips`, which drops every application table.
It now refuses when the database holds application rows, so a load survives an ordinary test run —
but do not point `DATABASE_URL` at a database you care about and then remove that guard.

If a load does get wiped, it is fully reproducible: re-run the loader for each accession. That is
the point of loading being idempotent and reconciled rather than a one-shot import.

---

## Re-running

Safe and expected. A rerun re-reads the whole package, recomputes every natural key, and inserts
only what is absent:

```
inserted this run    0
already present    967
```

`loaded_at` is a record of what happened, never a reason to skip work. A bookkeeping flag set by a
run that half-failed would make the gap permanent and invisible.

---

## Removing a load

Rare, and only for a load written by a defective loader — not for a restatement, which appends.

```sql
DELETE FROM xbrl_fact WHERE accession = :a AND source_dataset = 'dera_notes';
UPDATE dera_package SET loaded_at = NULL WHERE filename = :f;
```

Then re-run the loader. This was done once in Sprint 3, when a derived quarter start was found to
be a day short after 136 rows had been written.

`UPDATE` is not an option: a `BEFORE UPDATE` trigger rejects any change to a filed value, unit,
scale, concept, or period.
