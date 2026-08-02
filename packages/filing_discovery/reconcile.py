"""Reconcile discovery against the quarterly master index.

The submissions API is a convenience view. The quarterly `master.gz` files are the index SEC
builds from the filings themselves, so they are the independent check on whether discovery
missed something. Running both and comparing is the only way to know that "this issuer filed
47 reports" means 47 rather than "47 that we happened to see".

SEC-INVARIANT: use `master.gz`, not `master.idx`. Same content, roughly six times smaller.
"""

from __future__ import annotations

import gzip
import io
from datetime import date

from packages.sec_identity import accession_dashed, cik_padded, quarterly_index_url

from .discovery import is_covered_form
from .errors import ReconciliationError

# master.idx is pipe-delimited with a header block ending in a line of dashes.
_FIELDS = 5


def quarters_between(start: date, end: date) -> list[tuple[int, int]]:
    """Every (year, quarter) pair covering the range, inclusive."""
    out: list[tuple[int, int]] = []
    year, quarter = start.year, (start.month - 1) // 3 + 1
    last = (end.year, (end.month - 1) // 3 + 1)
    while (year, quarter) <= last:
        out.append((year, quarter))
        quarter += 1
        if quarter == 5:
            year, quarter = year + 1, 1
    return out


def parse_master_index(raw: bytes, cik: str) -> set[str]:
    """Accessions of covered filings for one CIK in a decompressed master index.

    HISTORICAL-FORMAT: some quarters repeat a row. The 25-NSE rows in 2019Q1 appear twice. A set
    absorbs that; a list would inflate the count and produce a phantom discrepancy.
    """
    text = (
        gzip.decompress(raw).decode("latin-1") if raw[:2] == b"\x1f\x8b" else raw.decode("latin-1")
    )
    wanted = str(int(cik))
    found: set[str] = set()
    for line in io.StringIO(text):
        parts = line.rstrip("\n").split("|")
        if len(parts) != _FIELDS:
            continue
        row_cik, _name, form, _filed, path = parts
        if row_cik.strip() != wanted or not is_covered_form(form):
            continue
        stem = path.rsplit("/", 1)[-1].removesuffix(".txt")
        try:
            found.add(accession_dashed(stem))
        except Exception:  # noqa: BLE001 - a malformed path is not a reconciliation failure
            continue
    return found


def reconcile_against_master(
    client,
    cik: str | int,
    discovered: set[str],
    *,
    start: date,
    end: date,
) -> dict[str, object]:
    """Compare discovery with the master index over a quarter range.

    Returns a report rather than raising, so a caller can log the detail before deciding. Use
    `raise_if_incomplete` when a gap should stop the run.
    """
    padded = cik_padded(cik)
    in_index: set[str] = set()
    quarters_read = 0
    quarters_unavailable: list[str] = []

    for year, quarter in quarters_between(start, end):
        url = quarterly_index_url(year, quarter)
        try:
            raw = client.get_bytes(url)
        except Exception as error:  # noqa: BLE001 - a missing quarter is reported, not fatal
            quarters_unavailable.append(f"{year}Q{quarter}: {type(error).__name__}")
            continue
        in_index |= parse_master_index(raw, padded)
        quarters_read += 1

    return {
        "cik": padded,
        "quarters_read": quarters_read,
        "quarters_unavailable": tuple(quarters_unavailable),
        "in_master_index": len(in_index),
        "discovered": len(discovered),
        "missing_from_discovery": tuple(sorted(in_index - discovered)),
        "absent_from_index": tuple(sorted(discovered - in_index)),
    }


def raise_if_incomplete(report: dict[str, object]) -> None:
    """Fail when the master index knows about a filing discovery did not return.

    The reverse case, a filing discovery found that the index does not list, is reported but not
    fatal: the index omits some amendments and the submissions API is the more complete source
    for those.
    """
    missing = report.get("missing_from_discovery") or ()
    if missing:
        raise ReconciliationError(str(report["cik"]), tuple(missing))  # type: ignore[arg-type]
