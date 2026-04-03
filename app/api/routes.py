"""
Purpose: Expose REST endpoints for devices, raw positions, movement history, and heatmap data.
Inputs: Query parameters from FastAPI requests and database sessions from dependency injection.
Outputs: JSON responses tailored for dashboards, scripts, and Home Assistant consumers.
Invariants: Device-specific routes always return 404 for unknown device ids instead of empty success responses.
Debugging: Re-run the same request with `curl -v` and compare timestamps if filtering results seem off.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.schemas import (
    DeviceResponse,
    HeatmapTileResponse,
    MovementEventResponse,
    PositionResponse,
)
from app.config import get_settings
from app.db.session import get_db_session
from app.services.analytics_service import AnalyticsService

router = APIRouter()
settings = get_settings()
analytics_service = AnalyticsService(default_limit=settings.default_query_limit)


def _require_device(db_session: Session, device_id: str):
    device = analytics_service.get_device(db_session, device_id)
    if device is None:
        raise HTTPException(status_code=404, detail=f"Unknown device_id '{device_id}'")
    return device


@router.get("/devices", response_model=list[DeviceResponse], tags=["devices"])
def list_devices(db_session: Session = Depends(get_db_session)) -> list[DeviceResponse]:
    devices = analytics_service.list_devices(db_session)
    return [DeviceResponse.model_validate(device) for device in devices]


@router.get("/devices/{device_id}", response_model=DeviceResponse, tags=["devices"])
def get_device(device_id: str, db_session: Session = Depends(get_db_session)) -> DeviceResponse:
    device = _require_device(db_session, device_id)
    return DeviceResponse.model_validate(device)


@router.get(
    "/devices/{device_id}/positions", response_model=list[PositionResponse], tags=["positions"]
)
def list_positions(
    device_id: str,
    db_session: Session = Depends(get_db_session),
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    limit: Annotated[int | None, Query(ge=1, le=5000)] = None,
) -> list[PositionResponse]:
    _require_device(db_session, device_id)
    positions = analytics_service.list_positions(db_session, device_id, start_time, end_time, limit)
    return [PositionResponse.from_position(position) for position in positions]


@router.get(
    "/devices/{device_id}/movements",
    response_model=list[MovementEventResponse],
    tags=["movements"],
)
def list_movements(
    device_id: str,
    db_session: Session = Depends(get_db_session),
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    limit: Annotated[int | None, Query(ge=1, le=5000)] = None,
) -> list[MovementEventResponse]:
    _require_device(db_session, device_id)
    movements = analytics_service.list_movements(db_session, device_id, start_time, end_time, limit)
    return [MovementEventResponse.model_validate(event) for event in movements]


@router.get(
    "/devices/{device_id}/heatmap",
    response_model=list[HeatmapTileResponse],
    tags=["heatmap"],
)
@router.get(
    "/heatmap/{device_id}",
    response_model=list[HeatmapTileResponse],
    tags=["heatmap"],
    include_in_schema=False,
)
def list_heatmap(
    device_id: str,
    db_session: Session = Depends(get_db_session),
    limit: Annotated[int | None, Query(ge=1, le=5000)] = None,
) -> list[HeatmapTileResponse]:
    _require_device(db_session, device_id)
    heatmap_tiles = analytics_service.list_heatmap(db_session, device_id, limit)
    return [HeatmapTileResponse.from_tile(tile) for tile in heatmap_tiles]
