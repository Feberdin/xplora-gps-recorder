"""
Purpose: Protect the tile-rounding logic used by heatmap aggregation.
Inputs: Known coordinates that exercise decimal rounding boundaries.
Outputs: Assertions for deterministic tile coordinates.
Invariants: Heatmap rounding must stay stable across Python and database upgrades.
Debugging: If tiles shift, inspect `HEATMAP_TILE_PRECISION` and Decimal rounding behavior.
"""

from __future__ import annotations

from decimal import Decimal

from app.heatmap import HeatmapService, tile_coordinate


def test_tile_coordinate_uses_half_up_rounding() -> None:
    assert tile_coordinate(52.1235, 3) == Decimal("52.124")
    assert tile_coordinate(52.1234, 3) == Decimal("52.123")


def test_heatmap_service_returns_expected_tile_pair() -> None:
    service = HeatmapService(precision=3)

    lat_tile, lon_tile = service.tile_for_position(52.12345, 8.45654)

    assert lat_tile == Decimal("52.123")
    assert lon_tile == Decimal("8.457")
