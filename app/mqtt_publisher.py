"""
Purpose: Publish location, movement, and battery updates for Home Assistant and other MQTT consumers.
Inputs: Normalized position snapshots, enrichment data, and optional movement events from the ingestion pipeline.
Outputs: JSON messages on stable MQTT topics under the configured prefix.
Invariants: Publishing failures must never crash the polling loop; secrets stay out of logs.
Debugging: If Home Assistant sees no updates, inspect connection logs and subscribe with `mosquitto_sub`.
"""

from __future__ import annotations

import json
import logging
import threading
from typing import Any

import paho.mqtt.client as mqtt

from app.config import Settings
from app.db.models import LocationEnriched, MovementEvent
from app.xplora_client import DeviceLocationSnapshot

logger = logging.getLogger(__name__)


class MqttPublisher:
    """Best-effort MQTT publisher that is safe to disable or run without a broker."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.enabled = bool(settings.mqtt_enabled and settings.mqtt_host)
        self._lock = threading.Lock()
        self._connected = False
        self._client: mqtt.Client | None = None

        if not self.enabled:
            logger.info("MQTT publishing disabled")
            return

        self._client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id=settings.app_name,
            protocol=mqtt.MQTTv311,
        )
        if settings.mqtt_user:
            self._client.username_pw_set(
                username=settings.mqtt_user,
                password=settings.mqtt_password.get_secret_value()
                if settings.mqtt_password
                else None,
            )
        if settings.mqtt_tls_enabled:
            self._client.tls_set()

        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect

    def connect(self) -> None:
        if not self.enabled or self._client is None:
            return

        with self._lock:
            if self._connected:
                return
            try:
                self._client.connect(self.settings.mqtt_host, self.settings.mqtt_port, keepalive=60)
                self._client.loop_start()
                logger.info("Connected to MQTT broker", extra={"host": self.settings.mqtt_host})
            except Exception as exc:
                logger.warning(
                    "MQTT connection failed; continuing without broker publishing", exc_info=exc
                )

    def publish_location(
        self,
        snapshot: DeviceLocationSnapshot,
        enrichment: LocationEnriched | None,
    ) -> None:
        payload = {
            "device_id": snapshot.device_id,
            "lat": snapshot.latitude,
            "lon": snapshot.longitude,
            "timestamp": snapshot.timestamp.isoformat(),
            "place": enrichment.place_name if enrichment else None,
            "city": enrichment.city if enrichment else None,
        }
        self._publish(f"{self.settings.mqtt_topic_prefix}/{snapshot.device_id}/location", payload)

    def publish_movement(self, device_id: str, movement_event: MovementEvent | None) -> None:
        if movement_event is None:
            return

        payload = {
            "device_id": device_id,
            "movement_type": movement_event.movement_type,
            "start_time": movement_event.start_time.isoformat(),
            "end_time": movement_event.end_time.isoformat(),
            "distance_m": movement_event.distance_m,
            "avg_speed": movement_event.avg_speed,
        }
        self._publish(f"{self.settings.mqtt_topic_prefix}/{device_id}/movement", payload)

    def publish_battery(self, snapshot: DeviceLocationSnapshot) -> None:
        if snapshot.battery_level is None:
            return

        payload = {
            "device_id": snapshot.device_id,
            "battery_level": snapshot.battery_level,
            "timestamp": snapshot.timestamp.isoformat(),
        }
        self._publish(f"{self.settings.mqtt_topic_prefix}/{snapshot.device_id}/battery", payload)

    def close(self) -> None:
        if not self.enabled or self._client is None:
            return

        with self._lock:
            self._client.loop_stop()
            self._client.disconnect()
            self._connected = False

    def _publish(self, topic: str, payload: dict[str, Any]) -> None:
        """Publish one JSON message without interrupting the polling pipeline on failure."""

        if not self.enabled or self._client is None:
            return

        self.connect()
        try:
            info = self._client.publish(topic, json.dumps(payload), qos=1, retain=False)
            if info.rc != mqtt.MQTT_ERR_SUCCESS:
                logger.warning(
                    "MQTT publish returned non-success status",
                    extra={"topic": topic, "rc": info.rc},
                )
        except Exception as exc:
            logger.warning("MQTT publish failed", extra={"topic": topic}, exc_info=exc)

    def _on_connect(
        self, client: mqtt.Client, userdata: Any, flags: Any, reason_code: Any, properties: Any
    ) -> None:
        self._connected = True
        logger.info("MQTT broker connection established", extra={"reason_code": str(reason_code)})

    def _on_disconnect(
        self,
        client: mqtt.Client,
        userdata: Any,
        disconnect_flags: Any,
        reason_code: Any,
        properties: Any,
    ) -> None:
        self._connected = False
        logger.warning("MQTT broker disconnected", extra={"reason_code": str(reason_code)})
