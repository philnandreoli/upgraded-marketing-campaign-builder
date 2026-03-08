"""Alembic environment – async SQLAlchemy support."""

from __future__ import annotations

import asyncio
import os
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config, create_async_engine

from alembic import context

# -- Alembic Config object ---------------------------------------------------
config = context.config

# ---------------------------------------------------------------------------
# Database URL — honour DB_AUTH_MODE
# ---------------------------------------------------------------------------

_DB_AUTH_MODE = os.getenv("DB_AUTH_MODE", "local").lower()

if _DB_AUTH_MODE == "azure":
    _host = os.getenv("AZURE_POSTGRES_HOST", "")
    _database = os.getenv("AZURE_POSTGRES_DATABASE", "campaigns")
    _user = os.getenv("AZURE_POSTGRES_USER", "")
    DATABASE_URL = f"postgresql+asyncpg://{_user}@{_host}/{_database}"
else:
    # Set the database URL from environment, falling back to default
    DATABASE_URL = os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://postgres:postgres@db:5432/campaigns",
    )

config.set_main_option("sqlalchemy.url", DATABASE_URL)

# Logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# -- Import our models so autogenerate can detect changes --------------------
from backend.infrastructure.database import Base  # noqa: E402

target_metadata = Base.metadata


# ---------------------------------------------------------------------------
# Offline (SQL-script) mode
# ---------------------------------------------------------------------------

def run_migrations_offline() -> None:
    """Emit SQL to stdout without a live database connection."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


# ---------------------------------------------------------------------------
# Online (async) mode
# ---------------------------------------------------------------------------

def do_run_migrations(connection) -> None:
    """Helper: configure context with the given connection and run."""
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Create an async engine and run migrations within a connection."""
    if _DB_AUTH_MODE == "azure":
        # Azure mode: acquire an Entra token for the migration connection.
        # get_connection_password() returns the token coroutine callable.
        from backend.infrastructure.database import get_connection_password  # noqa: PLC0415

        connectable = create_async_engine(
            DATABASE_URL,
            poolclass=pool.NullPool,
            connect_args={
                "password": get_connection_password(),
                "ssl": "require",
            },
        )
    else:
        connectable = async_engine_from_config(
            config.get_section(config.config_ini_section, {}),
            prefix="sqlalchemy.",
            poolclass=pool.NullPool,
        )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode (async)."""
    asyncio.run(run_async_migrations())


# ---------------------------------------------------------------------------

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
