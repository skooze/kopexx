"""The entity and filing catalog a run is chosen from.

WHAT THIS IS IN PHASE 2. The 613-filing research corpus, read from a SUPPLIED manifest. It is not
the beta catalog: roadmap.md Phase 6 builds that from live discovery over the whole reporting
universe, and Phase 8 widens it. What it has to be today is honest about which entities and
filings this project can actually serve, because a search control that offers something the
product cannot process is worse than one that offers less.

NO FABRICATED IDENTITY. An entity's name, its former names and its tickers come from what EDGAR
returned when the corpus was acquired. Where an issuer has no current ticker — 68 of the 112 in
the corpus — it has none here, and no plausible reconstruction is substituted. A sampling label is
an INTENT and is never displayed as identity.

THE MANIFEST PATH IS SUPPLIED AND HAS NO DEFAULT, for the same reason the capability snapshot and
the qualifying-form set are supplied: a default path is how a stale artifact keeps answering after
the real one has moved.

JSON IS READ HERE AND THAT IS NOT A BOUNDARY VIOLATION. This manifest is host state describing
files on disk. It is never model-visible; ADR-0013 governs what a MODEL sees.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from packages.sec_identity import accession_dashed, cik_padded


@dataclass(frozen=True)
class PreservedFile:
    """One preserved artifact of a filing, as the corpus manifest records it."""

    filename: str
    sha256: str
    byte_count: int
    source_url: str
    local_path: str


@dataclass(frozen=True)
class FilingRecord:
    """One qualifying filing this project can actually process."""

    cik: str
    accession: str
    form_as_filed: str
    filing_date: str
    report_period: str | None
    issuer_label: str
    transport_era: str
    is_amendment: bool
    is_annual: bool
    form_variant: str
    package_file_count: int
    package_image_count: int
    primary_estimated_tokens: int
    files: tuple[PreservedFile, ...] = field(default_factory=tuple)

    def to_mapping(self) -> dict[str, Any]:
        return {
            "cik": self.cik,
            "accession": self.accession,
            "form_as_filed": self.form_as_filed,
            "filing_date": self.filing_date,
            "report_period": self.report_period,
            "issuer_label": self.issuer_label,
            "transport_era": self.transport_era,
            "is_amendment": self.is_amendment,
            "is_annual": self.is_annual,
            "form_variant": self.form_variant,
            "package_file_count": self.package_file_count,
            "package_image_count": self.package_image_count,
            "primary_estimated_tokens": self.primary_estimated_tokens,
        }


@dataclass(frozen=True)
class EntityRecord:
    """One issuer with at least one qualifying filing. An issuer with none never appears."""

    cik: str
    name: str
    tickers: tuple[str, ...]
    former_names: tuple[str, ...]
    sic_description: str
    earliest_filing_date: str
    latest_filing_date: str
    filing_count: int
    forms_present: tuple[str, ...]

    def to_mapping(self) -> dict[str, Any]:
        return {
            "cik": self.cik,
            "name": self.name,
            "tickers": list(self.tickers),
            "former_names": list(self.former_names),
            "sic_description": self.sic_description,
            "earliest_filing_date": self.earliest_filing_date,
            "latest_filing_date": self.latest_filing_date,
            "filing_count": self.filing_count,
            "forms_present": list(self.forms_present),
        }


class FilingCatalog(Protocol):
    """Whatever can answer which entities and filings exist."""

    def search_entities(self, query: str, *, limit: int = 20) -> list[EntityRecord]: ...

    def entity(self, cik: str) -> EntityRecord | None: ...

    def filings(
        self, cik: str, *, from_date: str | None = None, to_date: str | None = None
    ) -> list[FilingRecord]: ...

    def filing(self, cik: str, accession: str) -> FilingRecord | None: ...


class CorpusFilingCatalog:
    """A catalog over the preserved research corpus."""

    def __init__(self, records: list[dict[str, Any]]) -> None:
        self._filings: dict[tuple[str, str], FilingRecord] = {}
        self._by_cik: dict[str, list[FilingRecord]] = {}
        self._entities: dict[str, EntityRecord] = {}
        self._index(records)

    @classmethod
    def from_manifest(cls, path: str | Path) -> CorpusFilingCatalog:
        """Load from a supplied corpus manifest. No default path exists."""
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(raw, list):
            raise ValueError(f"{path} is not a list of filing records")
        return cls(raw)

    def _index(self, records: list[dict[str, Any]]) -> None:
        entity_rows: dict[str, list[dict[str, Any]]] = {}
        for row in records:
            cik = cik_padded(str(row["cik"]))
            accession = accession_dashed(str(row["accession"]))
            files = tuple(
                PreservedFile(
                    filename=str(f["filename"]),
                    sha256=str(f["sha256"]),
                    byte_count=int(f["raw_bytes"]),
                    source_url=str(f.get("source_url") or ""),
                    local_path=str(f["local_path"]),
                )
                for f in (row.get("files") or ())
                if f.get("filename") and f.get("local_path")
            )
            record = FilingRecord(
                cik=cik,
                accession=accession,
                form_as_filed=str(row["form_as_filed"]),
                filing_date=str(row["filing_date"]),
                report_period=str(row["report_period"]) if row.get("report_period") else None,
                issuer_label=str(row.get("issuer_name_current") or row.get("issuer_label") or ""),
                transport_era=str(row.get("transport_era") or ""),
                is_amendment=bool(row.get("is_amendment")),
                is_annual=bool(row.get("is_annual")),
                form_variant=str(row.get("form_variant") or ""),
                package_file_count=int(row.get("package_file_count") or 0),
                package_image_count=int(row.get("package_image_count") or 0),
                primary_estimated_tokens=int(row.get("primary_est_tokens_at_3_0") or 0),
                files=files,
            )
            self._filings[(cik, accession)] = record
            self._by_cik.setdefault(cik, []).append(record)
            entity_rows.setdefault(cik, []).append(row)

        for cik, rows in entity_rows.items():
            filings = sorted(self._by_cik[cik], key=lambda f: f.filing_date)
            # IDENTITY COMES FROM THE NEWEST ROW, NOT THE FIRST ONE IN THE FILE. Taking `rows[0]`
            # let manifest ORDER decide a displayed name: an issuer renamed between two
            # acquisitions, or a re-acquired corpus, would show whichever row happened to be
            # written first. This module's own rule is that a sampling label is an intent and
            # EDGAR is the authority, so the most recently filed row is the least wrong answer
            # available without asking EDGAR again.
            head = max(rows, key=lambda r: str(r.get("filing_date") or ""))
            self._entities[cik] = EntityRecord(
                cik=cik,
                name=str(head.get("issuer_name_current") or head.get("issuer_label") or ""),
                tickers=tuple(str(t) for t in (head.get("tickers_current") or ())),
                former_names=tuple(
                    str(n.get("name")) for n in (head.get("former_names") or ()) if n.get("name")
                ),
                sic_description=str(head.get("sic_description") or ""),
                earliest_filing_date=filings[0].filing_date,
                latest_filing_date=filings[-1].filing_date,
                filing_count=len(filings),
                forms_present=tuple(sorted({f.form_as_filed for f in filings})),
            )
        for records_for_cik in self._by_cik.values():
            records_for_cik.sort(key=lambda f: (f.filing_date, f.accession), reverse=True)

    @property
    def entity_count(self) -> int:
        return len(self._entities)

    @property
    def filing_count(self) -> int:
        return len(self._filings)

    def search_entities(self, query: str, *, limit: int = 20) -> list[EntityRecord]:
        """Match on current name, former names and current tickers. Nothing is invented.

        A ticker match ranks above a name match because a user who typed four capital letters
        meant a ticker. Beyond that the ordering is alphabetical, which is at least reproducible —
        a relevance score nobody specified would be a product decision made in a sort key.
        """
        needle = query.strip().lower()
        if not needle:
            return []
        exact_ticker: list[EntityRecord] = []
        name_match: list[EntityRecord] = []
        for entity in self._entities.values():
            if any(needle == t.lower() for t in entity.tickers):
                exact_ticker.append(entity)
            elif needle in entity.name.lower() or any(
                needle in n.lower() for n in entity.former_names
            ):
                name_match.append(entity)
        exact_ticker.sort(key=lambda e: e.name)
        name_match.sort(key=lambda e: e.name)
        return (exact_ticker + name_match)[:limit]

    def entity(self, cik: str) -> EntityRecord | None:
        return self._entities.get(cik_padded(cik))

    def filings(
        self, cik: str, *, from_date: str | None = None, to_date: str | None = None
    ) -> list[FilingRecord]:
        """Qualifying filings for one entity, newest first, bounded by an ISO date range."""
        found = list(self._by_cik.get(cik_padded(cik), ()))
        if from_date:
            found = [f for f in found if f.filing_date >= from_date]
        if to_date:
            found = [f for f in found if f.filing_date <= to_date]
        return found

    def filing(self, cik: str, accession: str) -> FilingRecord | None:
        """One filing, or None. A MALFORMED identity is None too, not an exception.

        The protocol promises `FilingRecord | None`, and `sec_identity` refuses a malformed CIK or
        accession with its own typed error. Letting that escape made a bad request from a browser
        surface as an identity exception from two packages away instead of as "no such filing".
        """
        try:
            key = (cik_padded(cik), accession_dashed(accession))
        except ValueError:
            return None
        return self._filings.get(key)


class BenchmarkFilingCatalog:
    """A catalog over the SUPPLIED benchmark-filing contract.

    WHY A SECOND CATALOG RATHER THAN A ROW IN THE FIRST. The research corpus manifest is the output
    of a sampling run: which filings it holds is a property of how that run drew its sample, and it
    lives under `var/`, untracked, regenerated by a Phase 0 tool. A BENCHMARK filing is chosen
    deliberately and must be reachable on any checkout, so its identity is tracked source that a
    reviewer can read — `docs/benchmark/benchmark-filings.yaml`.

    IT CARRIES IDENTITY AND NOT BYTES. The preserved package is resolved through the ordinary source
    inventory, hash-verified on every read, and a missing member is fetched under the normal
    raw-first rules. A catalog that also claimed to know where the bytes were would be a second
    place for that fact to drift.
    """

    def __init__(self, records: list[dict[str, Any]]) -> None:
        self._filings: dict[tuple[str, str], FilingRecord] = {}
        for row in records:
            cik = cik_padded(str(row["cik"]))
            accession = accession_dashed(str(row["accession"]))
            self._filings[(cik, accession)] = FilingRecord(
                cik=cik,
                accession=accession,
                form_as_filed=str(row["form_as_filed"]),
                filing_date=str(row["filing_date"]),
                report_period=(str(row["report_period"]) if row.get("report_period") else None),
                issuer_label=str(row["issuer_label"]),
                transport_era=str(row["transport_era"]),
                is_amendment=bool(row.get("is_amendment")),
                is_annual=bool(row.get("is_annual")),
                form_variant="",
                package_file_count=0,
                package_image_count=0,
                primary_estimated_tokens=0,
            )

    @classmethod
    def from_manifest(cls, path: str | Path) -> BenchmarkFilingCatalog:
        """Load from the supplied benchmark contract. No default path exists."""
        from packages.llm_gateway import parse_yaml, require_mapping  # noqa: PLC0415 - single home

        document = require_mapping(parse_yaml(Path(path).read_text(encoding="utf-8")))
        rows = document.get("filings")
        if not isinstance(rows, list) or not rows:
            raise ValueError(f"{path} declares no benchmark filings")
        return cls([row for row in rows if isinstance(row, dict)])

    def search_entities(self, query: str, *, limit: int = 20) -> list[EntityRecord]:
        """A benchmark filing is opened by identity, never found by browsing."""
        return []

    def entity(self, cik: str) -> EntityRecord | None:
        return None

    def filings(
        self, cik: str, *, from_date: str | None = None, to_date: str | None = None
    ) -> list[FilingRecord]:
        found = [f for f in self._filings.values() if f.cik == cik_padded(cik)]
        return sorted(found, key=lambda f: f.filing_date)

    def filing(self, cik: str, accession: str) -> FilingRecord | None:
        return self._filings.get((cik_padded(cik), accession_dashed(accession)))


class CompositeFilingCatalog:
    """Ask each catalog in order and take the first that holds the filing.

    ORDER IS THE CALLER'S CHOICE AND IT MATTERS. The research corpus comes first, so a filing that
    is genuinely in the sampled corpus keeps the richer record the sampling run measured — package
    counts, image counts, the primary document's estimated size. The benchmark contract answers
    only for what the corpus does not hold.

    THIS IS NOT A FALLBACK IN THE SENSE THIS REPOSITORY FORBIDS. A fallback is how a stale artifact
    keeps answering after the real one has moved; both catalogs here are SUPPLIED, both are read
    fresh, and neither substitutes a different filing for the one that was asked for.
    """

    def __init__(self, *catalogs: FilingCatalog) -> None:
        self._catalogs = catalogs

    def search_entities(self, query: str, *, limit: int = 20) -> list[EntityRecord]:
        found: list[EntityRecord] = []
        seen: set[str] = set()
        for catalog in self._catalogs:
            for entity in catalog.search_entities(query, limit=limit):
                if entity.cik not in seen:
                    seen.add(entity.cik)
                    found.append(entity)
        return found[:limit]

    def entity(self, cik: str) -> EntityRecord | None:
        for catalog in self._catalogs:
            found = catalog.entity(cik)
            if found is not None:
                return found
        return None

    def filings(
        self, cik: str, *, from_date: str | None = None, to_date: str | None = None
    ) -> list[FilingRecord]:
        found: list[FilingRecord] = []
        seen: set[tuple[str, str]] = set()
        for catalog in self._catalogs:
            for filing in catalog.filings(cik, from_date=from_date, to_date=to_date):
                key = (filing.cik, filing.accession)
                if key not in seen:
                    seen.add(key)
                    found.append(filing)
        return sorted(found, key=lambda f: f.filing_date)

    def filing(self, cik: str, accession: str) -> FilingRecord | None:
        for catalog in self._catalogs:
            found = catalog.filing(cik, accession)
            if found is not None:
                return found
        return None
