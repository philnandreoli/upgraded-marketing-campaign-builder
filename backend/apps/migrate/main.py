"""Dedicated database migration entry point.

This module is the **sole** component responsible for applying schema changes
in cloud (``azure``) deployments.  It is executed as a one-shot Azure
Container Apps Job that must complete successfully before the API and Worker
services are (re)started.

Usage::

    python -m backend.apps.migrate.main

In local development the API and Worker still auto-migrate on startup via
:func:`backend.infrastructure.database.init_db`, so this module is not
required for day-to-day development workflows.

Rollout order
-------------
1. Build and push the new container image to the registry.
2. Trigger the migration job (``caj-<env>-migration``) via the Azure portal,
   CLI, or CI pipeline and wait for it to complete successfully.
3. Deploy the updated API revision.
4. Deploy the updated Worker revision.

If the migration job fails:
- The existing API and Worker revisions remain active and unaffected.
- Inspect the job logs in Azure Log Analytics / Container Apps log stream.
- Fix the migration script, build a new image, and re-trigger the job.
- Do **not** start the new API/Worker revisions until the job succeeds; they
  will refuse to start with a mismatched schema (``RuntimeError`` in
  :func:`~backend.infrastructure.database.init_db`).
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

# backend/apps/migrate/main.py → three parents up = backend/
_BACKEND_DIR = Path(__file__).resolve().parent.parent.parent


def _make_alembic_config():
    """Return an Alembic Config pointed at our ini file."""
    from alembic.config import Config  # noqa: PLC0415

    alembic_cfg = Config(str(_BACKEND_DIR / "alembic.ini"))
    alembic_cfg.set_main_option("script_location", str(_BACKEND_DIR / "migrations"))

    # Set the database URL based on auth mode so env.py picks it up.
    from backend.infrastructure.database import (  # noqa: PLC0415
        DATABASE_URL,
        _DB_AUTH_MODE_AZURE,
        _build_azure_db_url,
        _get_auth_mode,
    )

    if _get_auth_mode() == _DB_AUTH_MODE_AZURE:
        # env.py will acquire the Entra token per connection.
        alembic_cfg.set_main_option("sqlalchemy.url", _build_azure_db_url())
    else:
        alembic_cfg.set_main_option("sqlalchemy.url", DATABASE_URL.replace("+asyncpg", ""))

    return alembic_cfg


def run_migrations() -> None:
    """Apply all pending Alembic migrations synchronously.

    This is always a **write** operation — it applies schema changes
    unconditionally, regardless of ``DB_AUTH_MODE``.  In azure deployments
    this is intentional: only the migration job should call this function.
    """
    from alembic import command  # noqa: PLC0415

    alembic_cfg = _make_alembic_config()
    logger.info("Running alembic upgrade head")
    command.upgrade(alembic_cfg, "head")
    logger.info("Migrations complete")


def main() -> None:
    """Entry point for the dedicated migration job.

    Configures logging, runs all pending migrations, and exits with a
    non-zero status code on failure so that the Azure Container Apps Job
    runtime marks the execution as failed.
    """
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        force=True,
    )

    logger.info("Migration job starting")

    try:
        run_migrations()
    except BaseException as exc:
        import time
        import traceback

        traceback.print_exc()
        logger.exception("Migration job failed: %s", exc)
        sys.stdout.flush()
        sys.stderr.flush()
        time.sleep(5)
        sys.exit(1)

    logger.info("Migration job completed successfully")


if __name__ == "__main__":
    main()
