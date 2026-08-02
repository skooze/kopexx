"""Reconcile a completed load against the package it came from.

A short load is the failure mode that would poison everything downstream, and it is invisible: a
filing that loaded 3,000 of its 4,000 facts looks exactly like a filing that has 3,000 facts. No
error is raised, no row is malformed, and the missing facts surface years later as a metric that
quietly disagrees with the filed statements.

So the load is not complete when the inserts succeed. It is complete when every row read is
accounted for and the database independently reproduces the source's own arithmetic.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.engine import Engine

from .loader import SOURCE_DATASET, LoadResult

# xbrl_fact.value_numeric is NUMERIC(38, 6). A DERA value carrying more than six fractional digits
# is rounded on insert, so the database total can differ from the source total by a fraction of a
# cent per row. The tolerance scales with the row count; anything larger is a missing or duplicated
# row, not rounding.
ROUNDING_TOLERANCE_PER_ROW = Decimal("0.000001")


@dataclass(frozen=True)
class Check:
    """One reconciliation assertion and its result."""

    name: str
    expected: str
    actual: str
    ok: bool
    detail: str = ""


@dataclass
class Reconciliation:
    """The full set of checks for one load."""

    accession: str
    package: str
    checks: list[Check]

    @property
    def ok(self) -> bool:
        return all(c.ok for c in self.checks)

    @property
    def failures(self) -> list[Check]:
        return [c for c in self.checks if not c.ok]

    def as_record(self) -> dict[str, object]:
        return {
            "accession": self.accession,
            "package": self.package,
            "ok": self.ok,
            "checks": [
                {
                    "name": c.name,
                    "expected": c.expected,
                    "actual": c.actual,
                    "ok": c.ok,
                    "detail": c.detail,
                }
                for c in self.checks
            ],
        }


@dataclass(frozen=True)
class DatabaseProfile:
    """What the database holds for one accession, computed by the database itself.

    A typed record rather than a mapping of `object`: every field below is compared against a
    source-side count, and a wrong coercion in that comparison is exactly the kind of defect this
    module exists to catch.
    """

    rows: int
    distinct_keys: int
    concepts: int
    total: Decimal
    consolidated: int
    instants: int
    durations: int


def _database_profile(engine: Engine, accession: str) -> DatabaseProfile:
    with engine.connect() as connection:
        row = (
            connection.execute(
                text(
                    "SELECT count(*) AS rows,"
                    " count(DISTINCT source_row_id) AS distinct_keys,"
                    " count(DISTINCT concept) AS concepts,"
                    " coalesce(sum(value_numeric), 0) AS total,"
                    " count(*) FILTER (WHERE dimensions = '{}'::jsonb) AS consolidated,"
                    " count(*) FILTER (WHERE period_type = 'instant') AS instants,"
                    " count(*) FILTER (WHERE period_type = 'duration') AS durations"
                    " FROM xbrl_fact WHERE accession = :a AND source_dataset = :d"
                ),
                {"a": accession, "d": SOURCE_DATASET},
            )
            .mappings()
            .one()
        )
    return DatabaseProfile(
        rows=int(row["rows"]),
        distinct_keys=int(row["distinct_keys"]),
        concepts=int(row["concepts"]),
        total=Decimal(row["total"]),
        consolidated=int(row["consolidated"]),
        instants=int(row["instants"]),
        durations=int(row["durations"]),
    )


def reconcile(engine: Engine, result: LoadResult) -> Reconciliation:
    """Check a completed load against its source package and against the database."""
    read = result.read
    db = _database_profile(engine, result.accession)

    source_concepts = len({f.concept for f in read.facts})
    source_consolidated = sum(1 for f in read.facts if f.is_consolidated)
    source_instants = sum(1 for f in read.facts if f.period_type == "instant")
    source_durations = sum(1 for f in read.facts if f.period_type == "duration")

    tolerance = ROUNDING_TOLERANCE_PER_ROW * max(read.accepted, 1)
    value_delta = abs(db.total - read.value_total)

    checks = [
        Check(
            name="every_matched_row_is_accounted_for",
            expected=str(read.rows_matched),
            actual=str(read.accepted + read.rejected),
            ok=read.rows_matched == read.accepted + read.rejected,
            detail="accepted + rejected must equal the rows read for this accession",
        ),
        Check(
            name="database_row_count_matches_accepted",
            expected=str(read.accepted),
            actual=str(db.rows),
            ok=db.rows == read.accepted,
            detail="a short load is otherwise indistinguishable from a small filing",
        ),
        Check(
            name="natural_key_is_unique_in_database",
            expected=str(db.rows),
            actual=str(db.distinct_keys),
            ok=db.distinct_keys == db.rows,
            detail="a repeated key means idempotency is broken and a rerun would double-count",
        ),
        Check(
            name="distinct_concepts_match",
            expected=str(source_concepts),
            actual=str(db.concepts),
            ok=db.concepts == source_concepts,
            detail="catches a whole tag being dropped by normalization",
        ),
        Check(
            name="numeric_total_matches",
            expected=str(read.value_total),
            actual=str(db.total),
            ok=value_delta <= tolerance,
            detail=(
                f"delta {value_delta} against a NUMERIC(38,6) rounding tolerance of {tolerance}; "
                "the strongest single check that no row was lost, duplicated, or mangled"
            ),
        ),
        Check(
            name="consolidated_split_matches",
            expected=str(source_consolidated),
            actual=str(db.consolidated),
            ok=db.consolidated == source_consolidated,
            detail="dimensional facts must not land in the consolidated series",
        ),
        Check(
            name="period_type_split_matches",
            expected=f"{source_instants} instant / {source_durations} duration",
            actual=f"{db.instants} instant / {db.durations} duration",
            ok=db.instants == source_instants and db.durations == source_durations,
            detail="catches a qtrs value being misread, which would move a fact between series",
        ),
        Check(
            name="every_dimension_hash_resolved",
            expected="0 unknown",
            actual=f"{len(read.unknown_dimension_hashes)} unknown",
            ok=not read.unknown_dimension_hashes,
            detail="a dimh absent from dim.tsv means the package is internally inconsistent",
        ),
        Check(
            name="no_duplicate_natural_keys_in_source",
            expected="0",
            actual=str(len(read.duplicate_keys)),
            ok=not read.duplicate_keys,
            detail="DERA documents this tuple as num.tsv's primary key",
        ),
    ]

    return Reconciliation(accession=result.accession, package=result.package, checks=checks)
