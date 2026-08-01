#!/usr/bin/env python3
"""Generate the initial Alembic migration from the model metadata.

Alembic's --autogenerate requires a live database to diff against. This environment has none
(see SPRINT-0002 blockers), so the initial migration is produced deterministically from
Base.metadata instead. The output is a normal Alembic revision: reviewable, reversible, and
identical to what autogenerate would emit against an empty database.

Run once. Subsequent migrations use --autogenerate against a live database.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from sqlalchemy import CheckConstraint, ForeignKeyConstraint, UniqueConstraint  # noqa: E402

from packages.persistence import Base  # noqa: E402


def render_type(column) -> str:
    type_ = column.type
    module = type(type_).__module__
    prefix = "postgresql." if "postgresql" in module else "sa."
    text = repr(type_)
    if prefix == "postgresql." and not text.startswith("postgresql."):
        text = f"postgresql.{text}"
    elif prefix == "sa." and not text.startswith("sa."):
        text = f"sa.{text}"
    return text


def render_column(column) -> str:
    parts = [f'"{column.name}"', render_type(column)]
    if column.primary_key:
        parts.append("primary_key=True")
    parts.append(f"nullable={column.nullable}")
    if column.server_default is not None:
        arg = column.server_default.arg
        literal = arg if isinstance(arg, str) else str(arg)
        parts.append(f'server_default=sa.text("{literal}")')
    if column.comment:
        escaped = column.comment.replace('"', '\\"')
        parts.append(f'comment="{escaped}"')
    return f"        sa.Column({', '.join(parts)}),"


def render_table(table) -> list[str]:
    lines = [f'    op.create_table(\n        "{table.name}",']
    for column in table.columns:
        lines.append(render_column(column))
    for constraint in sorted(
        table.constraints, key=lambda c: (type(c).__name__, str(c.name or ""))
    ):
        if isinstance(constraint, ForeignKeyConstraint):
            local = ", ".join(f'"{e.parent.name}"' for e in constraint.elements)
            remote = ", ".join(
                f'"{e.column.table.name}.{e.column.name}"' for e in constraint.elements
            )
            ondelete = constraint.ondelete
            extra = f', ondelete="{ondelete}"' if ondelete else ""
            lines.append(
                f"        sa.ForeignKeyConstraint([{local}], [{remote}], "
                f'name="{constraint.name}"{extra}),'
            )
        elif isinstance(constraint, UniqueConstraint):
            cols = ", ".join(f'"{c.name}"' for c in constraint.columns)
            lines.append(f'        sa.UniqueConstraint({cols}, name="{constraint.name}"),')
        elif isinstance(constraint, CheckConstraint):
            text = str(constraint.sqltext).replace('"', '\\"').replace("\n", " ")
            lines.append(f'        sa.CheckConstraint("{text}", name="{constraint.name}"),')
    lines.append("    )")
    for index in sorted(table.indexes, key=lambda i: i.name or ""):
        cols = ", ".join(f'"{c.name}"' for c in index.columns)
        opts = [f'"{index.name}"', f'"{table.name}"', f"[{cols}]"]
        if index.unique:
            opts.append("unique=True")
        where = index.dialect_options.get("postgresql", {}).get("where")
        if where is not None:
            opts.append(f'postgresql_where=sa.text("{where}")')
        using = index.dialect_options.get("postgresql", {}).get("using")
        if using:
            opts.append(f'postgresql_using="{using}"')
        lines.append(f"    op.create_index({', '.join(opts)})")
    return lines


def main() -> int:
    tables = Base.metadata.sorted_tables
    up: list[str] = []
    for table in tables:
        up.extend(render_table(table))
        up.append("")
    down = [f'    op.drop_table("{t.name}")' for t in reversed(tables)]

    body = f'''"""initial control plane schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-08-01

Creates the FinTek control plane: issuer identity with temporal validity, filings, canonical
footnotes with their source blocks and tables, the append-only fact lake, curated metric
definitions and derived values, versioned summaries, the ingest ledger, the DERA mirror ledger,
Deep Analysis sessions, and model invocation audit.

Generated deterministically from packages.persistence metadata rather than by --autogenerate,
because the authoring environment had no PostgreSQL available. See docs/sprints/SPRINT-0002.md.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import Text
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import UUID

# Text and UUID are imported explicitly because postgresql.JSONB and postgresql.ARRAY render
# their repr as JSONB(astext_type=Text()) and ARRAY(UUID()), which the generated code evaluates.
_ = (Text, UUID)

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
{chr(10).join(up)}
    # FINANCIAL-INVARIANT: a filed fact is immutable. A restatement appends a new observation and
    # is_latest_selected is recomputed; it never rewrites history. Enforced in the database so the
    # guarantee holds even against a direct SQL session.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION fintek_reject_fact_value_update()
        RETURNS TRIGGER AS $$
        BEGIN
            IF NEW.value_as_filed IS DISTINCT FROM OLD.value_as_filed
               OR NEW.unit IS DISTINCT FROM OLD.unit
               OR NEW.scale IS DISTINCT FROM OLD.scale
               OR NEW.concept IS DISTINCT FROM OLD.concept
               OR NEW.period_start IS DISTINCT FROM OLD.period_start
               OR NEW.period_end IS DISTINCT FROM OLD.period_end
               OR NEW.instant_date IS DISTINCT FROM OLD.instant_date THEN
                RAISE EXCEPTION
                    'xbrl_fact is append-only: a filed value, unit, scale, concept, or period '
                    'may never be updated. Append a new observation instead (fact_id=%)',
                    OLD.fact_id;
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_xbrl_fact_append_only
        BEFORE UPDATE ON xbrl_fact
        FOR EACH ROW EXECUTE FUNCTION fintek_reject_fact_value_update();
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_xbrl_fact_append_only ON xbrl_fact;")
    op.execute("DROP FUNCTION IF EXISTS fintek_reject_fact_value_update();")
{chr(10).join(down)}
'''
    target = REPO_ROOT / "migrations" / "versions" / "0001_initial_control_plane_schema.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(body, encoding="utf-8")
    print(f"wrote {target} ({len(tables)} tables)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
