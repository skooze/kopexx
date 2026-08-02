"""Load one filing's DERA facts into the append-only fact lake.

SCOPE. Per accession, not per package. `xbrl_fact` has foreign keys to `issuer` and `filing`, so
loading every company in a monthly package would first require registering thousands of issuers —
that is the issuer universe, Stage 2 phase W-1, and out of scope by ADR-0015.

IDEMPOTENCY IS BY CONTENT. A rerun re-reads the package, recomputes each row's DERA natural key,
and inserts only keys the database does not already hold. A `loaded_at` timestamp is a report of
what happened, never a reason to skip work: a bookkeeping flag set by a run that half-failed would
make the gap permanent and invisible.

RESTART SAFETY. Everything is one transaction. A crash mid-load rolls back to zero rows with the
ledger unmarked, so a failed load is distinguishable from a complete one by inspection rather than
by trust.

CONCURRENCY. A transaction-scoped advisory lock keyed on the accession serializes two loaders of
the same filing. Without it, both could read the same empty existing-key set and both insert. The
lock is released when the transaction ends, including on rollback.
"""

from __future__ import annotations

import hashlib
import logging
import zipfile
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.engine import Engine

from packages.observability import get_logger, log_event
from packages.storage import sha256_file

from .dimensions import DIM_MEMBER, DimensionIndex
from .errors import DeraError
from .normalize import NormalizedFact, normalize_fact
from .registration import FilingContext
from .selection import REQUIRED_MEMBERS, SelectedPackage, assert_members_present
from .tsv import count_rows, iter_rows
from .validate import Rejection, violations

logger = get_logger("fintek.dera.loader")

FACT_MEMBER = "num.tsv"
SOURCE_DATASET = "dera_notes"

# Nothing has validated these facts. The validation pipeline is Sprint 5, and writing 'VALID' here
# would be a claim no code in this repository has earned. See normalize.py on why DERA periods in
# particular are approximations awaiting the XBRL instance.
INITIAL_VALIDATION_STATUS = "UNVALIDATED"

_INSERT = text(
    "INSERT INTO xbrl_fact (fact_id, issuer_id, cik, filing_id, accession, form, filing_date,"
    " report_date, fiscal_year, fiscal_period, taxonomy, namespace, concept, value_as_filed,"
    " value_numeric, unit, scale, sign, period_type, period_start, period_end, instant_date,"
    " duration_days, duration_months, dimensions, segment, coregistrant, source_dataset,"
    " source_row_id, filed_at, is_latest_selected, validation_status)"
    " VALUES (gen_random_uuid(), :issuer_id, :cik, :filing_id, :accession, :form, :filing_date,"
    " :report_date, :fiscal_year, :fiscal_period, :taxonomy, :namespace, :concept,"
    " :value_as_filed, :value_numeric, :unit, :scale, :sign, :period_type, :period_start,"
    " :period_end, :instant_date, :duration_days, :duration_months, CAST(:dimensions AS jsonb),"
    " :segment, :coregistrant, :source_dataset, :source_row_id, :filed_at, :is_latest_selected,"
    " :validation_status)"
)


class LoadError(DeraError):
    """The load could not proceed, and left nothing behind."""


def advisory_lock_key(accession: str) -> int:
    """A stable signed 64-bit lock key for one accession.

    `pg_advisory_xact_lock` takes a bigint. PostgreSQL's `hashtext()` would produce one, but it is
    an internal function with no compatibility guarantee across versions, and a lock key that
    changes between servers silently stops serializing anything.

    Python's own `hash()` is worse: it is salted per process, so two loaders of the same accession
    would take different locks and both proceed.

    SHA-256 truncated to eight bytes is deterministic everywhere and forever.
    """
    digest = hashlib.sha256(f"dera_load:{accession}".encode()).digest()[:8]
    return int.from_bytes(digest, "big", signed=True)


@dataclass
class ReadResult:
    """What came out of the package, before anything touched the database."""

    rows_matched: int = 0
    facts: list[NormalizedFact] = field(default_factory=list)
    rejections: list[Rejection] = field(default_factory=list)
    duplicate_keys: list[str] = field(default_factory=list)
    unknown_dimension_hashes: list[str] = field(default_factory=list)
    truncated_dimension_hashes: list[str] = field(default_factory=list)
    member_rows: dict[str, int] = field(default_factory=dict)

    @property
    def accepted(self) -> int:
        return len(self.facts)

    @property
    def rejected(self) -> int:
        return len(self.rejections) + len(self.duplicate_keys)

    @property
    def value_total(self) -> Decimal:
        """Sum of every numeric value accepted. Reconciled against the database after the load."""
        return sum((f.value_numeric for f in self.facts if f.value_numeric is not None), Decimal(0))


@dataclass
class LoadResult:
    """Everything the load did, and everything reconciliation needs to check it."""

    package: str
    package_sha256: str
    period: str
    accession: str
    read: ReadResult
    rows_inserted: int = 0
    rows_already_present: int = 0
    rows_in_database: int = 0
    database_value_total: Decimal = Decimal(0)
    started_at: str = ""
    completed_at: str = ""
    state: str = "PENDING"

    @property
    def duration_seconds(self) -> float:
        if not (self.started_at and self.completed_at):
            return 0.0
        start = datetime.fromisoformat(self.started_at)
        end = datetime.fromisoformat(self.completed_at)
        return (end - start).total_seconds()

    def as_record(self) -> dict[str, object]:
        return {
            "package": self.package,
            "package_sha256": self.package_sha256,
            "period": self.period,
            "accession": self.accession,
            "member_rows": dict(self.read.member_rows),
            "rows_matched": self.read.rows_matched,
            "rows_accepted": self.read.accepted,
            "rows_rejected": self.read.rejected,
            "rows_inserted": self.rows_inserted,
            "rows_already_present": self.rows_already_present,
            "rows_in_database": self.rows_in_database,
            "source_value_total": str(self.read.value_total),
            "database_value_total": str(self.database_value_total),
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "duration_seconds": round(self.duration_seconds, 3),
            "state": self.state,
        }


def verify_package(selected: SelectedPackage) -> str:
    """Re-hash the archive and confirm every required member is present.

    The mirror ledger recorded a hash at download time. Trusting it here would mean a file that
    rotted on disk since then loads silently, and a fact lake is exactly the place where that
    would go unnoticed for years.
    """
    assert_members_present(selected.path)
    actual = sha256_file(selected.path)
    if actual != selected.sha256:
        raise LoadError(
            f"{selected.filename} hash mismatch: ledger has {selected.sha256}, "
            f"the file on disk hashes to {actual}. Refusing to load a package that changed "
            "since it was mirrored."
        )
    return actual


def read_package(
    selected: SelectedPackage,
    accession: str,
    *,
    cik: str,
    count_all_members: bool = True,
) -> ReadResult:
    """Parse, normalize, and validate every fact row belonging to one accession.

    Reads the archive exactly once and holds only the matching rows. A monthly num.tsv is 261 MB
    and around three million rows; one filing's share of that is a few thousand.
    """
    result = ReadResult()
    undashed = accession.replace("-", "")

    with zipfile.ZipFile(selected.path) as archive:
        names = set(archive.namelist())
        if count_all_members:
            for member in REQUIRED_MEMBERS:
                result.member_rows[member] = count_rows(archive, member)

        if DIM_MEMBER in names:
            index = DimensionIndex.from_archive(archive)
        else:
            # Not fatal, but not silent either: every fact would look consolidated.
            log_event(
                logger,
                logging.WARNING,
                "dera package has no dim.tsv; dimensional facts cannot be distinguished",
                package=selected.filename,
            )
            index = DimensionIndex.empty()

        seen: set[str] = set()
        for row in iter_rows(archive, FACT_MEMBER):
            if (row.get("adsh") or "").strip() not in (accession, undashed):
                continue
            result.rows_matched += 1

            digest = (row.get("dimh") or "").strip()
            if not index.is_known(digest):
                result.unknown_dimension_hashes.append(digest)
            if index.is_truncated(digest):
                result.truncated_dimension_hashes.append(digest)

            fact = normalize_fact(
                row,
                cik=cik,
                dimensions=index.resolve(digest),
                segment=index.raw_segments(digest),
            )
            if fact is None:
                result.rejections.append(
                    Rejection(
                        source_row_id="",
                        concept=(row.get("tag") or ""),
                        reasons=("row_is_not_a_fact: missing accession, tag, or value",),
                    )
                )
                continue

            broken = violations(fact)
            if broken:
                result.rejections.append(Rejection.create(fact, broken))
                continue

            if fact.source_row_id in seen:
                # A duplicate of DERA's own primary key inside one package. Counted, not loaded
                # twice, and surfaced because it would mean the natural key is not what the
                # documentation says it is.
                result.duplicate_keys.append(fact.source_row_id)
                continue

            seen.add(fact.source_row_id)
            result.facts.append(fact)

    return result


def _bind(fact: NormalizedFact, context: FilingContext) -> dict[str, object]:
    """One row's INSERT parameters.

    Filing-level columns are copied from the filing row, never from the fact row: DERA's own
    documentation warns that `fy` and `fp` describe the submission rather than the fact, and the
    schema comments on those columns say the same.
    """
    import json

    return {
        "issuer_id": context.issuer_id,
        "cik": fact.cik,
        "filing_id": context.filing_id,
        "accession": fact.accession,
        "form": context.form,
        "filing_date": context.filing_date,
        "report_date": context.report_date,
        "fiscal_year": context.fiscal_year,
        "fiscal_period": context.fiscal_period,
        "taxonomy": fact.taxonomy,
        "namespace": fact.namespace,
        "concept": fact.concept,
        "value_as_filed": fact.value_as_filed,
        "value_numeric": fact.value_numeric,
        "unit": fact.unit,
        "scale": fact.scale,
        "sign": fact.sign,
        "period_type": fact.period_type,
        "period_start": fact.period_start,
        "period_end": fact.period_end,
        "instant_date": fact.instant_date,
        "duration_days": fact.duration_days,
        "duration_months": fact.duration_months,
        "dimensions": json.dumps(fact.dimensions, sort_keys=True),
        "segment": fact.segment,
        "coregistrant": fact.coregistrant,
        "source_dataset": SOURCE_DATASET,
        "source_row_id": fact.source_row_id,
        # The DERA package does not carry a submission timestamp at fact granularity. The filing
        # date is the observation time, and it is what the append-only ordering uses.
        "filed_at": datetime.combine(context.filing_date, datetime.min.time(), tzinfo=UTC),
        # Selecting the latest observation is a pure function over the observation set and belongs
        # to the fact lake (Sprint 6). Claiming it here, with one source loaded, would be wrong the
        # moment a second source arrives.
        "is_latest_selected": False,
        "validation_status": INITIAL_VALIDATION_STATUS,
    }


def load_facts(
    engine: Engine,
    selected: SelectedPackage,
    context: FilingContext,
    *,
    batch_size: int = 2000,
    read: ReadResult | None = None,
) -> LoadResult:
    """Load every fact for one accession from the selected package."""
    started = datetime.now(UTC)
    verify_package(selected)

    parsed = read or read_package(selected, context.accession, cik=context.cik)

    result = LoadResult(
        package=selected.filename,
        package_sha256=selected.sha256,
        period=selected.period,
        accession=context.accession,
        read=parsed,
        started_at=started.isoformat(),
        state="RUNNING",
    )

    with engine.begin() as connection:
        # Serialize concurrent loaders of this accession. Transaction-scoped, so it is released on
        # commit and on rollback alike.
        connection.execute(
            text("SELECT pg_advisory_xact_lock(:key)"),
            {"key": advisory_lock_key(context.accession)},
        )

        existing = {
            row[0]
            for row in connection.execute(
                text(
                    "SELECT source_row_id FROM xbrl_fact"
                    " WHERE accession = :a AND source_dataset = :d"
                ),
                {"a": context.accession, "d": SOURCE_DATASET},
            )
        }
        pending = [f for f in parsed.facts if f.source_row_id not in existing]
        result.rows_already_present = parsed.accepted - len(pending)

        for start in range(0, len(pending), batch_size):
            connection.execute(
                _INSERT, [_bind(f, context) for f in pending[start : start + batch_size]]
            )
        result.rows_inserted = len(pending)

        totals = connection.execute(
            text(
                "SELECT count(*), coalesce(sum(value_numeric), 0) FROM xbrl_fact"
                " WHERE accession = :a AND source_dataset = :d"
            ),
            {"a": context.accession, "d": SOURCE_DATASET},
        ).one()
        result.rows_in_database = int(totals[0])
        result.database_value_total = Decimal(totals[1])

        # The load ledger is marked inside the same transaction as the facts. A crash before the
        # commit leaves neither, which is the only way the flag can stay truthful.
        connection.execute(
            text("UPDATE dera_package SET loaded_at = :now WHERE filename = :f"),
            {"now": datetime.now(UTC), "f": selected.filename},
        )

    result.completed_at = datetime.now(UTC).isoformat()
    result.state = "COMPLETE"

    log_event(
        logger,
        logging.INFO,
        "dera fact load complete",
        package=selected.filename,
        accession=context.accession,
        matched=parsed.rows_matched,
        accepted=parsed.accepted,
        rejected=parsed.rejected,
        inserted=result.rows_inserted,
        already_present=result.rows_already_present,
        in_database=result.rows_in_database,
    )
    return result
