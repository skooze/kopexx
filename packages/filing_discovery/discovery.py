"""Discover every 10-K and 10-Q an issuer has filed.

SEC-INVARIANT: `filings.recent` in the submissions payload is capped at 1,000 entries. Apple hits
that cap exactly, with 1,238 further filings in an overflow shard reaching back to 1994. Reading
only `recent` silently truncates history to the last few years, and the truncation looks
identical to a company that simply has not filed much.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date

from packages.sec_identity import (
    accession_dashed,
    cik_padded,
    submissions_shard_url,
    submissions_url,
)

from .errors import SubmissionsShapeError

# Forms that constitute the covered corpus. 10-K405 is a historical annual-report variant used
# through 2002; Apple filed two. Excluding it would leave a two-year hole in the annual series
# that no later check would notice.
ANNUAL_FORMS = ("10-K", "10-K405", "10-KSB")
QUARTERLY_FORMS = ("10-Q", "10-QSB")

# The parallel-array keys we require. SEC returns column arrays, not row objects.
_REQUIRED_KEYS = ("accessionNumber", "filingDate", "form")


def is_covered_form(form: str) -> bool:
    """True for a 10-K or 10-Q in any of its variants, including amendments."""
    base = form.split("/")[0].strip().upper()
    return base in ANNUAL_FORMS or base in QUARTERLY_FORMS


def is_amendment(form: str) -> bool:
    return form.strip().upper().endswith("/A")


def classify_era(*, filing_date: date, is_xbrl: bool, is_inline_xbrl: bool) -> str:
    """Which acquisition strategy this filing needs.

    HISTORICAL-FORMAT: the boundaries are behavioural, not cosmetic. Inline XBRL filings carry
    their narrative and every linkbase in one `-xbrl.zip`. Older XBRL filings need the primary
    document fetched separately. Pre-2001 filings are PEM-armored inside the complete submission
    text file and have no primary document name at all.
    """
    if is_inline_xbrl:
        return "inline_xbrl"
    if is_xbrl:
        return "standalone_xbrl"
    if filing_date >= date(2001, 1, 1):
        return "html_no_xbrl"
    return "pem_armored"


@dataclass(frozen=True)
class DiscoveredFiling:
    """One filing as the submissions API describes it, before anything is downloaded."""

    cik: str
    accession: str
    form: str
    filing_date: date
    report_date: date | None
    primary_document: str
    is_xbrl: bool
    is_inline_xbrl: bool
    size_bytes: int | None
    era: str
    source: str

    @property
    def is_amendment(self) -> bool:
        return is_amendment(self.form)

    @property
    def is_annual(self) -> bool:
        return self.form.split("/")[0].strip().upper() in ANNUAL_FORMS

    def as_record(self) -> dict[str, object]:
        """A flat record for logging and manifests."""
        return {
            "cik": self.cik,
            "accession": self.accession,
            "form": self.form,
            "filing_date": self.filing_date.isoformat(),
            "report_date": self.report_date.isoformat() if self.report_date else None,
            "primary_document": self.primary_document,
            "is_inline_xbrl": self.is_inline_xbrl,
            "era": self.era,
            "size_bytes": self.size_bytes,
            "source": self.source,
        }


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    return date.fromisoformat(value[:10])


def _column(block: dict, key: str, index: int) -> object:
    values = block.get(key)
    if not isinstance(values, list) or index >= len(values):
        return None
    return values[index]


def _rows(block: dict, cik: str, source: str) -> Iterator[DiscoveredFiling]:
    """Turn one parallel-array block into filings, keeping only covered forms."""
    missing = [k for k in _REQUIRED_KEYS if k not in block]
    if missing:
        raise SubmissionsShapeError(
            f"submissions block {source!r} is missing required keys: {', '.join(missing)}"
        )

    for index, form in enumerate(block["form"]):
        if not is_covered_form(str(form)):
            continue
        filing_date = _parse_date(str(_column(block, "filingDate", index) or ""))
        if filing_date is None:
            raise SubmissionsShapeError(
                f"filing {block['accessionNumber'][index]!r} in {source!r} has no filing date"
            )
        is_inline = bool(_column(block, "isInlineXBRL", index))
        is_xbrl = bool(_column(block, "isXBRL", index))
        size = _column(block, "size", index)
        yield DiscoveredFiling(
            cik=cik,
            accession=accession_dashed(str(block["accessionNumber"][index])),
            form=str(form),
            filing_date=filing_date,
            report_date=_parse_date(_column(block, "reportDate", index)),  # type: ignore[arg-type]
            # SEC-INVARIANT: pre-2001 filings have an EMPTY primary document. Building a URL from
            # it returns HTTP 200 with a directory listing, which is a silent corruption rather
            # than an error. The empty string is preserved so the acquirer can route on it.
            primary_document=str(_column(block, "primaryDocument", index) or ""),
            is_xbrl=is_xbrl,
            is_inline_xbrl=is_inline,
            size_bytes=int(size) if isinstance(size, int | str) and str(size).isdigit() else None,
            era=classify_era(filing_date=filing_date, is_xbrl=is_xbrl, is_inline_xbrl=is_inline),
            source=source,
        )


def discover_filings(client, cik: str | int) -> list[DiscoveredFiling]:
    """Every covered filing for one issuer, newest first.

    Reads `filings.recent`, then every overflow shard named in `filings.files`. Deduplicates by
    accession, because a shard boundary can repeat an entry.
    """
    padded = cik_padded(cik)
    payload = json.loads(client.get_text(submissions_url(padded)))

    filings_block = payload.get("filings")
    if not isinstance(filings_block, dict) or "recent" not in filings_block:
        raise SubmissionsShapeError(f"submissions payload for CIK {padded} has no filings.recent")

    found: dict[str, DiscoveredFiling] = {}
    for filing in _rows(filings_block["recent"], padded, "recent"):
        found[filing.accession] = filing

    for shard in filings_block.get("files") or []:
        name = shard.get("name")
        if not name:
            continue
        shard_payload = json.loads(client.get_text(submissions_shard_url(name)))
        for filing in _rows(shard_payload, padded, name):
            found.setdefault(filing.accession, filing)

    return sorted(found.values(), key=lambda f: (f.filing_date, f.accession), reverse=True)


def issuer_profile(client, cik: str | int) -> dict[str, object]:
    """Identity fields from the submissions payload, without the filing arrays."""
    padded = cik_padded(cik)
    payload = json.loads(client.get_text(submissions_url(padded)))
    return {
        "cik": padded,
        "legal_name": payload.get("name"),
        "sic": payload.get("sic"),
        "sic_description": payload.get("sicDescription"),
        "fiscal_year_end": payload.get("fiscalYearEnd"),
        "state_of_incorporation": payload.get("stateOfIncorporation"),
        "tickers": tuple(payload.get("tickers") or ()),
        "exchanges": tuple(payload.get("exchanges") or ()),
        "former_names": tuple(n.get("name") for n in payload.get("formerNames") or ()),
    }
