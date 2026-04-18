"""
Purpose: Verify the Xplora GraphQL client login flow, headers, and snapshot normalization.
Inputs: Synthetic GraphQL responses returned by a fake HTTP session.
Outputs: Assertions that the client authenticates correctly and emits valid snapshots.
Invariants: The client must support e-mail and phone login modes and fail fast on missing coordinates.
Debugging: If these tests fail, inspect the fake session call order and the GraphQL payload builder first.
"""

from __future__ import annotations

import json
from datetime import UTC

import pytest

from app.xplora_client import WatchProfile, XploraClient, XploraPayloadError
from tests.conftest import make_settings


class FakeResponse:
    """Small `requests.Response` stand-in for deterministic unit tests."""

    def __init__(self, payload, status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code
        self.ok = status_code < 400
        self.text = json.dumps(payload)

    def json(self):
        return self._payload


class FakeSession:
    """Record outgoing requests and return canned responses in order."""

    def __init__(self, responses) -> None:
        self.responses = list(responses)
        self.calls = []

    def post(self, url, json, headers, timeout, verify):
        self.calls.append(
            {
                "url": url,
                "json": json,
                "headers": headers,
                "timeout": timeout,
                "verify": verify,
            }
        )
        if not self.responses:
            raise AssertionError("The test client issued more HTTP calls than expected.")
        return self.responses.pop(0)


def test_fetch_device_snapshots_uses_graphql_email_login(monkeypatch) -> None:
    monkeypatch.setattr("app.xplora_client.time.sleep", lambda _: None)

    client = XploraClient(
        make_settings(
            XPLORA_USERNAME="parent@example.test",
            XPLORA_PASSWORD="secret",
            XPLORA_USER_LANG="de-DE",
            XPLORA_TIME_ZONE="Europe/Berlin",
        )
    )
    client.session = FakeSession(
        [
            FakeResponse(
                {
                    "data": {
                        "signInWithEmailOrPhone": {
                            "token": "access-token",
                            "refreshToken": "refresh-token",
                            "user": {
                                "name": "Parent",
                                "children": [
                                    {
                                        "guardian": {"id": "guardian-1", "name": "Parent"},
                                        "ward": {"id": "watch-1", "name": "Lena", "phoneNumber": "15123456"},
                                    }
                                ],
                            },
                            "w360": {"token": "bearer-token", "secret": "bearer-secret"},
                        }
                    }
                }
            ),
            FakeResponse({"data": {"askWatchLocate": True}}),
            FakeResponse(
                {
                    "data": {
                        "watchLastLocate": {
                            "tm": 1760011200,
                            "lat": "52.123",
                            "lng": "8.456",
                            "rad": "15",
                            "battery": 77,
                        }
                    }
                }
            ),
        ]
    )

    snapshots = client.fetch_device_snapshots()

    assert len(snapshots) == 1
    snapshot = snapshots[0]
    assert snapshot.device_id == "watch-1"
    assert snapshot.name == "Lena"
    assert snapshot.owner_name == "Parent"
    assert snapshot.latitude == 52.123
    assert snapshot.longitude == 8.456
    assert snapshot.accuracy == 15.0
    assert snapshot.battery_level == 77
    assert snapshot.timestamp.tzinfo == UTC

    login_call = client.session.calls[0]
    assert login_call["json"]["variables"]["emailAddress"] == "parent@example.test"
    assert login_call["json"]["variables"]["phoneNumber"] is None
    assert login_call["headers"]["H-BackDoor-Authorization"].startswith("Open ")

    locate_call = client.session.calls[1]
    assert locate_call["headers"]["H-BackDoor-Authorization"] == "Bearer bearer-token:bearer-secret"


def test_build_login_variables_uses_phone_mode_when_country_code_is_present() -> None:
    client = XploraClient(
        make_settings(
            XPLORA_USERNAME="15123456",
            XPLORA_COUNTRY_CODE="49",
            XPLORA_PASSWORD="secret",
        )
    )

    variables = client._build_login_variables()

    assert variables["emailAddress"] is None
    assert variables["phoneNumber"] == "15123456"
    assert variables["countryPhoneNumber"] == "49"
    assert variables["password"] == "5ebe2294ecd0e0f08eab7690d2a6ee69"


def test_build_snapshot_raises_for_missing_coordinates() -> None:
    client = XploraClient(make_settings())

    with pytest.raises(XploraPayloadError):
        client._build_snapshot(
            profile=WatchProfile(device_id="watch-1", name="Lena", owner_name="Parent"),
            location={"tm": 1760011200},
        )
