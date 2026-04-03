"""
Purpose: Convert raw GPS points into rounded tiles and visit counters for hotspot analysis.
Inputs: Device ids and latitude/longitude pairs from persisted position samples.
Outputs: Updated `heatmap_tiles` rows and deterministic tile coordinates for API responses.
Invariants: Tile precision must match the configured grid rounding used across ingestion and queries.
Debugging: If counts look fragmented, verify `HEATMAP_TILE_PRECISION` stayed constant across deployments.
"""

from __future__ import annotations

import logging
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import GPSPosition, HeatmapTile

logger = logging.getLogger(__name__)


def tile_coordinate(value: float, precision: int) -> Decimal:
    """Round one coordinate into a deterministic heatmap tile."""

    quantizer = Decimal("1").scaleb(-precision)
    return Decimal(str(value)).quantize(quantizer, rounding=ROUND_HALF_UP)


class HeatmapService:
    """Update visit counters and expose tile math for other modules."""

    def __init__(self, precision: int) -> None:
        self.precision = precision

    def tile_for_position(self, latitude: float, longitude: float) -> tuple[Decimal, Decimal]:
        return tile_coordinate(latitude, self.precision), tile_coordinate(longitude, self.precision)

    def record_visit(self, db_session: Session, position: GPSPosition) -> HeatmapTile:
        """Increment one heatmap tile for the latest stored position."""

        lat_tile, lon_tile = self.tile_for_position(position.latitude, position.longitude)

        statement = select(HeatmapTile).where(
            HeatmapTile.device_id == position.device_id,
            HeatmapTile.lat_tile == lat_tile,
            HeatmapTile.lon_tile == lon_tile,
        )
        tile = db_session.execute(statement).scalar_one_or_none()

        if tile is None:
            tile = HeatmapTile(
                device_id=position.device_id,
                lat_tile=lat_tile,
                lon_tile=lon_tile,
                visit_count=1,
            )
            db_session.add(tile)
            logger.debug(
                "Created new heatmap tile",
                extra={"device_id": position.device_id, "lat_tile": str(lat_tile), "lon_tile": str(lon_tile)},
            )
        else:
            tile.visit_count += 1

        db_session.flush()
        return tile

