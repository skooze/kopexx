"""Register the rows a DERA fact load must attach to.

`xbrl_fact` has foreign keys to `issuer` and `filing`. Loading a fact therefore presupposes that
both rows exist, and until this module they did not: Sprint 3's acquisition wrote objects to the
store and provenance to a manifest, never to PostgreSQL.

SCOPE. Stage 1 is one issuer. A monthly DERA package describes thousands of companies, and
registering all of them is the issuer universe — Stage 2 phase W-1, out of scope by ADR-0015. So
registration is per-accession: the caller names a filing, and sub.tsv supplies its metadata.

WHAT DERA CAN AND CANNOT SAY. sub.tsv is authoritative for what it carries — form, period, fiscal
year and period, filing date, fiscal year end, name, SIC, state of incorporation. It carries
nothing about the filing's era, its primary document, or the objects acquired from EDGAR, so those
columns are left NULL rather than guessed. `packages/filing_acquisition` owns them and will fill
them when acquisition registration is written.
"""

from __future__ import annotations

import uuid
import zipfile
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine

from packages.sec_identity import accession_dashed, cik_padded

from .errors import DeraError
from .ledger import MirrorLedger
from .tsv import as_date, as_int, clean, iter_rows

SUB_MEMBER = "sub.tsv"


class RegistrationError(DeraError):
    """A row the load depends on could not be registered."""


@dataclass(frozen=True)
class SubmissionRecord:
    """One sub.tsv row, reduced to what `issuer` and `filing` model."""

    accession: str
    cik: str
    name: str
    sic: str | None
    fiscal_year_end: str | None
    state_of_incorporation: str | None
    country_of_incorporation: str | None
    form: str
    filed: date | None
    period: date | None
    fiscal_year: int | None
    fiscal_period: str | None
    instance: str | None
    detail: bool
    prior_report: bool

    @property
    def is_amendment(self) -> bool:
        return self.form.upper().endswith("/A")

    @property
    def is_xbrl(self) -> bool:
        """DERA names the XBRL instance it derived the package from.

        Every submission in a NOTES package is an XBRL filer by construction, so this is close to
        a constant, but it is read from the row rather than assumed: an empty `instance` would mean
        the package's own provenance for this filing is incomplete and that should be visible.
        """
        return bool(self.instance)

    @property
    def is_inline_xbrl(self) -> bool:
        """SEC names the instance it extracts from an inline-XBRL document `<doc>_htm.xml`.

        A standalone-XBRL-era filing carries its instance directly, under a name that does not
        end in `_htm.xml`. This is the distinction, read from DERA's own filename rather than
        inferred from the filing date, which would misclassify early and late adopters.
        """
        return self.instance is not None and self.instance.rstrip(".").endswith("_htm.xml")


def read_submission(archive: zipfile.ZipFile, accession: str) -> SubmissionRecord:
    """Find one accession in sub.tsv and reduce it to a registration record."""
    target = accession_dashed(accession)
    undashed = target.replace("-", "")

    for row in iter_rows(archive, SUB_MEMBER):
        raw = (row.get("adsh") or "").strip()
        if raw not in (target, undashed):
            continue
        return SubmissionRecord(
            accession=target,
            cik=cik_padded(row.get("cik") or "0"),
            name=clean(row.get("name")) or "",
            sic=clean(row.get("sic")),
            # DERA writes the fiscal year end as MMDD, which is exactly what the column stores.
            fiscal_year_end=clean(row.get("fye")),
            state_of_incorporation=clean(row.get("stprinc")),
            country_of_incorporation=clean(row.get("countryinc")),
            form=clean(row.get("form")) or "",
            filed=as_date(row.get("filed")),
            period=as_date(row.get("period")),
            fiscal_year=as_int(row.get("fy")),
            fiscal_period=clean(row.get("fp")),
            instance=clean(row.get("instance")),
            detail=(clean(row.get("detail")) == "1"),
            prior_report=(clean(row.get("prevrpt")) == "1"),
        )

    raise RegistrationError(f"{SUB_MEMBER} does not list {target}")


def _upsert_issuer(connection: Connection, record: SubmissionRecord) -> uuid.UUID:
    """Insert the issuer, or return the existing one.

    CIK is identity and is already UNIQUE, so this is safe to repeat. An existing row is not
    overwritten: DERA's copy of a company name is one observation among several, and the issuer
    registry that arbitrates between them is Stage 2 work.
    """
    existing = connection.execute(
        text("SELECT issuer_id FROM issuer WHERE cik = :cik"), {"cik": record.cik}
    ).scalar()
    if existing is not None:
        return uuid.UUID(str(existing))

    return uuid.UUID(
        str(
            connection.execute(
                text(
                    "INSERT INTO issuer (issuer_id, cik, legal_name, sic, fiscal_year_end,"
                    " state_of_incorporation, country, is_active)"
                    " VALUES (gen_random_uuid(), :cik, :name, :sic, :fye, :stprinc, :country, true)"
                    " RETURNING issuer_id"
                ),
                {
                    "cik": record.cik,
                    "name": record.name,
                    "sic": record.sic,
                    "fye": record.fiscal_year_end,
                    "stprinc": record.state_of_incorporation,
                    "country": record.country_of_incorporation,
                },
            ).scalar_one()
        )
    )


def _upsert_filing(
    connection: Connection, record: SubmissionRecord, issuer_id: uuid.UUID
) -> uuid.UUID:
    """Insert the filing, or return the existing one. Accession is UNIQUE."""
    existing = connection.execute(
        text("SELECT filing_id FROM filing WHERE accession = :a"), {"a": record.accession}
    ).scalar()
    if existing is not None:
        return uuid.UUID(str(existing))

    if record.filed is None:
        raise RegistrationError(
            f"{record.accession} has no filing date in sub.tsv; filing.filing_date is NOT NULL"
        )

    return uuid.UUID(
        str(
            connection.execute(
                text(
                    "INSERT INTO filing (filing_id, issuer_id, cik, accession, form, filing_date,"
                    " report_date, fiscal_year, fiscal_period, fiscal_year_end, is_amendment,"
                    " is_xbrl, is_inline_xbrl, processing_state, footnote_status,"
                    " reconciliation_status)"
                    " VALUES (gen_random_uuid(), :issuer_id, :cik, :accession, :form, :filed,"
                    " :period, :fy, :fp, :fye, :amendment, :is_xbrl, :is_inline_xbrl,"
                    " 'DISCOVERED', 'NOT_STARTED', 'NOT_ATTEMPTED') RETURNING filing_id"
                ),
                {
                    "issuer_id": issuer_id,
                    "cik": record.cik,
                    "accession": record.accession,
                    "form": record.form,
                    "filed": record.filed,
                    "period": record.period,
                    "fy": record.fiscal_year,
                    "fp": record.fiscal_period,
                    "fye": record.fiscal_year_end,
                    "amendment": record.is_amendment,
                    "is_xbrl": record.is_xbrl,
                    "is_inline_xbrl": record.is_inline_xbrl,
                    # `era` is deliberately left NULL. DERA does not describe the filing's
                    # acquisition era, and filing_acquisition owns that column.
                },
            ).scalar_one()
        )
    )


@dataclass(frozen=True)
class FilingContext:
    """The parent rows a fact attaches to, plus the filing-level columns it copies."""

    issuer_id: uuid.UUID
    filing_id: uuid.UUID
    cik: str
    accession: str
    form: str
    filing_date: date
    report_date: date | None
    fiscal_year: int | None
    fiscal_period: str | None


def register_filing(engine: Engine, package_path: Path, accession: str) -> FilingContext:
    """Ensure the issuer and filing rows exist, and return what the loader needs from them."""
    with zipfile.ZipFile(package_path) as archive:
        record = read_submission(archive, accession)

    with engine.begin() as connection:
        issuer_id = _upsert_issuer(connection, record)
        filing_id = _upsert_filing(connection, record, issuer_id)
        row = (
            connection.execute(
                text(
                    "SELECT cik, form, filing_date, report_date, fiscal_year, fiscal_period"
                    " FROM filing WHERE filing_id = :id"
                ),
                {"id": filing_id},
            )
            .mappings()
            .one()
        )

    return FilingContext(
        issuer_id=issuer_id,
        filing_id=filing_id,
        cik=row["cik"],
        accession=record.accession,
        form=row["form"],
        filing_date=row["filing_date"],
        report_date=row["report_date"],
        fiscal_year=row["fiscal_year"],
        fiscal_period=row["fiscal_period"],
    )


def register_mirror_ledger(engine: Engine, ledger: MirrorLedger, package_root: Path) -> int:
    """Copy the JSON mirror ledger into `dera_package`, which is where the load ledger lives.

    Sprint 1 wrote the mirror ledger to JSON because there was no database. There is one now, and
    `loaded_at` — the column that records which packages have been loaded — is on this table. Two
    ledgers with different contents would be two sources of truth, so the JSON one is copied in and
    from here on the database is authoritative for load state.

    Returns the number of rows inserted. Re-running inserts none.
    """
    inserted = 0
    with engine.begin() as connection:
        known = {row[0] for row in connection.execute(text("SELECT filename FROM dera_package"))}
        for entry in ledger.entries.values():
            if entry.filename in known:
                continue
            path = package_root / entry.storage_key
            connection.execute(
                text(
                    "INSERT INTO dera_package (id, filename, source_url, cadence, period, sha256,"
                    " size_bytes, storage_key, format_version, zip_validated, hash_validated,"
                    " retrieved_at)"
                    " VALUES (gen_random_uuid(), :filename, :url, :cadence, :period, :sha256,"
                    " :size_bytes, :storage_key, :format_version, :zip_validated, true,"
                    " :retrieved_at)"
                ),
                {
                    "filename": entry.filename,
                    "url": entry.url,
                    "cadence": entry.cadence,
                    "period": entry.period,
                    "sha256": entry.sha256,
                    "size_bytes": entry.size_bytes,
                    "storage_key": entry.storage_key,
                    "format_version": entry.format_version,
                    # Only claim ZIP validation for archives actually present on this host.
                    "zip_validated": path.is_file(),
                    "retrieved_at": entry.retrieved_at,
                },
            )
            inserted += 1
    return inserted
