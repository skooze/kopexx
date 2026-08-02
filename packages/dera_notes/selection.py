"""Select the DERA package that contains a given filing.

SEC-INVARIANT: a filing appears in the package covering the period in which it was SUBMITTED,
not the period it reports on. Apple's FY2025 10-K reports on a fiscal year ending 2025-09-27 but
was filed 2025-10-31, so it lives in the 2025_10 monthly package, not 2025q3.

The package is never guessed from a date. `locate_filing` reads `sub.tsv` and answers from the
data, because the submission-versus-report distinction is exactly the kind of off-by-one-quarter
error that produces a confident, wrong, silent result.
"""

from __future__ import annotations

import zipfile
from dataclasses import dataclass
from pathlib import Path

from packages.sec_identity import accession_dashed

from .errors import DeraError
from .ledger import MirrorLedger

# Every member a NOTES package is expected to carry. readme.htm is present but stale inside the
# archives and is deliberately not consumed.
REQUIRED_MEMBERS = ("sub.tsv", "num.tsv", "pre.tsv", "tag.tsv", "ren.tsv", "txt.tsv")
OPTIONAL_MEMBERS = ("dim.tsv", "cal.tsv", "notes-metadata.json", "readme.htm")


class PackageSelectionError(DeraError):
    """No package could be selected, or the selected package is unusable."""


@dataclass(frozen=True)
class SelectedPackage:
    """A package chosen for loading, with the evidence for why it was chosen."""

    filename: str
    path: Path
    cadence: str
    period: str
    sha256: str
    size_bytes: int
    accessions: tuple[str, ...]
    reason: str

    def as_record(self) -> dict[str, object]:
        return {
            "filename": self.filename,
            "cadence": self.cadence,
            "period": self.period,
            "sha256": self.sha256,
            "size_bytes": self.size_bytes,
            "accessions": list(self.accessions),
            "reason": self.reason,
        }


def package_members(path: Path) -> list[str]:
    """Every member name in the archive."""
    with zipfile.ZipFile(path) as archive:
        return archive.namelist()


def assert_members_present(path: Path) -> None:
    """Fail closed when a required member is missing.

    A package short a table would load partially and look successful. The count would simply be
    lower, which is indistinguishable from a quiet month.
    """
    present = set(package_members(path))
    missing = [m for m in REQUIRED_MEMBERS if m not in present]
    if missing:
        raise PackageSelectionError(
            f"{path.name} is missing required member(s): {', '.join(missing)}"
        )


def accessions_in_package(path: Path, cik: str | None = None) -> list[str]:
    """Accessions listed in the package's sub.tsv, optionally filtered to one CIK."""
    from .tsv import iter_rows

    wanted = str(int(cik)) if cik else None
    found: list[str] = []
    with zipfile.ZipFile(path) as archive:
        for row in iter_rows(archive, "sub.tsv"):
            if wanted is not None and row.get("cik") != wanted:
                continue
            adsh = row.get("adsh")
            if adsh:
                found.append(accession_dashed(adsh))
    return found


def period_sort_key(cadence: str, period: str) -> tuple[int, int, int]:
    """Order a mixed set of monthly and quarterly packages by the period each one ends in.

    The ledger writes monthly periods as `2025-10` and quarterly ones as `2025Q2`. Sorting those
    as raw strings compares `-` against `Q` and produces an ordering that happens to work today and
    is not a decision anyone made. Both forms are parsed to a year and an end month instead.

    The tie-break PREFERS THE QUARTERLY package. Monthly packages are deleted upstream after the
    quarterly consolidation is published, so a load whose recorded provenance names a monthly
    package becomes unreproducible from SEC the moment that deletion happens. When both hold the
    same filing, the durable one is the right citation.
    """
    text = period.strip().upper()
    if "Q" in text:
        year, _, quarter = text.partition("Q")
        return (int(year), int(quarter) * 3, 1 if cadence == "quarterly" else 0)
    year, _, month = text.partition("-")
    return (int(year), int(month), 1 if cadence == "quarterly" else 0)


def locate_filing(accession: str, *, package_root: Path, ledger: MirrorLedger) -> SelectedPackage:
    """Find the mirrored package whose sub.tsv lists this accession.

    Searches newest-first, because a filing is overwhelmingly likely to sit in a recent period,
    and stops at the first hit. Reading sub.tsv is cheap relative to the rest of the archive.
    """
    target = accession_dashed(accession)
    entries = sorted(
        ledger.entries.values(),
        key=lambda e: period_sort_key(e.cadence, e.period),
        reverse=True,
    )
    if not entries:
        raise PackageSelectionError("the mirror ledger is empty; nothing to search")

    for entry in entries:
        path = package_root / entry.storage_key
        if not path.is_file():
            continue
        try:
            with zipfile.ZipFile(path) as archive:
                if "sub.tsv" not in archive.namelist():
                    continue
                blob = archive.read("sub.tsv").decode("utf-8", errors="replace")
        except zipfile.BadZipFile as error:
            raise PackageSelectionError(f"{entry.filename} is not a readable archive") from error

        if target in blob or target.replace("-", "") in blob:
            assert_members_present(path)
            return SelectedPackage(
                filename=entry.filename,
                path=path,
                cadence=entry.cadence,
                period=entry.period,
                sha256=entry.sha256,
                size_bytes=entry.size_bytes,
                accessions=(target,),
                reason=(
                    f"sub.tsv in {entry.filename} lists {target}. Selected by reading the "
                    "package contents, not by deriving a period from the filing date: a filing "
                    "belongs to the period it was SUBMITTED in, which differs from the period it "
                    "reports on."
                ),
            )

    raise PackageSelectionError(
        f"no mirrored package lists accession {target}. Searched {len(entries)} ledger entries."
    )
