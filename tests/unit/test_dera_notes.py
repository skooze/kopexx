"""DERA package discovery and mirror ledger tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from packages.dera_notes import (
    DeraDiscoveryError,
    MirrorEntry,
    MirrorLedger,
    PackageCadence,
    classify_filename,
    discover_packages,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def _landing() -> str:
    return (FIXTURES / "dera_landing_page.html").read_text(encoding="utf-8")


def test_dera_links_are_scraped() -> None:
    """SEC-INVARIANT: package URLs come from the authoritative listing, never from a pattern."""
    packages = discover_packages(_landing())
    names = {p.filename for p in packages}
    assert "2026_06_notes.zip" in names
    assert "2026q1_notes.zip" in names
    assert "file.pdf" not in names, "non-package links must be ignored"
    assert all(p.url.startswith("https://www.sec.gov/") for p in packages)


def test_dera_discovery_resolves_absolute_urls() -> None:
    packages = discover_packages(_landing())
    for package in packages:
        assert package.url.startswith("https://www.sec.gov/files/dera/")


def test_dera_filename_not_generated() -> None:
    """Three 2010 packages carry irregular numeric suffixes.

    A generated-name downloader emitting 2010q1_notes.zip would 404. Discovery must surface the
    real names 2010q1_notes_1.zip and 2010q2_notes_0.zip.
    """
    names = {p.filename for p in discover_packages(_landing())}
    assert "2010q1_notes_1.zip" in names
    assert "2010q2_notes_0.zip" in names
    assert "2010q1_notes.zip" not in names, "the regular name does not exist for this vintage"


def test_irregular_suffixes_classify_correctly() -> None:
    assert classify_filename("2010q1_notes_1.zip") == (PackageCadence.QUARTERLY, "2010Q1", 2010)
    assert classify_filename("2026_06_notes.zip") == (PackageCadence.MONTHLY, "2026-06", 2026)
    assert classify_filename("readme.htm") is None


def test_empty_listing_raises_rather_than_returning_nothing() -> None:
    """Silent zero-discovery would look identical to 'nothing new to mirror'."""
    with pytest.raises(DeraDiscoveryError):
        discover_packages("")
    with pytest.raises(DeraDiscoveryError):
        discover_packages("<html><body>no packages here</body></html>")


def test_dera_mirror_is_resumable(tmp_path: Path) -> None:
    """A completed pass must download nothing on re-run."""
    ledger_path = tmp_path / "ledger.json"
    packages = discover_packages(_landing())

    ledger = MirrorLedger(ledger_path)
    assert len(ledger.pending(packages)) == len(packages)

    # Mirror the first two packages, then simulate a crash by reloading from disk.
    for package in packages[:2]:
        ledger.record(
            MirrorEntry.create(
                package, sha256="0" * 64, size_bytes=123, storage_key=package.ledger_key
            )
        )
    ledger.save()

    resumed = MirrorLedger(ledger_path)
    assert len(resumed) == 2
    pending = resumed.pending(packages)
    assert len(pending) == len(packages) - 2
    assert all(not resumed.has(p) for p in pending)

    for package in pending:
        resumed.record(
            MirrorEntry.create(
                package, sha256="1" * 64, size_bytes=456, storage_key=package.ledger_key
            )
        )
    resumed.save()

    final = MirrorLedger(ledger_path)
    assert final.pending(packages) == [], "a completed pass must have nothing pending"


def test_monthly_packages_retained_alongside_quarterly() -> None:
    """TIME-SENSITIVE: monthlies are deleted upstream after quarterly consolidation.

    The mirror must keep both so a period reachable only as a monthly is never lost.
    """
    packages = discover_packages(_landing())
    cadences = {p.cadence for p in packages}
    assert PackageCadence.MONTHLY in cadences
    assert PackageCadence.QUARTERLY in cadences
