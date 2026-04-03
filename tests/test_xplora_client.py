"""
Purpose: Verify the payload normalization layer for the Xplora API client.
Inputs: Representative device payloads with nested coordinates and varying field names.
Outputs: Assertions that normalized snapshots contain the required fields.
Invariants: Unsupported payload shapes must fail fast with actionable exceptions.
Debugging: If a test fails after API changes, inspect the raw payload and update the extraction rules.
"""

from __future__ import annotations

from datetime import UTC

import pytest

from app.xplora_client import XploraClient, XploraPayloadError
from tests.conftest import make_settings


def test_extract_collection_reads_devices_key() -> None:
    client = XploraClient(make_settings())

    payload = {"devices": [{"deviceId": "watch-1"}, {"deviceId": "watch-2"}]}

    records = client._extract_collection(payload)

    assert len(records) == 2


def test_build_snapshot_normalizes_nested_payload() -> None:
    client = XploraClient(make_settings())
    device_payload = {
        "deviceId": "watch-1",
        "name": "Lena",
        "owner": {"name": "Mom"},
        "location": {
            "latitude": 52.123,
            "longitude": 8.456,
            "timestamp": "2026-04-03T10:00:00Z",
            "accuracy": 15,
        },
        "battery": {"level": 77},
    }

    snapshot = client._build_snapshot(device_payload, location_map={})

    assert snapshot.device_id == "watch-1"
    assert snapshot.name == "Lena"
    assert snapshot.owner_name == "Mom"
    assert snapshot.latitude == 52.123
    assert snapshot.longitude == 8.456
    assert snapshot.timestamp.tzinfo == UTC
    assert snapshot.battery_level == 77


def test_build_snapshot_raises_for_missing_coordinates() -> None:
    client = XploraClient(make_settings())
    broken_payload = {"deviceId": "watch-1", "name": "Lena"}

    with pytest.raises(XploraPayloadError):
        client._build_snapshot(broken_payload, location_map={})
