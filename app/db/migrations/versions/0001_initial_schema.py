"""
Purpose: Create the initial PostgreSQL schema for devices, positions, enrichments, analytics, and caches.
Inputs: Applied by Alembic during startup or manual deployment.
Outputs: All tables and indexes required by the recorder service.
Invariants: This migration is the baseline and should remain append-only after release.
Debugging: If startup fails here, inspect the container logs and verify database credentials and permissions.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Why this section exists:
    # These tables store the canonical watch metadata and every raw GPS sample.
    op.create_table(
        "watch_devices",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("device_id", sa.String(length=128), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("owner_name", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_watch_devices_device_id"), "watch_devices", ["device_id"], unique=True)

    op.create_table(
        "gps_positions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("device_id", sa.String(length=128), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("latitude", sa.Float(), nullable=False),
        sa.Column("longitude", sa.Float(), nullable=False),
        sa.Column("accuracy", sa.Float(), nullable=True),
        sa.Column("speed", sa.Float(), nullable=True),
        sa.Column("battery_level", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["device_id"], ["watch_devices.device_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("device_id", "timestamp", name="uq_gps_positions_device_timestamp"),
    )
    op.create_index(op.f("ix_gps_positions_device_id"), "gps_positions", ["device_id"], unique=False)
    op.create_index(op.f("ix_gps_positions_timestamp"), "gps_positions", ["timestamp"], unique=False)

    # Why this section exists:
    # Enrichment and cache tables separate slow geocoding work from raw position storage.
    op.create_table(
        "location_enriched",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("position_id", sa.Integer(), nullable=False),
        sa.Column("street", sa.String(length=255), nullable=True),
        sa.Column("city", sa.String(length=255), nullable=True),
        sa.Column("postcode", sa.String(length=64), nullable=True),
        sa.Column("country", sa.String(length=255), nullable=True),
        sa.Column("place_name", sa.String(length=255), nullable=True),
        sa.ForeignKeyConstraint(["position_id"], ["gps_positions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("position_id"),
    )
    op.create_index(op.f("ix_location_enriched_position_id"), "location_enriched", ["position_id"], unique=True)

    op.create_table(
        "reverse_geocode_cache",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("lat_tile", sa.Float(), nullable=False),
        sa.Column("lon_tile", sa.Float(), nullable=False),
        sa.Column("street", sa.String(length=255), nullable=True),
        sa.Column("city", sa.String(length=255), nullable=True),
        sa.Column("postcode", sa.String(length=64), nullable=True),
        sa.Column("country", sa.String(length=255), nullable=True),
        sa.Column("place_name", sa.String(length=255), nullable=True),
        sa.Column("raw_payload", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("lat_tile", "lon_tile", name="uq_reverse_geocode_cache_tiles"),
    )
    op.create_index(
        op.f("ix_reverse_geocode_cache_lat_tile"),
        "reverse_geocode_cache",
        ["lat_tile"],
        unique=False,
    )
    op.create_index(
        op.f("ix_reverse_geocode_cache_lon_tile"),
        "reverse_geocode_cache",
        ["lon_tile"],
        unique=False,
    )

    # Why this section exists:
    # Analytics tables support both movement history and heatmap generation for dashboards.
    op.create_table(
        "movement_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("device_id", sa.String(length=128), nullable=False),
        sa.Column("start_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("distance_m", sa.Float(), nullable=False),
        sa.Column("avg_speed", sa.Float(), nullable=False),
        sa.Column("movement_type", sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(["device_id"], ["watch_devices.device_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_movement_events_device_id"), "movement_events", ["device_id"], unique=False)
    op.create_index(op.f("ix_movement_events_end_time"), "movement_events", ["end_time"], unique=False)
    op.create_index(
        op.f("ix_movement_events_movement_type"),
        "movement_events",
        ["movement_type"],
        unique=False,
    )
    op.create_index(op.f("ix_movement_events_start_time"), "movement_events", ["start_time"], unique=False)

    op.create_table(
        "heatmap_tiles",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("device_id", sa.String(length=128), nullable=False),
        sa.Column("lat_tile", sa.Numeric(precision=9, scale=3), nullable=False),
        sa.Column("lon_tile", sa.Numeric(precision=9, scale=3), nullable=False),
        sa.Column("visit_count", sa.Integer(), nullable=False, server_default="1"),
        sa.ForeignKeyConstraint(["device_id"], ["watch_devices.device_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("device_id", "lat_tile", "lon_tile", name="uq_heatmap_tiles"),
    )
    op.create_index(op.f("ix_heatmap_tiles_device_id"), "heatmap_tiles", ["device_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_heatmap_tiles_device_id"), table_name="heatmap_tiles")
    op.drop_table("heatmap_tiles")

    op.drop_index(op.f("ix_movement_events_start_time"), table_name="movement_events")
    op.drop_index(op.f("ix_movement_events_movement_type"), table_name="movement_events")
    op.drop_index(op.f("ix_movement_events_end_time"), table_name="movement_events")
    op.drop_index(op.f("ix_movement_events_device_id"), table_name="movement_events")
    op.drop_table("movement_events")

    op.drop_index(op.f("ix_reverse_geocode_cache_lon_tile"), table_name="reverse_geocode_cache")
    op.drop_index(op.f("ix_reverse_geocode_cache_lat_tile"), table_name="reverse_geocode_cache")
    op.drop_table("reverse_geocode_cache")

    op.drop_index(op.f("ix_location_enriched_position_id"), table_name="location_enriched")
    op.drop_table("location_enriched")

    op.drop_index(op.f("ix_gps_positions_timestamp"), table_name="gps_positions")
    op.drop_index(op.f("ix_gps_positions_device_id"), table_name="gps_positions")
    op.drop_table("gps_positions")

    op.drop_index(op.f("ix_watch_devices_device_id"), table_name="watch_devices")
    op.drop_table("watch_devices")
