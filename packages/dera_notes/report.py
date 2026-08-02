"""Render a load and its reconciliation as plain text.

Separate from the loader so that reporting can change without touching a transaction boundary, and
so a report can be produced from a stored result without re-running the load.

The output is deliberately plain text rather than JSON. It is read by people, and it must never be
confused with model-visible content: `rules.md` and ADR-0013 prohibit JSON in either direction
across the LLM boundary, and a load report is exactly the kind of operational artifact that later
gets pasted somewhere it should not be.
"""

from __future__ import annotations

from .loader import LoadResult
from .reconcile import Reconciliation
from .selection import SelectedPackage

RULE = "-" * 78


def _row(label: str, value: object, width: int = 34) -> str:
    return f"{label:<{width}}{value}"


def selection_report(selected: SelectedPackage, accession: str) -> str:
    lines = [
        RULE,
        f"DERA PACKAGE SELECTED FOR {accession}",
        RULE,
        _row("filename", selected.filename),
        _row("cadence", selected.cadence),
        _row("period", selected.period),
        _row("sha256", selected.sha256),
        _row("size", f"{selected.size_bytes:,} bytes"),
        _row("path", selected.path),
        "",
        "why this package:",
        f"  {selected.reason}",
    ]
    return "\n".join(lines)


def load_report(result: LoadResult) -> str:
    read = result.read
    lines = [
        RULE,
        f"DERA FACT LOAD  {result.accession}  from  {result.package}",
        RULE,
        _row("state", result.state),
        _row("started", result.started_at),
        _row("completed", result.completed_at),
        _row("elapsed", f"{result.duration_seconds:.1f} s"),
        "",
        "source package",
        _row("  sha256 re-verified", result.package_sha256),
    ]
    for member, count in sorted(read.member_rows.items()):
        lines.append(_row(f"  {member} rows", f"{count:,}"))

    lines += [
        "",
        "rows for this accession",
        _row("  matched in num.tsv", f"{read.rows_matched:,}"),
        _row("  accepted", f"{read.accepted:,}"),
        _row("  rejected", f"{read.rejected:,}"),
        _row("  duplicate natural keys", f"{len(read.duplicate_keys):,}"),
        "",
        "database",
        _row("  inserted this run", f"{result.rows_inserted:,}"),
        _row("  already present", f"{result.rows_already_present:,}"),
        _row("  total held", f"{result.rows_in_database:,}"),
        _row("  numeric total (source)", read.value_total),
        _row("  numeric total (database)", result.database_value_total),
    ]

    if read.rejections:
        lines += ["", "rejections by rule"]
        counts: dict[str, int] = {}
        for rejection in read.rejections:
            for reason in rejection.reasons:
                rule = reason.split(":", 1)[0]
                counts[rule] = counts.get(rule, 0) + 1
        for rule, count in sorted(counts.items(), key=lambda kv: -kv[1]):
            lines.append(_row(f"  {rule}", f"{count:,}"))

    if read.truncated_dimension_hashes:
        lines += [
            "",
            _row(
                "  dimension strings truncated",
                f"{len(read.truncated_dimension_hashes):,} (flagged by DERA's own segt column)",
            ),
        ]

    return "\n".join(lines)


def reconciliation_report(reconciliation: Reconciliation) -> str:
    lines = [
        RULE,
        f"RECONCILIATION  {reconciliation.accession}  against  {reconciliation.package}",
        RULE,
    ]
    for check in reconciliation.checks:
        mark = "PASS" if check.ok else "FAIL"
        lines.append(f"[{mark}] {check.name}")
        lines.append(f"       expected {check.expected}")
        lines.append(f"       actual   {check.actual}")
        if check.detail:
            lines.append(f"       {check.detail}")
    lines += ["", RULE]
    lines.append(
        "RECONCILED"
        if reconciliation.ok
        else f"MISMATCH: {len(reconciliation.failures)} check(s) failed"
    )
    lines.append(RULE)
    return "\n".join(lines)


def full_report(
    selected: SelectedPackage, result: LoadResult, reconciliation: Reconciliation
) -> str:
    return "\n\n".join(
        [
            selection_report(selected, result.accession),
            load_report(result),
            reconciliation_report(reconciliation),
        ]
    )
