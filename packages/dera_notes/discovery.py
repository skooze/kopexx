"""Discovery of SEC DERA Financial Statement and Notes dataset packages.

SEC-INVARIANT: dataset filenames MUST be discovered by scraping the authoritative listing page.
They must never be generated from a pattern. Three known 2010 packages carry irregular suffixes
(2010q1_notes_1.zip, 2010q2_notes_0.zip, 2010q3_notes_0.zip) that any generated-name downloader
will miss with a 404. Vintage-specific metadata filenames vary the same way.

TIME-SENSITIVE: SEC retains only a rolling twelve months of monthly packages and deletes them
once consolidated into quarterly packages. A period reachable only as a monthly package becomes
permanently unreachable if it is deleted before its quarterly consolidation is published. The
mirror therefore retains monthly packages even after the corresponding quarterly package arrives.
See docs/runbooks/dera-mirror.md.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from urllib.parse import urljoin

from .errors import DeraDiscoveryError

NOTES_LANDING_URL = (
    "https://www.sec.gov/data-research/sec-markets-data/financial-statement-notes-data-sets"
)

# Anchor href extraction. Deliberately permissive about surrounding markup because the landing
# page layout changes; the constraint that matters is that we read hrefs rather than invent them.
_HREF = re.compile(r'href\s*=\s*["\']([^"\']+\.zip)["\']', re.IGNORECASE)

_QUARTERLY = re.compile(r"(\d{4})q([1-4])_notes(?:_\d+)?\.zip$", re.IGNORECASE)
_MONTHLY = re.compile(r"(\d{4})_(\d{2})_notes(?:_\d+)?\.zip$", re.IGNORECASE)


class PackageCadence(StrEnum):
    """Whether a package covers a month or a quarter."""

    MONTHLY = "monthly"
    QUARTERLY = "quarterly"


@dataclass(frozen=True)
class DeraPackage:
    """One discovered dataset package."""

    url: str
    filename: str
    cadence: PackageCadence
    period: str
    year: int

    @property
    def ledger_key(self) -> str:
        """Return the stable storage key for this package."""
        return f"dera/notes/{self.cadence.value}/{self.filename}"


def classify_filename(filename: str) -> tuple[PackageCadence, str, int] | None:
    """Classify a discovered filename into cadence, period label, and year.

    Returns None when the filename is not a NOTES package. Handles the irregular numeric suffix
    present on three 2010 packages.
    """
    name = filename.strip().split("/")[-1]
    quarterly = _QUARTERLY.search(name)
    if quarterly:
        year, quarter = int(quarterly.group(1)), quarterly.group(2)
        return PackageCadence.QUARTERLY, f"{year}Q{quarter}", year
    monthly = _MONTHLY.search(name)
    if monthly:
        year, month = int(monthly.group(1)), monthly.group(2)
        return PackageCadence.MONTHLY, f"{year}-{month}", year
    return None


def discover_packages(landing_html: str, *, base_url: str = NOTES_LANDING_URL) -> list[DeraPackage]:
    """Extract every NOTES package from the authoritative listing page.

    Raises DeraDiscoveryError when the page yields no packages at all, which means the layout
    changed and silent zero-discovery would otherwise look like "nothing new to mirror".
    """
    if not landing_html or not landing_html.strip():
        raise DeraDiscoveryError("empty listing page; cannot discover DERA packages")

    seen: dict[str, DeraPackage] = {}
    for href in _HREF.findall(landing_html):
        filename = href.strip().split("/")[-1]
        classified = classify_filename(filename)
        if classified is None:
            continue
        cadence, period, year = classified
        url = urljoin(base_url, href.strip())
        if filename not in seen:
            seen[filename] = DeraPackage(
                url=url, filename=filename, cadence=cadence, period=period, year=year
            )

    if not seen:
        raise DeraDiscoveryError(
            "no DERA NOTES packages found on the listing page; the page layout may have "
            "changed. Filenames must never be generated as a fallback."
        )
    return sorted(seen.values(), key=lambda p: (p.year, p.period, p.filename))
