# Runbook: dataset publication rollback

SEVERITY: high, user-visible

## Design property that makes this safe

Published Parquet datasets are immutable and versioned. The serving layer reads whichever version
the pointer names. Rollback is a pointer flip, not a data restore.

## Symptoms

Charts show wrong or missing values after a publication. Query errors referencing a dataset
version.

## Procedure

1. Identify the current and previous dataset versions.
2. Flip the pointer back to the previous version. This takes effect on each worker's next
   connection; no restart is required.
3. Confirm the dashboard recovers.
4. Leave the bad version in place for diagnosis. Do not delete it.

## Then diagnose

Compare row counts and metric spot-checks between versions. Common causes: a metric definition
change that was not regression-tested, a fact-load that ran against a partial DERA package, or a
Q4 derivation change.

## Prevention

Publication is gated on verification against the previous version: row-count delta within
tolerance, spot-check metrics for a fixed issuer set, and no null spike in a required column.
