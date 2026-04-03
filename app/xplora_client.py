"""
Purpose: Authenticate against the Xplora cloud API and normalize device/location responses.
Inputs: API credentials, configurable endpoint paths, and JSON payloads returned by the cloud service.
Outputs: A list of `DeviceLocationSnapshot` records that the ingestion pipeline can store safely.
Invariants: Every snapshot emitted by this client contains a stable device id, coordinates, and timestamp.
Debugging: Enable `LOG_LEVEL=DEBUG` and compare raw API payloads with the normalization helpers if a field is missing.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urljoin

import requests
from requests import Response, Session
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from app.config import Settings

logger = logging.getLogger(__name__)


class XploraClientError(RuntimeError):
    """Base exception raised for Xplora API integration problems."""


class XploraAuthenticationError(XploraClientError):
    """Raised when the client cannot establish an authenticated API session."""


class XploraPayloadError(XploraClientError):
    """Raised when the cloud API returns a payload that cannot be normalized."""


@dataclass(slots=True)
class DeviceLocationSnapshot:
    """Normalized location sample ready for storage."""

    device_id: str
    name: str
    owner_name: str | None
    latitude: float
    longitude: float
    timestamp: datetime
    accuracy: float | None = None
    speed: float | None = None
    battery_level: int | None = None


class XploraClient:
    """Thin API client that hides session handling and payload normalization details."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.session = self._build_session()
        self._authenticated = False

    def fetch_device_snapshots(self) -> list[DeviceLocationSnapshot]:
        """Fetch all available devices and their latest coordinates from the Xplora API."""

        self._authenticate()
        devices_payload = self._request_json("GET", self.settings.xplora_devices_path)
        device_records = self._extract_collection(devices_payload)
        logger.debug("Fetched device inventory from Xplora", extra={"device_count": len(device_records)})

        location_map = self._load_location_payloads(device_records)
        snapshots: list[DeviceLocationSnapshot] = []

        for device_record in device_records:
            snapshot = self._build_snapshot(device_record, location_map)
            snapshots.append(snapshot)

        return snapshots

    def _build_session(self) -> Session:
        """Create an HTTP session with retry behavior for transient API failures."""

        retry = Retry(
            total=self.settings.xplora_max_retries,
            read=self.settings.xplora_max_retries,
            connect=self.settings.xplora_max_retries,
            backoff_factor=0.5,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset({"GET", "POST"}),
            raise_on_status=False,
        )

        adapter = HTTPAdapter(max_retries=retry)
        session = requests.Session()
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        session.headers.update({"Accept": "application/json"})
        return session

    def _authenticate(self) -> None:
        """Authenticate once and reuse cookies or bearer tokens for later calls."""

        if self._authenticated:
            return

        login_payload = {
            "username": self.settings.xplora_username,
            "password": self.settings.xplora_password.get_secret_value(),
        }

        response = self.session.post(
            self._build_url(self.settings.xplora_login_path),
            json=login_payload,
            timeout=self.settings.xplora_timeout_seconds,
            verify=self.settings.xplora_verify_ssl,
        )
        self._raise_for_status(response, "authenticate against Xplora")

        token = self._extract_token(response)
        if token:
            self.session.headers["Authorization"] = f"Bearer {token}"

        self._authenticated = True
        logger.info("Authenticated successfully against Xplora")

    def _load_location_payloads(self, device_records: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        """Fetch optional device-specific location payloads when a second endpoint is configured."""

        if not self.settings.xplora_location_path:
            return {}

        location_path = self.settings.xplora_location_path
        location_map: dict[str, dict[str, Any]] = {}

        if "{device_id}" in location_path:
            for device_record in device_records:
                device_id = self._extract_device_id(device_record)
                payload = self._request_json("GET", location_path.format(device_id=device_id))
                if isinstance(payload, dict):
                    location_map[device_id] = payload
            return location_map

        payload = self._request_json("GET", location_path)
        for record in self._extract_collection(payload):
            try:
                device_id = self._extract_device_id(record)
            except XploraPayloadError:
                logger.debug("Skipping location payload without device id")
                continue
            location_map[device_id] = record

        return location_map

    def _build_snapshot(
        self,
        device_record: dict[str, Any],
        location_map: dict[str, dict[str, Any]],
    ) -> DeviceLocationSnapshot:
        """Merge device and location payloads into one normalized storage object."""

        device_id = self._extract_device_id(device_record)
        location_record = location_map.get(device_id, {})

        combined_payload: dict[str, Any] = {
            **device_record,
            **location_record,
            "device": device_record,
            "location_payload": location_record,
        }

        latitude = self._extract_float(
            combined_payload,
            candidate_paths=[("location", "latitude"), ("location", "lat"), ("coordinates", "latitude")],
            candidate_keys={"latitude", "lat"},
            field_name="latitude",
        )
        longitude = self._extract_float(
            combined_payload,
            candidate_paths=[("location", "longitude"), ("location", "lon"), ("location", "lng")],
            candidate_keys={"longitude", "lon", "lng"},
            field_name="longitude",
        )

        snapshot = DeviceLocationSnapshot(
            device_id=device_id,
            name=str(
                self._extract_value(
                    combined_payload,
                    candidate_paths=[("profile", "name"), ("device", "name")],
                    candidate_keys={"name", "deviceName", "nickname"},
                    default=f"Watch {device_id}",
                )
            ),
            owner_name=self._extract_optional_string(
                combined_payload,
                candidate_paths=[("owner", "name"), ("child", "name"), ("profile", "ownerName")],
                candidate_keys={"owner_name", "ownerName", "childName", "guardianName"},
            ),
            latitude=latitude,
            longitude=longitude,
            timestamp=self._extract_timestamp(combined_payload),
            accuracy=self._extract_optional_float(
                combined_payload,
                candidate_paths=[("location", "accuracy")],
                candidate_keys={"accuracy", "horizontalAccuracy"},
            ),
            speed=self._extract_optional_float(
                combined_payload,
                candidate_paths=[("location", "speed")],
                candidate_keys={"speed", "velocity"},
            ),
            battery_level=self._extract_optional_int(
                combined_payload,
                candidate_paths=[("battery", "level")],
                candidate_keys={"batteryLevel", "battery", "battery_percent"},
            ),
        )
        return snapshot

    def _request_json(self, method: str, path: str) -> dict[str, Any] | list[Any]:
        """Perform one HTTP request and parse the JSON response."""

        url = self._build_url(path)
        logger.debug("Calling Xplora API", extra={"method": method, "url": url})
        response = self.session.request(
            method,
            url,
            timeout=self.settings.xplora_timeout_seconds,
            verify=self.settings.xplora_verify_ssl,
        )
        self._raise_for_status(response, f"call Xplora endpoint {url}")

        try:
            return response.json()
        except ValueError as exc:
            raise XploraPayloadError(f"Xplora endpoint {url} did not return valid JSON") from exc

    def _build_url(self, path: str) -> str:
        """Resolve a relative path against the configured base URL."""

        if path.startswith("http://") or path.startswith("https://"):
            return path
        return urljoin(f"{self.settings.xplora_base_url.rstrip('/')}/", path.lstrip("/"))

    def _raise_for_status(self, response: Response, action: str) -> None:
        """Raise actionable exceptions with context instead of silent HTTP errors."""

        if response.ok:
            return

        message = (
            f"Failed to {action}. "
            f"HTTP status={response.status_code}. "
            f"Body preview={response.text[:300]!r}. "
            "Verify credentials, endpoint paths, and the cloud API contract."
        )
        if response.status_code in {401, 403}:
            raise XploraAuthenticationError(message)
        raise XploraClientError(message)

    def _extract_token(self, response: Response) -> str | None:
        """Find a bearer token in common authentication response shapes."""

        try:
            payload = response.json()
        except ValueError:
            return None

        token = self._extract_value(
            payload,
            candidate_paths=[("data", "token"), ("auth", "token")],
            candidate_keys={"accessToken", "token", "jwt"},
        )
        return str(token) if token else None

    def _extract_collection(self, payload: dict[str, Any] | list[Any]) -> list[dict[str, Any]]:
        """Normalize top-level lists so the rest of the code can iterate predictably."""

        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]

        if isinstance(payload, dict):
            for key in ("devices", "children", "watches", "items", "data", "results"):
                value = payload.get(key)
                if isinstance(value, list):
                    return [item for item in value if isinstance(item, dict)]

            if any(key in payload for key in ("deviceId", "device_id", "latitude", "lat")):
                return [payload]

        raise XploraPayloadError(
            "Unable to find a device collection in the Xplora response. "
            "Adjust XPLORA_DEVICES_PATH or extend the normalization rules."
        )

    def _extract_device_id(self, payload: dict[str, Any]) -> str:
        """Return the stable external device id from a payload."""

        value = self._extract_value(
            payload,
            candidate_paths=[("device", "id"), ("profile", "deviceId")],
            candidate_keys={"deviceId", "device_id", "watchId", "watch_id", "id"},
        )
        if value in (None, ""):
            raise XploraPayloadError(f"Missing device id in payload: {payload}")
        return str(value)

    def _extract_timestamp(self, payload: dict[str, Any]) -> datetime:
        """Parse timestamps in ISO-8601 or Unix epoch format."""

        raw_value = self._extract_value(
            payload,
            candidate_paths=[("location", "timestamp"), ("gps", "timestamp")],
            candidate_keys={"timestamp", "recordedAt", "createdAt", "updatedAt", "lastSeenAt"},
            default=None,
        )

        if raw_value is None:
            return datetime.now(tz=UTC)

        if isinstance(raw_value, (int, float)):
            return datetime.fromtimestamp(float(raw_value), tz=UTC)

        if isinstance(raw_value, str):
            normalized = raw_value.replace("Z", "+00:00")
            parsed = datetime.fromisoformat(normalized)
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)

        raise XploraPayloadError(f"Unsupported timestamp value {raw_value!r}")

    def _extract_optional_string(
        self,
        payload: dict[str, Any],
        candidate_paths: list[tuple[str, ...]],
        candidate_keys: set[str],
    ) -> str | None:
        value = self._extract_value(payload, candidate_paths, candidate_keys, default=None)
        return None if value in (None, "") else str(value)

    def _extract_optional_float(
        self,
        payload: dict[str, Any],
        candidate_paths: list[tuple[str, ...]],
        candidate_keys: set[str],
    ) -> float | None:
        value = self._extract_value(payload, candidate_paths, candidate_keys, default=None)
        if value in (None, ""):
            return None
        return float(value)

    def _extract_optional_int(
        self,
        payload: dict[str, Any],
        candidate_paths: list[tuple[str, ...]],
        candidate_keys: set[str],
    ) -> int | None:
        value = self._extract_value(payload, candidate_paths, candidate_keys, default=None)
        if value in (None, ""):
            return None
        return int(float(value))

    def _extract_float(
        self,
        payload: dict[str, Any],
        candidate_paths: list[tuple[str, ...]],
        candidate_keys: set[str],
        field_name: str,
    ) -> float:
        value = self._extract_value(payload, candidate_paths, candidate_keys, default=None)
        if value in (None, ""):
            raise XploraPayloadError(
                f"Missing {field_name} in payload for device {self._extract_device_id(payload)}"
            )
        return float(value)

    def _extract_value(
        self,
        payload: dict[str, Any] | list[Any],
        candidate_paths: list[tuple[str, ...]],
        candidate_keys: set[str],
        default: Any = None,
    ) -> Any:
        """Try explicit paths first, then fall back to recursive key lookup."""

        for path in candidate_paths:
            value = self._value_at_path(payload, path)
            if value not in (None, ""):
                return value

        found = self._find_first_matching_key(payload, candidate_keys)
        return default if found in (None, "") else found

    def _value_at_path(self, payload: dict[str, Any] | list[Any], path: tuple[str, ...]) -> Any:
        current: Any = payload
        for key in path:
            if not isinstance(current, dict):
                return None
            current = current.get(key)
        return current

    def _find_first_matching_key(self, payload: dict[str, Any] | list[Any], keys: set[str]) -> Any:
        if isinstance(payload, dict):
            for key, value in payload.items():
                if key in keys and value not in (None, ""):
                    return value
            for value in payload.values():
                found = self._find_first_matching_key(value, keys)
                if found not in (None, ""):
                    return found

        if isinstance(payload, list):
            for item in payload:
                found = self._find_first_matching_key(item, keys)
                if found not in (None, ""):
                    return found

        return None

