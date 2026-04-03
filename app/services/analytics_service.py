"""
Purpose: Provide focused query helpers for the REST API so route handlers stay easy to read.
Inputs: Device ids and optional time-window filters from API requests.
Outputs: ORM objects for devices, positions, movement events, and heatmap tiles.
Invariants: Queries always return the newest data first and respect the configured safety limits.
Debugging: Reproduce an API call with `curl` and compare SQL logs if filtering behaves unexpectedly.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Select, select
from sqlalchemy.orm import Session, joinedload

from app.db.models import GPSPosition, HeatmapTile, MovementEvent, WatchDevice


class AnalyticsService:
    """Encapsulate API-facing database queries."""

    def __init__(self, default_limit: int) -> None:
        self.default_limit = default_limit

    def list_devices(self, db_session: Session) -> list[WatchDevice]:
        statement = select(WatchDevice).order_by(WatchDevice.name.asc())
        return list(db_session.execute(statement).scalars().all())

    def get_device(self, db_session: Session, device_id: str) -> WatchDevice | None:
        statement = select(WatchDevice).where(WatchDevice.device_id == device_id)
        return db_session.execute(statement).scalar_one_or_none()

    def list_positions(
        self,
        db_session: Session,
        device_id: str,
        start_time: datetime | None,
        end_time: datetime | None,
        limit: int | None,
    ) -> list[GPSPosition]:
        statement = (
            select(GPSPosition)
            .options(joinedload(GPSPosition.enrichment))
            .where(GPSPosition.device_id == device_id)
            .order_by(GPSPosition.timestamp.desc())
        )
        statement = self._apply_time_filters(statement, GPSPosition.timestamp, start_time, end_time)
        statement = statement.limit(limit or self.default_limit)
        return list(db_session.execute(statement).scalars().all())

    def list_movements(
        self,
        db_session: Session,
        device_id: str,
        start_time: datetime | None,
        end_time: datetime | None,
        limit: int | None,
    ) -> list[MovementEvent]:
        statement = (
            select(MovementEvent)
            .where(MovementEvent.device_id == device_id)
            .order_by(MovementEvent.start_time.desc())
        )
        statement = self._apply_time_filters(
            statement, MovementEvent.start_time, start_time, end_time
        )
        statement = statement.limit(limit or self.default_limit)
        return list(db_session.execute(statement).scalars().all())

    def list_heatmap(
        self, db_session: Session, device_id: str, limit: int | None
    ) -> list[HeatmapTile]:
        statement = (
            select(HeatmapTile)
            .where(HeatmapTile.device_id == device_id)
            .order_by(
                HeatmapTile.visit_count.desc(),
                HeatmapTile.lat_tile.asc(),
                HeatmapTile.lon_tile.asc(),
            )
            .limit(limit or self.default_limit)
        )
        return list(db_session.execute(statement).scalars().all())

    def _apply_time_filters(
        self,
        statement: Select,
        column,
        start_time: datetime | None,
        end_time: datetime | None,
    ) -> Select:
        if start_time is not None:
            statement = statement.where(column >= start_time)
        if end_time is not None:
            statement = statement.where(column <= end_time)
        return statement
