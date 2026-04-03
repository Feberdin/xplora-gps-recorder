"""
Purpose: Wait for PostgreSQL to become reachable and apply Alembic migrations before app startup.
Inputs: Database settings and the local `alembic.ini` configuration.
Outputs: An initialized schema at the latest migration revision.
Invariants: Migrations are the only supported way to create or evolve the database schema.
Debugging: Run this script manually if the container exits early to isolate DB connectivity from API startup.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

from app.config import get_settings
from app.logging_config import configure_logging

LOGGER = logging.getLogger(__name__)


def wait_for_database(database_url: str, attempts: int = 30, sleep_seconds: int = 2) -> None:
    """Retry database connections so container startup tolerates cold PostgreSQL boots."""

    engine = create_engine(database_url, future=True, pool_pre_ping=True)
    try:
        for attempt in range(1, attempts + 1):
            try:
                with engine.connect() as connection:
                    connection.execute(text("SELECT 1"))
                LOGGER.info("Database connection established", extra={"attempt": attempt})
                return
            except SQLAlchemyError as exc:
                LOGGER.warning(
                    "Database not ready yet",
                    extra={"attempt": attempt, "remaining_attempts": attempts - attempt},
                    exc_info=exc,
                )
                time.sleep(sleep_seconds)
    finally:
        engine.dispose()

    raise RuntimeError(
        "PostgreSQL did not become ready in time. Check container health and credentials."
    )


def run_migrations() -> None:
    project_root = Path(__file__).resolve().parents[1]
    alembic_config = Config(str(project_root / "alembic.ini"))
    command.upgrade(alembic_config, "head")


def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_json, settings.log_include_sql)
    wait_for_database(settings.postgres_url)
    run_migrations()
    LOGGER.info("Database migrations applied successfully")


if __name__ == "__main__":
    main()
