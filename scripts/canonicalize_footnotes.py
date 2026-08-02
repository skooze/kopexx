"""Extract and reconcile canonical footnotes for one issuer's preserved filings.

    python scripts/canonicalize_footnotes.py                       # every acquired filing
    python scripts/canonicalize_footnotes.py 0000320193-25-000079  # one filing
    python scripts/canonicalize_footnotes.py --dry-run             # no database

The script orchestrates; each stage lives in its own package and is testable without a database:

    footnote_extractor      report inventory, candidates, child blocks, note headings
    footnote_canonicalizer  stages 1-5, exclusions, attachment audit, completeness
    table_parser            table structure and cell provenance
    ...persistence          one transaction, one advisory lock, all upserts

Exit status is 0 only when every filing canonicalized with zero orphans and no unresolved case.

NO MODEL IS INVOKED and no network request is made. Input is the preserved bytes under var/objects.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from packages.footnote_canonicalizer import (  # noqa: E402
    ExclusionList,
    canonicalize,
    classify_tables,
    evaluate,
    match_headings_to_footnotes,
    ownership_report,
    reconciliation_report,
)
from packages.footnote_canonicalizer.persistence import persist  # noqa: E402
from packages.footnote_extractor import (  # noqa: E402
    find_tagged_spans,
    read_headings,
    read_inventory,
    read_presentation_from_package,
    text_block_spans,
)
from packages.observability import configure_logging  # noqa: E402
from packages.persistence.engine import create_database_engine  # noqa: E402
from packages.table_parser import parse_tables  # noqa: E402

DEFAULT_MANIFEST = REPO_ROOT / "var" / "acquisition.json"
DEFAULT_OBJECT_ROOT = REPO_ROOT / "var" / "objects"


def filing_paths(record: dict, object_root: Path) -> tuple[Path, Path, Path, str]:
    """Locate the preserved FilingSummary and primary document for one acquired filing.

    Derived from the acquisition manifest rather than guessed from the accession: the manifest
    records the storage key each object was actually written to, and inferring a filename would
    reintroduce exactly the kind of assumption acquisition exists to eliminate.
    """
    keys = {obj["role"]: obj["storage_key"] for obj in record["objects"]}
    for role in ("filing_summary", "primary_document", "xbrl_package"):
        if role not in keys:
            raise KeyError(f"{record['accession']} has no {role} in the acquisition manifest")
    return (
        object_root / keys["filing_summary"],
        object_root / keys["primary_document"],
        object_root / keys["xbrl_package"],
        keys["primary_document"],
    )


def canonicalize_one(record: dict, object_root: Path, exclusions: ExclusionList):
    """Run stages 1-5 and table parsing for one filing. Touches no database."""
    summary_path, primary_path, package_path, primary_key = filing_paths(record, object_root)
    inventory = read_inventory(summary_path)
    headings = read_headings(primary_path)

    result = canonicalize(
        accession=record["accession"],
        inventory=inventory,
        headings=headings,
        exclusions=exclusions,
        # Apple's filings carry no per-note table of contents. Stage 4 reports NOT_ATTEMPTED
        # rather than claiming a reconciliation that never happened.
        toc_expected_note_count=None,
    )
    heading_map = match_headings_to_footnotes(result.footnotes, headings)

    # Table ownership: the filer's own tagged note boundaries, resolved through the presentation
    # linkbase to the roles stage 3 already attached. Nothing positional.
    raw = primary_path.read_text(encoding="utf-8", errors="replace")
    tables = parse_tables(raw)
    spans = text_block_spans(raw)
    numeric_spans = [s for s in find_tagged_spans(raw) if s.tag == "ix:nonfraction"]
    linkbase = read_presentation_from_package(package_path)
    statement_roles = {
        report.role
        for report in inventory.real_reports
        if report.menu_category == "Statements" and report.role
    }
    ownership = classify_tables(
        result,
        tables,
        spans,
        linkbase,
        statement_roles=statement_roles,
        numeric_spans=numeric_spans,
    )

    completeness = evaluate(result, ownership)
    return result, completeness, heading_map, tables, ownership, primary_key


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("accession", nargs="?", help="one dashed accession; default is all")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--object-root", type=Path, default=DEFAULT_OBJECT_ROOT)
    parser.add_argument("--dry-run", action="store_true", help="parse only; touch no database")
    parser.add_argument("--report", type=Path, default=None)
    args = parser.parse_args(argv)

    configure_logging()
    exclusions = ExclusionList.load()

    records = json.loads(args.manifest.read_text(encoding="utf-8"))
    if args.accession:
        records = [r for r in records if r["accession"] == args.accession]
        if not records:
            print(f"no acquired filing with accession {args.accession}", file=sys.stderr)
            return 2

    engine = None if args.dry_run else create_database_engine()
    reports: list[str] = []
    failures = 0

    for record in records:
        result, completeness, heading_map, tables, ownership, primary_key = canonicalize_one(
            record, args.object_root, exclusions
        )
        report = reconciliation_report(result, completeness) + "\n\n" + ownership_report(ownership)

        if engine is not None:
            counts = persist(
                engine,
                result,
                completeness,
                heading_map,
                tables=tables,
                table_storage_uri=primary_key,
                ownership=ownership,
            )
            report += (
                f"\npersisted  footnotes={counts.canonical_footnotes}"
                f" (inserted {counts.footnotes_inserted}, updated {counts.footnotes_updated},"
                f" unchanged {counts.footnotes_unchanged})"
                f"  blocks={counts.source_blocks}"
                f" (inserted {counts.blocks_inserted}, updated {counts.blocks_updated},"
                f" unchanged {counts.blocks_unchanged})"
                f"  attachments={counts.attachments}"
                f"  sections={counts.filing_sections}"
                f"  tables={counts.tables} cells={counts.table_cells}"
                f"  footnote-owned={counts.tables_owned_by_footnote}"
            )

        if result.orphan_count or result.unresolved or ownership.unresolved:
            failures += 1
            report += "\n\nUNRESOLVED:"
            for item in result.unresolved:
                report += f"\n  {item}"

        reports.append(report)
        print(report)
        print()

    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text("\n\n".join(reports) + "\n", encoding="utf-8")

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
