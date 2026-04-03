"""
Purpose: Create shared SQLAlchemy engine and session helpers for the whole service.
Inputs: Database URL and logging flags from `app.config`.
Outputs: A declarative base, a configured engine, and context-managed sessions.
Invariants: Sessions must be short-lived; callers are responsible for commit/rollback boundaries.
Debugging: Enable `LOG_INCLUDE_SQL=true` to inspect SQL emitted by the application.
"""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    """Shared declarative base for all SQLAlchemy models."""


settings = get_settings()

engine = create_engine(
    settings.postgres_url,
    future=True,
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def get_db_session() -> Generator[Session, None, None]:
    """Yield a database session for FastAPI dependencies."""

    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@contextmanager
def session_scope() -> Generator[Session, None, None]:
    """Provide a transactional scope for background jobs and scripts."""

    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
