#!/usr/bin/env python3
"""Mirror the SEC DERA Financial Statement and Notes datasets.

TIME-SENSITIVE: SEC retains only a rolling twelve months of monthly packages and deletes them
once consolidated into quarterly packages. A period reachable only as a monthly becomes
permanently unreachable if deleted before its quarterly consolidation is published.

Resumable and idempotent: a completed run downloads nothing. See docs/runbooks/dera-mirror.md.

Usage:
    python scripts/mirror_dera.py --dry-run
    python scripts/mirror_dera.py
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from packages.configuration import Settings  # noqa: E402
from packages.dera_notes import (  # noqa: E402
    NOTES_LANDING_URL,
    MirrorEntry,
    MirrorLedger,
    discover_packages,
)
from packages.observability import correlation_scope, get_logger, log_event  # noqa: E402
from packages.sec_client import SecRateLimiters  # noqa: E402
from packages.storage import FilesystemObjectStore  # noqa: E402

import logging  # noqa: E402

logger = get_logger("fintek.dera.mirror")


def main() -> int:
    parser = argparse.ArgumentParser(description="Mirror SEC DERA NOTES datasets")
    parser.add_argument("--dry-run", action="store_true", help="discover and report, download nothing")
    parser.add_argument("--ledger", default="var/dera_ledger.json")
    parser.add_argument("--landing-url", default=NOTES_LANDING_URL)
    args = parser.parse_args()

    settings = Settings.from_env()
    store = FilesystemObjectStore(Path(settings.storage.root) / "dera")
    ledger = MirrorLedger(args.ledger)
    limiters = SecRateLimiters(
        global_rps=settings.sec.global_requests_per_second,
        efts_rps=settings.sec.efts_requests_per_second,
    )

    with correlation_scope() as correlation_id:
        log_event(
            logger, logging.INFO, "dera mirror starting",
            correlation_id=correlation_id, dry_run=args.dry_run, ledger_size=len(ledger),
        )

        # NOTE: fetching the landing page requires an HTTP client, which is Sprint 2 work.
        # Until then this script reports what it would do from a locally supplied listing.
        listing_path = REPO_ROOT / "var" / "dera_landing.html"
        if not listing_path.exists():
            log_event(
                logger, logging.ERROR,
                "landing page not available locally; the HTTP fetch path is Sprint 2 work",
                expected_path=str(listing_path), landing_url=args.landing_url,
            )
            print(
                f"No local listing at {listing_path}.\n"
                f"Save the page at {args.landing_url} to that path, or wait for the Sprint 2 "
                f"HTTP client.",
                file=sys.stderr,
            )
            return 2

        packages = discover_packages(listing_path.read_text(encoding="utf-8"), base_url=args.landing_url)
        pending = ledger.pending(packages)

        log_event(
            logger, logging.INFO, "dera discovery complete",
            discovered=len(packages), already_mirrored=len(packages) - len(pending),
            pending=len(pending),
        )

        if args.dry_run:
            for package in pending:
                print(f"WOULD MIRROR  {package.cadence.value:<10} {package.period:<8} {package.filename}")
            return 0

        for package in pending:
            limiters.for_host(package.url).acquire()
            log_event(
                logger, logging.ERROR,
                "download path not implemented; Sprint 2 delivers the SEC HTTP client",
                filename=package.filename,
            )
            print(f"NOT IMPLEMENTED: download of {package.filename}", file=sys.stderr)
            return 3

        ledger.save()
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
