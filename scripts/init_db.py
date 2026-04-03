"""
Purpose: Wait for PostgreSQL to become reachable and apply Alembic migrations before app startup.
Inputs: Database settings and the local `alembic.ini` configuration.
Outputs: An initialized schema at the latest migration revision.
Invariants: Migrations are the only supported way to create or evolve the database schema.
Debugging: Run this script manually if the container exits early to isolate DB connectivity from API startup.
"""

from __future__ import annotations

import logging
import sys
import time
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError

# Why this section exists:
# Home Assistant starts the database bootstrap via `python scripts/init_db.py`.
# In that execution mode, Python places `/app/scripts` on `sys.path`, but not the
# project root `/app`, so `from app...` imports would fail. We add the repository
# root explicitly to keep direct script execution reliable in Docker and HA.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.config import get_settings  # noqa: E402
from app.logging_config import configure_logging  # noqa: E402

LOGGER = logging.getLogger(__name__)


def wait_for_database(database_url: str, attempts: int = 30, sleep_seconds: int = 2) -> None:
    """Prepare SQLite or retry database connections for server-based databases."""

    if database_url.startswith("sqlite"):
        ensure_sqlite_parent_directory(database_url)
        engine = create_engine(database_url, future=True, connect_args={"check_same_thread": False})
        try:
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            LOGGER.info("SQLite database is ready")
            return
        finally:
            engine.dispose()

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
        "The database did not become ready in time. Check host reachability, credentials, or SQLite path permissions."
    )


def ensure_sqlite_parent_directory(database_url: str) -> None:
    """Create the parent directory for file-based SQLite databases when needed."""

    url = make_url(database_url)
    if not url.database or url.database == ":memory:":
        return

    database_path = Path(url.database)
    database_path.parent.mkdir(parents=True, exist_ok=True)


def run_migrations() -> None:
    alembic_config = Config(str(PROJECT_ROOT / "alembic.ini"))
    command.upgrade(alembic_config, "head")


def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_json, settings.log_include_sql)
    wait_for_database(settings.database_url or "")
    run_migrations()
    LOGGER.info("Database migrations applied successfully")


if __name__ == "__main__":
    main()
