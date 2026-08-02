"""Load one filing's DERA facts into PostgreSQL, then reconcile the result.

    python scripts/load_dera_partition.py 0000320193-25-000079

The script orchestrates; it holds no parsing, validation, or SQL of its own. Each stage lives in
its own module under packages/dera_notes and can be tested without a database:

    selection      which package contains this filing, decided by reading sub.tsv
    registration   the issuer and filing rows the fact foreign keys require
    tsv            parsing, with quoting disabled
    dimensions     dimh to axis and member, from dim.tsv
    normalize      row to domain values
    validate       domain rules, mirroring the database constraints
    loader         one transaction: insert, ledger, idempotency
    reconcile      does what landed match what was read
    report         plain text for a person to read

Exit status is 0 only when the load completed AND every reconciliation check passed.
"""

from __future__ import annotations

import argparse
import sys
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from packages.dera_notes import (  # noqa: E402
    MirrorLedger,
    full_report,
    load_facts,
    locate_filing,
    read_package,
    read_submission,
    reconcile,
    register_filing,
    register_mirror_ledger,
    selection_report,
)
from packages.observability import configure_logging  # noqa: E402
from packages.persistence.engine import create_database_engine  # noqa: E402

DEFAULT_PACKAGE_ROOT = REPO_ROOT / "var" / "dera" / "packages"
DEFAULT_LEDGER = REPO_ROOT / "var" / "dera" / "ledger.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("accession", help="dashed accession, for example 0000320193-25-000079")
    parser.add_argument("--package-root", type=Path, default=DEFAULT_PACKAGE_ROOT)
    parser.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER)
    parser.add_argument("--batch-size", type=int, default=2000)
    parser.add_argument(
        "--report",
        type=Path,
        default=None,
        help="also write the plain-text report to this path",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="read, normalize, and validate, but write nothing and touch no database",
    )
    args = parser.parse_args(argv)

    configure_logging()

    ledger = MirrorLedger(args.ledger)
    selected = locate_filing(args.accession, package_root=args.package_root, ledger=ledger)

    if args.dry_run:
        # A CIK is needed to normalize, and without a database there is no filing row to read it
        # from. sub.tsv is the package's own answer, which is the right one for a dry run.
        with zipfile.ZipFile(selected.path) as archive:
            record = read_submission(archive, args.accession)
        parsed = read_package(selected, record.accession, cik=record.cik)
        print(selection_report(selected, record.accession))
        print(f"\ndry run: {parsed.rows_matched} matched, {parsed.accepted} would load,")
        print(f"         {parsed.rejected} rejected, no database was contacted")
        for rejection in parsed.rejections[:10]:
            print(f"         rejected {rejection.concept}: {'; '.join(rejection.reasons)}")
        return 0

    engine = create_database_engine()

    registered = register_mirror_ledger(engine, ledger, args.package_root)
    if registered:
        print(f"registered {registered} DERA package(s) into the load ledger")

    context = register_filing(engine, selected.path, args.accession)
    result = load_facts(engine, selected, context, batch_size=args.batch_size)
    reconciliation = reconcile(engine, result)

    report = full_report(selected, result, reconciliation)
    print(report)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(report + "\n", encoding="utf-8")

    return 0 if reconciliation.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
