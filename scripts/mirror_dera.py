#!/usr/bin/env python3
"""Mirror the SEC DERA Financial Statement and Notes datasets.

TIME-SENSITIVE (roadmap URGENT-01): SEC retains only a rolling twelve months of monthly packages
and deletes them once consolidated into quarterly packages. A period reachable only as a monthly
becomes permanently unreachable if deleted before its quarterly consolidation is published.

Verified live on 2026-08-01: quarterly coverage ends at 2025q2, while monthlies run 2025_07
through 2026_06. Twelve months of data currently have NO quarterly consolidation, so those twelve
packages are the irreplaceable ones.

Single-process only. The rate limiter is in-process and the SEC limit is aggregate across
machines, so running two copies concurrently exceeds the documented ceiling.

Usage:
    python scripts/mirror_dera.py --size-only     probe sizes, download nothing
    python scripts/mirror_dera.py --dry-run       discover and report, download nothing
    python scripts/mirror_dera.py                 mirror everything not already held
    python scripts/mirror_dera.py --only-monthly  mirror only the irreplaceable monthlies
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from packages.configuration import Settings  # noqa: E402
from packages.dera_notes import (  # noqa: E402
    NOTES_LANDING_URL,
    DeraPackage,
    MirrorEntry,
    MirrorLedger,
    PackageCadence,
    discover_packages,
)
from packages.observability import correlation_scope, get_logger, log_event  # noqa: E402
from packages.sec_client import SecClientError, SecHttpClient, SecRateLimiters  # noqa: E402
from packages.storage import sha256_file  # noqa: E402

logger = get_logger("fintek.dera.mirror")


def build_client(settings: Settings) -> SecHttpClient:
    limiters = SecRateLimiters(
        global_rps=settings.sec.global_requests_per_second,
        efts_rps=settings.sec.efts_requests_per_second,
    )
    return SecHttpClient(
        user_agent=settings.sec.user_agent,
        limiters=limiters,
        cooldown_seconds=settings.sec.throttle_cooldown_seconds,
    )


def write_manifest(path: Path, rows: list[dict], listing_url: str) -> None:
    """Write the download manifest.

    The manifest is the reconciliation artifact: every discovered package appears exactly once
    with its outcome, so discovered and persisted counts can be compared without inspecting
    storage.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "manifest_version": "dera-mirror-v1",
        "listing_url": listing_url,
        "generated_at": datetime.now(UTC).isoformat(),
        "discovered": len(rows),
        "downloaded": sum(1 for r in rows if r["result"] == "downloaded"),
        "already_present": sum(1 for r in rows if r["result"] == "already_present"),
        "failed": sum(1 for r in rows if r["result"] == "failed"),
        "total_bytes": sum(r.get("size_bytes") or 0 for r in rows),
        "packages": rows,
    }
    temporary = path.with_suffix(path.suffix + ".partial")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    temporary.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser(description="Mirror SEC DERA NOTES datasets")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--size-only", action="store_true", help="HEAD every package, download none"
    )
    parser.add_argument("--only-monthly", action="store_true", help="mirror only monthly packages")
    parser.add_argument("--ledger", default="var/dera/ledger.json")
    parser.add_argument("--manifest", default="var/dera/manifest.json")
    parser.add_argument("--root", default="var/dera/packages")
    parser.add_argument("--landing-url", default=NOTES_LANDING_URL)
    args = parser.parse_args()

    settings = Settings.from_env()
    ledger = MirrorLedger(args.ledger)
    root = Path(args.root)
    root.mkdir(parents=True, exist_ok=True)

    with correlation_scope() as correlation_id, build_client(settings) as client:
        log_event(
            logger,
            logging.INFO,
            "dera mirror starting",
            correlation_id=correlation_id,
            ledger_size=len(ledger),
            landing_url=args.landing_url,
            only_monthly=args.only_monthly,
        )

        listing_html = client.get_text(args.landing_url)
        packages: list[DeraPackage] = discover_packages(listing_html, base_url=args.landing_url)

        if args.only_monthly:
            packages = [p for p in packages if p.cadence is PackageCadence.MONTHLY]

        monthly = sum(1 for p in packages if p.cadence is PackageCadence.MONTHLY)
        quarterly = len(packages) - monthly
        pending = ledger.pending(packages)

        log_event(
            logger,
            logging.INFO,
            "dera discovery complete",
            discovered=len(packages),
            monthly=monthly,
            quarterly=quarterly,
            already_mirrored=len(packages) - len(pending),
            pending=len(pending),
        )
        print(
            f"discovered {len(packages)} packages "
            f"({quarterly} quarterly, {monthly} monthly); "
            f"{len(packages) - len(pending)} already held, {len(pending)} pending"
        )

        if args.size_only:
            total = 0
            for package in packages:
                response = client.head(package.url)
                length = int(response.headers.get("content-length", 0))
                total += length
                print(f"  {length:>12,}  {package.cadence.value:<10} {package.filename}")
            print(
                f"\ntotal bytes across {len(packages)} packages: {total:,} "
                f"({total / 1024**3:.2f} GiB)"
            )
            return 0

        if args.dry_run:
            for package in pending:
                print(
                    f"WOULD MIRROR  {package.cadence.value:<10} "
                    f"{package.period:<8} {package.filename}"
                )
            return 0

        rows: list[dict] = []
        failures: list[str] = []

        for index, package in enumerate(packages, start=1):
            existing = ledger.get(package.filename)
            destination = root / package.cadence.value / package.filename

            # Resumability by content address: a ledger entry whose file is present with a
            # matching hash is complete. A truncated or altered file is detected, not trusted.
            if existing is not None and destination.exists():
                actual = sha256_file(destination)
                if actual == existing.sha256:
                    rows.append(
                        {
                            "filename": package.filename,
                            "url": package.url,
                            "cadence": package.cadence.value,
                            "period": package.period,
                            "result": "already_present",
                            "sha256": existing.sha256,
                            "size_bytes": existing.size_bytes,
                            "hash_validated": True,
                            "zip_validated": True,
                            "error": None,
                        }
                    )
                    continue
                log_event(
                    logger,
                    logging.WARNING,
                    "ledger hash mismatch; re-downloading",
                    filename=package.filename,
                    expected=existing.sha256,
                    actual=actual,
                )

            try:
                print(f"[{index}/{len(packages)}] {package.filename} ...", flush=True)
                fetched = client.download(package.url, destination, expect_zip=True)
                ledger.record(
                    MirrorEntry.create(
                        package,
                        sha256=fetched.sha256,
                        size_bytes=fetched.size_bytes,
                        storage_key=str(destination.relative_to(root)),
                    )
                )
                ledger.save()
                rows.append(
                    {
                        "filename": package.filename,
                        "url": package.url,
                        "cadence": package.cadence.value,
                        "period": package.period,
                        "result": "downloaded",
                        "sha256": fetched.sha256,
                        "size_bytes": fetched.size_bytes,
                        "hash_validated": True,
                        "zip_validated": True,
                        "last_modified": fetched.last_modified,
                        "content_type": fetched.content_type,
                        "etag": fetched.etag,
                        "retrieved_at": fetched.retrieved_at,
                        "error": None,
                    }
                )
                print(f"    ok {fetched.size_bytes:,} bytes  sha256={fetched.sha256[:16]}...")
            except SecClientError as error:
                failures.append(f"{package.filename}: {error}")
                log_event(
                    logger,
                    logging.ERROR,
                    "package download failed",
                    filename=package.filename,
                    error=str(error),
                )
                rows.append(
                    {
                        "filename": package.filename,
                        "url": package.url,
                        "cadence": package.cadence.value,
                        "period": package.period,
                        "result": "failed",
                        "sha256": None,
                        "size_bytes": None,
                        "hash_validated": False,
                        "zip_validated": False,
                        "error": str(error),
                    }
                )
                print(f"    FAILED {error}")

        ledger.save()
        write_manifest(Path(args.manifest), rows, args.landing_url)

        downloaded = sum(1 for r in rows if r["result"] == "downloaded")
        present = sum(1 for r in rows if r["result"] == "already_present")
        failed = sum(1 for r in rows if r["result"] == "failed")
        total_bytes = sum(r.get("size_bytes") or 0 for r in rows)
        persisted = downloaded + present

        print("\n--- reconciliation ---")
        print(f"discovered:       {len(packages)}")
        print(f"downloaded:       {downloaded}")
        print(f"already present:  {present}")
        print(f"failed:           {failed}")
        print(f"persisted total:  {persisted}")
        print(f"bytes stored:     {total_bytes:,} ({total_bytes / 1024**3:.2f} GiB)")
        print(f"manifest:         {args.manifest}")

        log_event(
            logger,
            logging.INFO,
            "dera mirror complete",
            discovered=len(packages),
            downloaded=downloaded,
            already_present=present,
            failed=failed,
            total_bytes=total_bytes,
            requests=client.request_count,
        )

        if failed:
            print("\nFAILURES:")
            for failure in failures:
                print(f"  {failure}")
            return 1
        if persisted != len(packages):
            print(f"\nRECONCILIATION MISMATCH: {len(packages)} discovered, {persisted} persisted")
            return 1
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
