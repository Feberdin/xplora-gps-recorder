"""
Purpose: Validate movement classification and distance calculations for core analytics logic.
Inputs: Synthetic GPS positions with predictable coordinates and timestamps.
Outputs: Assertions that protect against regressions in movement detection.
Invariants: The same coordinates must always produce the same distance and classification.
Debugging: If these tests fail, inspect threshold configuration and timestamp ordering first.
"""

from __future__ import annotations

from datetime import UTC, datetime

from app.db.models import GPSPosition
from app.movement_detection import MovementDetector, haversine_distance_m
from tests.conftest import make_settings


def test_haversine_distance_is_zero_for_identical_points() -> None:
    assert haversine_distance_m(52.52, 13.405, 52.52, 13.405) == 0.0


def test_movement_detector_classifies_stationary_points() -> None:
    detector = MovementDetector(make_settings(STATIONARY_DISTANCE_METERS=20))
    previous = GPSPosition(
        device_id="watch-1",
        timestamp=datetime(2026, 4, 3, 10, 0, tzinfo=UTC),
        latitude=52.5200,
        longitude=13.4050,
    )
    current = GPSPosition(
        device_id="watch-1",
        timestamp=datetime(2026, 4, 3, 10, 1, tzinfo=UTC),
        latitude=52.52001,
        longitude=13.40501,
    )

    decision = detector.classify(previous, current)

    assert decision.movement_type == "stationary"
    assert decision.distance_m < 20


def test_movement_detector_classifies_real_movement() -> None:
    detector = MovementDetector(make_settings(STATIONARY_DISTANCE_METERS=20))
    previous = GPSPosition(
        device_id="watch-1",
        timestamp=datetime(2026, 4, 3, 10, 0, tzinfo=UTC),
        latitude=52.5200,
        longitude=13.4050,
    )
    current = GPSPosition(
        device_id="watch-1",
        timestamp=datetime(2026, 4, 3, 10, 2, tzinfo=UTC),
        latitude=52.5215,
        longitude=13.4100,
    )

    decision = detector.classify(previous, current)

    assert decision.movement_type == "movement"
    assert decision.distance_m >= 20
    assert decision.avg_speed_m_s > 0
