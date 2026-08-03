"""Alembic environment.

Resolves the database URL through `packages.persistence.engine` rather than alembic.ini, so the
same migration runs against local, dev, and production without editing a checked-in file, and so
the migration tool and the application can never disagree about which database they mean.

The previous default here was a Docker Compose-style password-bearing localhost URL of the shape
`postgresql+psycopg://<user>:<password>@localhost:5432/<database>`. That is a credential in a
tracked file, which this project prohibits outright, and it was also wrong for this host: it
forced a TCP connection that failed SCRAM authentication against a cluster configured for peer
authentication over a Unix socket, which reads as a broken database rather than as a wrong URL.
"""

from __future__ import annotations

import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from packages.persistence import Base  # noqa: E402
from packages.persistence.engine import migration_target_url  # noqa: E402

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def get_url() -> str:
    """The migration target, from the single authoritative resolver.

    DEFECT D-13. This used to call `database_url()` directly, which reads DATABASE_URL. A caller
    that set `sqlalchemy.url` on the Alembic `Config` was therefore silently overridden, and a
    test helper's `stamp base` reached the application database. `migration_target_url()` gives
    an explicitly supplied target precedence over DATABASE_URL, which is the correction.

    An explicit `sqlalchemy.url` on the Config is honoured when present, so the ordinary
    `alembic -x` and Config paths behave as a reader expects.
    """
    configured = config.get_main_option("sqlalchemy.url", None)
    if configured:
        return configured
    return migration_target_url()


def run_migrations_offline() -> None:
    """Emit DDL to stdout without a live connection.

    This is how the migration is reviewed and how it is validated in an environment with no
    database available.
    """
    context.configure(
        url=get_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    section = config.get_section(config.config_ini_section, {})
    section["sqlalchemy.url"] = get_url()
    connectable = engine_from_config(section, prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
