"""
Purpose: Define the persistent data model for watches, GPS positions, enrichments, analytics, and caches.
Inputs: Data ingested from the Xplora API and derived analytics produced by background workers.
Outputs: SQLAlchemy ORM models that map directly to PostgreSQL tables.
Invariants: `watch_devices.device_id` is the stable external identifier; position timestamps must remain immutable.
Debugging: Inspect rows with `psql` or `/devices/{id}/positions` if enrichment or movement results look suspicious.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class WatchDevice(Base):
    """Registered smartwatch or child profile returned by the Xplora cloud."""

    __tablename__ = "watch_devices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    device_id: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    owner_name: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    positions: Mapped[list["GPSPosition"]] = relationship(
        back_populates="device",
        cascade="all, delete-orphan",
    )
    movement_events: Mapped[list["MovementEvent"]] = relationship(back_populates="device")
    heatmap_tiles: Mapped[list["HeatmapTile"]] = relationship(back_populates="device")


class GPSPosition(Base):
    """Raw GPS sample fetched from Xplora and stored for long-term analysis."""

    __tablename__ = "gps_positions"
    __table_args__ = (UniqueConstraint("device_id", "timestamp", name="uq_gps_positions_device_timestamp"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    device_id: Mapped[str] = mapped_column(
        String(128),
        ForeignKey("watch_devices.device_id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    accuracy: Mapped[float | None] = mapped_column(Float)
    speed: Mapped[float | None] = mapped_column(Float)
    battery_level: Mapped[int | None] = mapped_column(Integer)

    device: Mapped["WatchDevice"] = relationship(back_populates="positions")
    enrichment: Mapped["LocationEnriched | None"] = relationship(
        back_populates="position",
        uselist=False,
        cascade="all, delete-orphan",
    )


class LocationEnriched(Base):
    """Reverse-geocoded human-readable address for a GPS position."""

    __tablename__ = "location_enriched"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    position_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("gps_positions.id", ondelete="CASCADE"),
        unique=True,
        index=True,
        nullable=False,
    )
    street: Mapped[str | None] = mapped_column(String(255))
    city: Mapped[str | None] = mapped_column(String(255))
    postcode: Mapped[str | None] = mapped_column(String(64))
    country: Mapped[str | None] = mapped_column(String(255))
    place_name: Mapped[str | None] = mapped_column(String(255))

    position: Mapped["GPSPosition"] = relationship(back_populates="enrichment")


class MovementEvent(Base):
    """Aggregated segment describing a stationary period or movement interval."""

    __tablename__ = "movement_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    device_id: Mapped[str] = mapped_column(
        String(128),
        ForeignKey("watch_devices.device_id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)
    end_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)
    distance_m: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    avg_speed: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    movement_type: Mapped[str] = mapped_column(String(32), index=True, nullable=False)

    device: Mapped["WatchDevice"] = relationship(back_populates="movement_events")


class HeatmapTile(Base):
    """Visit counter for rounded geographic tiles used to render heatmaps."""

    __tablename__ = "heatmap_tiles"
    __table_args__ = (UniqueConstraint("device_id", "lat_tile", "lon_tile", name="uq_heatmap_tiles"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    device_id: Mapped[str] = mapped_column(
        String(128),
        ForeignKey("watch_devices.device_id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    lat_tile: Mapped[Decimal] = mapped_column(Numeric(9, 3), nullable=False)
    lon_tile: Mapped[Decimal] = mapped_column(Numeric(9, 3), nullable=False)
    visit_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    device: Mapped["WatchDevice"] = relationship(back_populates="heatmap_tiles")


class ReverseGeocodeCache(Base):
    """Cache of rounded coordinates to reduce calls against the public Nominatim API."""

    __tablename__ = "reverse_geocode_cache"
    __table_args__ = (
        UniqueConstraint("lat_tile", "lon_tile", name="uq_reverse_geocode_cache_tiles"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    lat_tile: Mapped[float] = mapped_column(Float, nullable=False, index=True)
    lon_tile: Mapped[float] = mapped_column(Float, nullable=False, index=True)
    street: Mapped[str | None] = mapped_column(String(255))
    city: Mapped[str | None] = mapped_column(String(255))
    postcode: Mapped[str | None] = mapped_column(String(64))
    country: Mapped[str | None] = mapped_column(String(255))
    place_name: Mapped[str | None] = mapped_column(String(255))
    raw_payload: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
