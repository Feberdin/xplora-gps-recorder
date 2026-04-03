"""
Purpose: Detect whether a device is moving or stationary by comparing consecutive GPS samples.
Inputs: Ordered position samples for one device plus configured distance and time thresholds.
Outputs: `movement_events` segments with distance, duration, and average speed.
Invariants: Distance uses the Haversine formula; movement classification is deterministic for the same inputs.
Debugging: When events look wrong, inspect the previous and current coordinates and compare the computed distance.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from math import asin, cos, radians, sin, sqrt

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.db.models import GPSPosition, MovementEvent

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class MovementDecision:
    """Computed movement classification for two consecutive points."""

    movement_type: str
    distance_m: float
    duration_s: float
    avg_speed_m_s: float


def haversine_distance_m(
    start_latitude: float,
    start_longitude: float,
    end_latitude: float,
    end_longitude: float,
) -> float:
    """Return the great-circle distance in meters between two geographic points."""

    earth_radius_m = 6_371_000

    delta_latitude = radians(end_latitude - start_latitude)
    delta_longitude = radians(end_longitude - start_longitude)
    start_latitude_rad = radians(start_latitude)
    end_latitude_rad = radians(end_latitude)

    haversine = (
        sin(delta_latitude / 2) ** 2
        + cos(start_latitude_rad) * cos(end_latitude_rad) * sin(delta_longitude / 2) ** 2
    )
    return 2 * earth_radius_m * asin(sqrt(haversine))


class MovementDetector:
    """Turn raw points into aggregated movement or stationary segments."""

    def __init__(self, settings: Settings) -> None:
        self.stationary_distance_meters = settings.stationary_distance_meters
        self.stationary_window_seconds = settings.stationary_window_seconds

    def process_position(self, db_session: Session, current_position: GPSPosition) -> MovementEvent | None:
        """Create or extend a movement event based on the latest position sample."""

        previous_position = self._load_previous_position(db_session, current_position)
        if previous_position is None:
            logger.debug("Skipping movement detection because no previous position exists")
            return None

        decision = self.classify(previous_position, current_position)
        last_event = self._load_last_event(db_session, current_position.device_id)

        if last_event and last_event.movement_type == decision.movement_type:
            if last_event.end_time == previous_position.timestamp:
                self._extend_event(last_event, current_position, decision)
                db_session.flush()
                return last_event

        event = MovementEvent(
            device_id=current_position.device_id,
            start_time=previous_position.timestamp,
            end_time=current_position.timestamp,
            distance_m=decision.distance_m,
            avg_speed=decision.avg_speed_m_s,
            movement_type=decision.movement_type,
        )
        db_session.add(event)
        db_session.flush()
        return event

    def classify(self, previous_position: GPSPosition, current_position: GPSPosition) -> MovementDecision:
        """Classify one pair of points into `movement` or `stationary`.

        Example:
        - Previous point: 52.5200 / 13.4050 at 10:00
        - Current point:  52.5201 / 13.4052 at 10:01
        - Result: a short segment with distance in meters and an average speed.
        """

        duration_s = max(
            (current_position.timestamp - previous_position.timestamp).total_seconds(),
            0.0,
        )
        distance_m = haversine_distance_m(
            previous_position.latitude,
            previous_position.longitude,
            current_position.latitude,
            current_position.longitude,
        )

        # Why this section exists:
        # The product requirement defines movement primarily via distance, with a stationary
        # threshold of less than 20 meters over short windows. This stays predictable for users.
        movement_type = "movement" if distance_m >= self.stationary_distance_meters else "stationary"
        if duration_s > self.stationary_window_seconds and distance_m < self.stationary_distance_meters:
            movement_type = "stationary"

        avg_speed_m_s = (
            current_position.speed
            if current_position.speed is not None
            else (distance_m / duration_s if duration_s > 0 else 0.0)
        )

        return MovementDecision(
            movement_type=movement_type,
            distance_m=distance_m,
            duration_s=duration_s,
            avg_speed_m_s=avg_speed_m_s,
        )

    def _load_previous_position(
        self,
        db_session: Session,
        current_position: GPSPosition,
    ) -> GPSPosition | None:
        statement = (
            select(GPSPosition)
            .where(
                GPSPosition.device_id == current_position.device_id,
                GPSPosition.timestamp < current_position.timestamp,
            )
            .order_by(GPSPosition.timestamp.desc())
            .limit(1)
        )
        return db_session.execute(statement).scalar_one_or_none()

    def _load_last_event(self, db_session: Session, device_id: str) -> MovementEvent | None:
        statement = (
            select(MovementEvent)
            .where(MovementEvent.device_id == device_id)
            .order_by(MovementEvent.end_time.desc())
            .limit(1)
        )
        return db_session.execute(statement).scalar_one_or_none()

    def _extend_event(
        self,
        event: MovementEvent,
        current_position: GPSPosition,
        decision: MovementDecision,
    ) -> None:
        total_distance = event.distance_m + decision.distance_m
        total_duration = max((current_position.timestamp - event.start_time).total_seconds(), 0.0)

        event.end_time = current_position.timestamp
        event.distance_m = total_distance
        event.avg_speed = total_distance / total_duration if total_duration > 0 else 0.0

