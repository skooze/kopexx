"""SQLAlchemy declarative base and shared column types.

ARCHITECTURE: this package is an infrastructure adapter. `packages/domain` must never import it.
Dependency flows domain <- persistence, never the reverse. See rules.md section 4.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, MetaData, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Explicit naming convention so Alembic autogenerate produces stable, reviewable constraint names
# instead of database-assigned ones that differ between environments.
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def new_uuid() -> uuid.UUID:
    """Generate an identifier application-side so a record has identity before insert."""
    return uuid.uuid4()


class TimestampMixin:
    """created_at on every table, per the data dictionary conventions."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
