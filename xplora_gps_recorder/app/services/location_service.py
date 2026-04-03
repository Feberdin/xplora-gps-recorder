"""
Purpose: Orchestrate the end-to-end ingestion pipeline for Xplora polling cycles.
Inputs: Normalized snapshots from the Xplora client plus service collaborators for enrichment and analytics.
Outputs: Stored positions, enrichment rows, heatmap updates, movement events, and optional MQTT messages.
Invariants: One failing device must not block the rest of the polling cycle.
Debugging: Start with the per-device log lines to see whether the failure happened at fetch, store, enrich, or publish time.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.db.models import GPSPosition, WatchDevice
from app.heatmap import HeatmapService
from app.movement_detection import MovementDetector
from app.mqtt_publisher import MqttPublisher
from app.reverse_geocode import ReverseGeocoder
from app.xplora_client import DeviceLocationSnapshot, XploraClient, XploraClientError

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class PollingSummary:
    """Summary of one scheduler run for logs and health monitoring."""

    discovered_devices: int = 0
    stored_positions: int = 0
    duplicate_positions: int = 0
    failed_devices: int = 0
    errors: list[str] = field(default_factory=list)


class LocationIngestionService:
    """Run one full polling cycle and persist derived analytics."""

    def __init__(
        self,
        session_factory: sessionmaker,
        xplora_client: XploraClient,
        reverse_geocoder: ReverseGeocoder,
        movement_detector: MovementDetector,
        heatmap_service: HeatmapService,
        mqtt_publisher: MqttPublisher,
    ) -> None:
        self.session_factory = session_factory
        self.xplora_client = xplora_client
        self.reverse_geocoder = reverse_geocoder
        self.movement_detector = movement_detector
        self.heatmap_service = heatmap_service
        self.mqtt_publisher = mqtt_publisher

    def poll_once(self) -> PollingSummary:
        """Fetch fresh locations and process each device independently."""

        summary = PollingSummary()
        try:
            snapshots = self.xplora_client.fetch_device_snapshots()
        except XploraClientError as exc:
            logger.exception("Xplora polling failed before device processing started")
            summary.failed_devices = 1
            summary.errors.append(str(exc))
            return summary

        summary.discovered_devices = len(snapshots)

        for snapshot in snapshots:
            try:
                stored = self._store_snapshot(snapshot)
                if stored:
                    summary.stored_positions += 1
                else:
                    summary.duplicate_positions += 1
            except Exception as exc:
                logger.exception(
                    "Device processing failed",
                    extra={"device_id": snapshot.device_id, "device_name": snapshot.name},
                )
                summary.failed_devices += 1
                summary.errors.append(f"{snapshot.device_id}: {exc}")

        logger.info(
            "Completed polling cycle",
            extra={
                "discovered_devices": summary.discovered_devices,
                "stored_positions": summary.stored_positions,
                "duplicate_positions": summary.duplicate_positions,
                "failed_devices": summary.failed_devices,
            },
        )
        return summary

    def _store_snapshot(self, snapshot: DeviceLocationSnapshot) -> bool:
        """Persist one snapshot and all derived analytics in a single transaction."""

        with self.session_factory() as db_session:
            device = self._upsert_device(db_session, snapshot)
            existing_position = self._find_existing_position(db_session, snapshot)
            if existing_position is not None:
                logger.info(
                    "Skipping duplicate GPS position",
                    extra={
                        "device_id": snapshot.device_id,
                        "timestamp": snapshot.timestamp.isoformat(),
                    },
                )
                db_session.rollback()
                return False

            position = GPSPosition(
                device_id=device.device_id,
                timestamp=snapshot.timestamp,
                latitude=snapshot.latitude,
                longitude=snapshot.longitude,
                accuracy=snapshot.accuracy,
                speed=snapshot.speed,
                battery_level=snapshot.battery_level,
            )
            db_session.add(position)
            db_session.flush()

            enrichment = self.reverse_geocoder.enrich_position(db_session, position)
            self.heatmap_service.record_visit(db_session, position)
            movement_event = self.movement_detector.process_position(db_session, position)

            db_session.commit()

        self.mqtt_publisher.publish_location(snapshot, enrichment)
        self.mqtt_publisher.publish_movement(snapshot.device_id, movement_event)
        self.mqtt_publisher.publish_battery(snapshot)
        return True

    def _upsert_device(self, db_session, snapshot: DeviceLocationSnapshot) -> WatchDevice:
        """Create or refresh the watch metadata before storing positions."""

        statement = select(WatchDevice).where(WatchDevice.device_id == snapshot.device_id)
        device = db_session.execute(statement).scalar_one_or_none()

        if device is None:
            device = WatchDevice(
                device_id=snapshot.device_id,
                name=snapshot.name,
                owner_name=snapshot.owner_name,
            )
            db_session.add(device)
            db_session.flush()
            return device

        device.name = snapshot.name
        device.owner_name = snapshot.owner_name
        db_session.flush()
        return device

    def _find_existing_position(
        self, db_session, snapshot: DeviceLocationSnapshot
    ) -> GPSPosition | None:
        statement = select(GPSPosition).where(
            GPSPosition.device_id == snapshot.device_id,
            GPSPosition.timestamp == snapshot.timestamp,
        )
        return db_session.execute(statement).scalar_one_or_none()
