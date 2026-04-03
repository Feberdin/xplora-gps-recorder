"""
Purpose: Define the Pydantic response models exposed by the REST API.
Inputs: ORM entities loaded from the analytics service.
Outputs: Stable JSON shapes for devices, positions, movement events, and heatmap tiles.
Invariants: API schemas stay backward-compatible unless intentionally versioned.
Debugging: If a field is missing in API output, compare the ORM object with the schema helper methods.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.db.models import GPSPosition, HeatmapTile


class DeviceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    device_id: str
    name: str
    owner_name: str | None
    created_at: datetime


class PositionResponse(BaseModel):
    id: int
    device_id: str
    timestamp: datetime
    latitude: float
    longitude: float
    accuracy: float | None
    speed: float | None
    battery_level: int | None
    street: str | None
    city: str | None
    postcode: str | None
    country: str | None
    place_name: str | None

    @classmethod
    def from_position(cls, position: GPSPosition) -> "PositionResponse":
        enrichment = position.enrichment
        return cls(
            id=position.id,
            device_id=position.device_id,
            timestamp=position.timestamp,
            latitude=position.latitude,
            longitude=position.longitude,
            accuracy=position.accuracy,
            speed=position.speed,
            battery_level=position.battery_level,
            street=enrichment.street if enrichment else None,
            city=enrichment.city if enrichment else None,
            postcode=enrichment.postcode if enrichment else None,
            country=enrichment.country if enrichment else None,
            place_name=enrichment.place_name if enrichment else None,
        )


class MovementEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    device_id: str
    start_time: datetime
    end_time: datetime
    distance_m: float
    avg_speed: float
    movement_type: str


class HeatmapTileResponse(BaseModel):
    id: int
    device_id: str
    lat_tile: float
    lon_tile: float
    visit_count: int

    @classmethod
    def from_tile(cls, tile: HeatmapTile) -> "HeatmapTileResponse":
        return cls(
            id=tile.id,
            device_id=tile.device_id,
            lat_tile=float(tile.lat_tile),
            lon_tile=float(tile.lon_tile),
            visit_count=tile.visit_count,
        )


class HealthResponse(BaseModel):
    status: str
    app_name: str
    app_env: str
    scheduler_running: bool
