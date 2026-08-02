"""table ownership classification and its provenance

Revision ID: 0002_table_ownership
Revises: 0001_initial
Create Date: 2026-08-02

Sprint 4 resolves which canonical footnote owns each parsed table. `footnote_table.footnote_id`
already existed and now carries that owner — but a NULL there is ambiguous. It could mean the
table belongs to a financial statement, to an excluded Item 408 or Item 1C disclosure, to filing
furniture such as a cover layout, or that ownership could not be established at all. Those four
are different facts and only one of them is a defect.

This revision adds the classification and the evidence behind it:

    ownership_kind       CANONICAL_FOOTNOTE | EXCLUDED_FILING_SECTION | FINANCIAL_STATEMENT
                         | OTHER_FILING_REPORT | UNRESOLVED
    ownership_method     which mechanism produced it
    ownership_evidence   the tagged concept, the candidate presentation roles, and the reason

Nothing else changes. `0001_initial` is SEALED and is not touched: every uniqueness constraint
canonicalization needs already existed there, which is why Sprint 4 needed no migration until
ownership introduced a genuinely new fact to record.

WHY NOT REUSE `validation_warnings`. That column exists for parse-quality warnings. Putting a
classification in it would make two unrelated concerns share one field, and the first query that
needed "every table owned by a footnote" would have to parse JSON to find out.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0002_table_ownership"
down_revision = "0001_initial"
branch_labels = None
depends_on = None

OWNERSHIP_KINDS = (
    "CANONICAL_FOOTNOTE",
    "EXCLUDED_FILING_SECTION",
    "FINANCIAL_STATEMENT",
    "OTHER_FILING_REPORT",
    "UNRESOLVED",
)


def upgrade() -> None:
    op.add_column(
        "footnote_table",
        sa.Column(
            "ownership_kind",
            sa.String(30),
            nullable=True,
            comment="how this table relates to the canonical footnote set",
        ),
    )
    op.add_column(
        "footnote_table",
        sa.Column(
            "ownership_method",
            sa.String(40),
            nullable=True,
            comment="the mechanism that produced the classification",
        ),
    )
    op.add_column(
        "footnote_table",
        sa.Column(
            "ownership_evidence",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment="tagged concept, candidate presentation roles, and the deterministic reason",
        ),
    )

    # Held as text with a check rather than a PostgreSQL ENUM, matching the rest of the schema:
    # adding a value stays a migration rather than a type alteration that locks the table.
    # The bare name, NOT a pre-prefixed one. `alembic.ini`'s naming convention is
    # `ck_%(table_name)s_%(constraint_name)s`, so passing `ck_footnote_table_...` here produces
    # `ck_footnote_table_ck_footnote_table_...` — which is what the first version of this
    # migration created, diverging from the name the model declares. A schema whose constraint
    # names differ from its models is drift that autogenerate would surface later as a phantom
    # change, so it is corrected here rather than lived with.
    values = ", ".join(f"'{kind}'" for kind in OWNERSHIP_KINDS)
    op.create_check_constraint(
        "ownership_kind_is_known",
        "footnote_table",
        f"ownership_kind IS NULL OR ownership_kind IN ({values})",
    )

    # A footnote-owned table must name its owner, and a table that names an owner must be
    # classified as footnote-owned. Enforcing both directions in the database means the
    # classification and the foreign key cannot drift apart.
    op.create_check_constraint(
        "ownership_matches_footnote",
        "footnote_table",
        "(ownership_kind = 'CANONICAL_FOOTNOTE' AND footnote_id IS NOT NULL)"
        " OR (ownership_kind IS DISTINCT FROM 'CANONICAL_FOOTNOTE' AND footnote_id IS NULL)"
        " OR ownership_kind IS NULL",
    )

    # Finding unresolved tables is a routine completeness query, so it gets a partial index.
    op.create_index(
        "ix_footnote_table_unresolved",
        "footnote_table",
        ["filing_id"],
        postgresql_where=sa.text("ownership_kind = 'UNRESOLVED'"),
    )


def downgrade() -> None:
    op.drop_index("ix_footnote_table_unresolved", table_name="footnote_table")
    # Bare names here too. Alembic renders the naming convention on DROP as well as CREATE, so a
    # pre-prefixed name produces the doubled form and the drop fails against a database the
    # corrected upgrade created. Verified by running the round trip, not by reading the docs.
    op.drop_constraint("ownership_matches_footnote", "footnote_table", type_="check")
    op.drop_constraint("ownership_kind_is_known", "footnote_table", type_="check")
    op.drop_column("footnote_table", "ownership_evidence")
    op.drop_column("footnote_table", "ownership_method")
    op.drop_column("footnote_table", "ownership_kind")
