"""
Purpose: Talk to the current Xplora GraphQL API and normalize watch locations for storage.
Inputs: Xplora account credentials, optional country code for phone logins, and GraphQL payloads.
Outputs: A list of `DeviceLocationSnapshot` records with stable ids, names, timestamps, and coordinates.
Invariants: The client reuses one authenticated session and retries with a fresh login when auth expires.
Debugging: Enable `LOG_LEVEL=DEBUG` to inspect login mode, discovered watches, and per-watch polling failures.
"""

from __future__ import annotations

import hashlib
import logging
import math
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import requests
from requests import Response, Session
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from app.config import Settings

logger = logging.getLogger(__name__)

# Why this section exists:
# Xplora does not publish a stable public developer API, so we intentionally keep
# the minimal GraphQL contract we need in one place. These values are based on
# the community-maintained `pyxplora_api` project and let us poll locations
# without depending on undocumented REST placeholder endpoints.
OPEN_API_KEY = "fc45d50304511edbf67a12b93c413b6a"
OPEN_API_SECRET = "1e9b6fe0327711ed959359c157878dcb"
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.3"
)

SIGN_IN_MUTATION = """
mutation signInWithEmailOrPhone(
  $countryPhoneNumber: String
  $phoneNumber: String
  $password: String!
  $emailAddress: String
  $client: ClientType!
  $userLang: String!
  $timeZone: String!
) {
  signInWithEmailOrPhone(
    countryPhoneNumber: $countryPhoneNumber
    phoneNumber: $phoneNumber
    password: $password
    emailAddress: $emailAddress
    client: $client
    userLang: $userLang
    timeZone: $timeZone
  ) {
    id
    token
    refreshToken
    valid
    user {
      id
      name
      children {
        id
        guardian {
          id
          name
        }
        ward {
          id
          name
          nickname
          phoneNumber
        }
      }
    }
    w360 {
      token
      secret
    }
  }
}
"""

ASK_WATCH_LOCATE_QUERY = """
query AskWatchLocate($uid: String!) {
  askWatchLocate(uid: $uid)
}
"""

WATCH_LAST_LOCATE_QUERY = """
query WatchLastLocate($uid: String!) {
  watchLastLocate(uid: $uid) {
    tm
    lat
    lng
    rad
    country
    countryAbbr
    province
    city
    addr
    poi
    battery
    isCharging
    isAdjusted
    locateType
    step
    distance
    isInSafeZone
    safeZoneLabel
    batteryTm
  }
}
"""


class XploraClientError(RuntimeError):
    """Base exception raised for Xplora API integration problems."""


class XploraAuthenticationError(XploraClientError):
    """Raised when the client cannot establish or refresh an authenticated API session."""


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


@dataclass(slots=True)
class AuthState:
    """Authenticated Xplora session values reused across polling cycles."""

    access_token: str
    secret: str
    refresh_token: str | None
    user: dict[str, Any]


@dataclass(slots=True)
class WatchProfile:
    """Child/watch metadata extracted from the login response."""

    device_id: str
    name: str
    owner_name: str | None
    phone_number: str | None = None


class XploraClient:
    """GraphQL client for Xplora cloud data with per-watch normalization."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.session = self._build_session()
        self._auth_state: AuthState | None = None

    def fetch_device_snapshots(self) -> list[DeviceLocationSnapshot]:
        """Fetch the latest location for every watch linked to the configured account."""

        profiles = self._get_watch_profiles()
        if not profiles:
            logger.warning("Xplora login succeeded but no linked watches were returned")
            return []

        if self.settings.xplora_trigger_locate:
            self._request_fresh_locations(profiles)

        snapshots: list[DeviceLocationSnapshot] = []
        errors: list[str] = []

        for profile in profiles:
            try:
                location_payload = self._run_authenticated_query(
                    WATCH_LAST_LOCATE_QUERY,
                    {"uid": profile.device_id},
                    operation_name="WatchLastLocate",
                )
                location = location_payload.get("data", {}).get("watchLastLocate")
                snapshot = self._build_snapshot(profile, location)
                snapshots.append(snapshot)
            except XploraClientError as exc:
                logger.warning(
                    "Failed to poll watch location",
                    extra={"device_id": profile.device_id, "device_name": profile.name},
                    exc_info=exc,
                )
                errors.append(f"{profile.device_id}: {exc}")

        logger.info(
            "Fetched Xplora watch locations",
            extra={"watch_count": len(profiles), "snapshot_count": len(snapshots), "failed_watches": len(errors)},
        )

        if snapshots:
            return snapshots

        if errors:
            raise XploraClientError(
                "Xplora returned linked watches, but no valid locations could be fetched. "
                f"Sample error: {errors[0]}"
            )

        return []

    def _build_session(self) -> Session:
        """Create one HTTP session with retries for transient network or gateway failures."""

        retry = Retry(
            total=self.settings.xplora_max_retries,
            read=self.settings.xplora_max_retries,
            connect=self.settings.xplora_max_retries,
            backoff_factor=0.5,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset({"POST"}),
            raise_on_status=False,
        )

        adapter = HTTPAdapter(max_retries=retry)
        session = requests.Session()
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        session.headers.update(
            {
                "Accept": "application/json",
                "User-Agent": DEFAULT_USER_AGENT,
            }
        )
        return session

    def _get_watch_profiles(self) -> list[WatchProfile]:
        """Return linked watches from the current authenticated account session."""

        auth_state = self._ensure_authenticated()
        user = auth_state.user or {}
        children = user.get("children", [])
        profiles: list[WatchProfile] = []

        for child in children:
            if not isinstance(child, dict):
                continue

            ward = child.get("ward") or {}
            guardian = child.get("guardian") or {}
            device_id = ward.get("id")
            if not device_id:
                logger.debug("Skipping Xplora child entry without ward id", extra={"child": child})
                continue

            watch_name = ward.get("name") or ward.get("nickname") or f"Watch {device_id}"
            owner_name = guardian.get("name") or user.get("name")
            profiles.append(
                WatchProfile(
                    device_id=str(device_id),
                    name=str(watch_name),
                    owner_name=str(owner_name) if owner_name else None,
                    phone_number=str(ward["phoneNumber"]) if ward.get("phoneNumber") else None,
                )
            )

        return profiles

    def _request_fresh_locations(self, profiles: list[WatchProfile]) -> None:
        """Ask every watch for a fresh location before reading the last known point."""

        triggered = 0
        for profile in profiles:
            try:
                self._run_authenticated_query(
                    ASK_WATCH_LOCATE_QUERY,
                    {"uid": profile.device_id},
                    operation_name="AskWatchLocate",
                )
                triggered += 1
            except XploraClientError as exc:
                logger.debug(
                    "Xplora locate trigger failed; falling back to last known location",
                    extra={"device_id": profile.device_id},
                    exc_info=exc,
                )

        # Why this section exists:
        # The watch needs a short moment to answer the locate request. Waiting once after
        # all triggers keeps the polling cycle fast while still improving freshness.
        if triggered:
            time.sleep(1.0)

    def _ensure_authenticated(self, force: bool = False) -> AuthState:
        """Create or refresh an authenticated Xplora session."""

        if self._auth_state is not None and not force:
            return self._auth_state

        variables = self._build_login_variables()
        payload = self._post_graphql(
            SIGN_IN_MUTATION,
            variables,
            operation_name="signInWithEmailOrPhone",
            use_auth=False,
        )

        sign_in = payload.get("data", {}).get("signInWithEmailOrPhone")
        if not isinstance(sign_in, dict):
            raise XploraAuthenticationError(
                "Xplora login returned an unexpected payload. Verify the account credentials and country code."
            )

        user = sign_in.get("user")
        if not isinstance(user, dict):
            raise XploraAuthenticationError("Xplora login succeeded but did not return user information.")

        w360 = sign_in.get("w360") or {}
        access_token = w360.get("token") or sign_in.get("token")
        secret = w360.get("secret") or OPEN_API_SECRET
        if not access_token or not secret:
            raise XploraAuthenticationError("Xplora login did not return the access token required for follow-up queries.")

        self._auth_state = AuthState(
            access_token=str(access_token),
            secret=str(secret),
            refresh_token=str(sign_in["refreshToken"]) if sign_in.get("refreshToken") else None,
            user=user,
        )

        logger.info(
            "Authenticated against Xplora GraphQL API",
            extra={
                "login_mode": "email" if self._is_email_login() else "phone",
                "linked_watch_count": len(user.get("children", [])),
            },
        )
        return self._auth_state

    def _build_login_variables(self) -> dict[str, Any]:
        """Build the GraphQL login payload from the configured username and password."""

        username = self.settings.xplora_username.strip()
        is_email = self._is_email_login()
        return {
            "countryPhoneNumber": None if is_email else self.settings.xplora_country_code,
            "phoneNumber": None if is_email else username,
            "password": hashlib.md5(self.settings.xplora_password.get_secret_value().encode()).hexdigest(),
            "emailAddress": username if is_email else None,
            "client": "APP",
            "userLang": self.settings.xplora_user_lang,
            "timeZone": self.settings.xplora_time_zone,
        }

    def _is_email_login(self) -> bool:
        """Treat the Xplora username as an e-mail when it contains `@`."""

        return "@" in self.settings.xplora_username

    def _run_authenticated_query(
        self,
        query: str,
        variables: dict[str, Any],
        operation_name: str,
    ) -> dict[str, Any]:
        """Run one authenticated GraphQL query, retrying once after re-authentication."""

        self._ensure_authenticated()
        try:
            return self._post_graphql(query, variables, operation_name=operation_name, use_auth=True)
        except XploraAuthenticationError:
            logger.info("Xplora session expired or was rejected; retrying with a fresh login")
            self._auth_state = None
            self._ensure_authenticated(force=True)
            return self._post_graphql(query, variables, operation_name=operation_name, use_auth=True)

    def _post_graphql(
        self,
        query: str,
        variables: dict[str, Any],
        operation_name: str,
        *,
        use_auth: bool,
    ) -> dict[str, Any]:
        """Execute one GraphQL POST request and fail fast on malformed or rejected responses."""

        url = self.settings.xplora_base_url
        headers = self._build_headers(use_auth=use_auth)
        body = {
            "query": query,
            "variables": variables,
            "operationName": operation_name,
        }
        response = self.session.post(
            url,
            json=body,
            headers=headers,
            timeout=self.settings.xplora_timeout_seconds,
            verify=self.settings.xplora_verify_ssl,
        )
        self._raise_for_status(response, f"call Xplora GraphQL operation {operation_name}")

        try:
            payload = response.json()
        except ValueError as exc:
            raise XploraPayloadError(
                f"Xplora GraphQL operation {operation_name} returned invalid JSON from {url!r}."
            ) from exc

        if not isinstance(payload, dict):
            raise XploraPayloadError(
                f"Xplora GraphQL operation {operation_name} returned a non-object payload: {payload!r}"
            )

        errors = payload.get("errors") or []
        if errors:
            raise self._build_graphql_error(operation_name, errors)

        return payload

    def _build_headers(self, *, use_auth: bool) -> dict[str, str]:
        """Build the Xplora-specific authorization headers for open or authenticated calls."""

        if use_auth:
            auth_state = self._auth_state
            if auth_state is None:
                raise XploraAuthenticationError("No authenticated Xplora session is available.")
            authorization = f"Bearer {auth_state.access_token}:{auth_state.secret}"
        else:
            authorization = f"Open {OPEN_API_KEY}:{OPEN_API_SECRET}"

        return {
            "Content-Type": "application/json; charset=UTF-8",
            "H-Date": datetime.now(UTC).strftime("%a, %d %b %Y %H:%M:%S") + " GMT",
            "H-Tid": str(math.floor(time.time())),
            "H-BackDoor-Authorization": authorization,
        }

    def _build_graphql_error(self, operation_name: str, errors: list[Any]) -> XploraClientError:
        """Convert GraphQL error arrays into actionable exception types."""

        messages = []
        for error in errors:
            if isinstance(error, dict):
                messages.append(str(error.get("message", "Unknown GraphQL error")))
            else:
                messages.append(str(error))

        message = "; ".join(messages) if messages else "Unknown GraphQL error"
        if any("authentication failed" in part.lower() for part in messages):
            return XploraAuthenticationError(
                f"Xplora GraphQL operation {operation_name} was rejected because authentication failed."
            )

        return XploraClientError(f"Xplora GraphQL operation {operation_name} failed: {message}")

    def _build_snapshot(self, profile: WatchProfile, location: dict[str, Any] | None) -> DeviceLocationSnapshot:
        """Normalize one GraphQL watch location into the storage-facing snapshot schema."""

        if not isinstance(location, dict):
            raise XploraPayloadError(
                f"Watch {profile.device_id} did not return a location payload. The watch may be offline or not yet reachable."
            )

        latitude = self._coerce_required_float(location.get("lat"), "lat", profile.device_id)
        longitude = self._coerce_required_float(location.get("lng"), "lng", profile.device_id)
        timestamp = self._parse_timestamp(location.get("tm"))

        return DeviceLocationSnapshot(
            device_id=profile.device_id,
            name=profile.name,
            owner_name=profile.owner_name,
            latitude=latitude,
            longitude=longitude,
            timestamp=timestamp,
            accuracy=self._coerce_optional_float(location.get("rad")),
            speed=None,
            battery_level=self._coerce_optional_int(location.get("battery")),
        )

    def _parse_timestamp(self, value: Any) -> datetime:
        """Parse the Xplora location timestamp, which is currently delivered as Unix epoch seconds."""

        if value in (None, ""):
            return datetime.now(tz=UTC)

        if isinstance(value, str) and value.isdigit():
            return datetime.fromtimestamp(float(value), tz=UTC)

        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(float(value), tz=UTC)

        if isinstance(value, str):
            normalized = value.replace("Z", "+00:00")
            parsed = datetime.fromisoformat(normalized)
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)

        raise XploraPayloadError(f"Unsupported Xplora timestamp value: {value!r}")

    def _coerce_required_float(self, value: Any, field_name: str, device_id: str) -> float:
        """Convert required numeric values and keep the error message tied to the current watch."""

        if value in (None, ""):
            raise XploraPayloadError(f"Missing required Xplora location field {field_name!r} for watch {device_id}.")
        return float(value)

    def _coerce_optional_float(self, value: Any) -> float | None:
        if value in (None, ""):
            return None
        return float(value)

    def _coerce_optional_int(self, value: Any) -> int | None:
        if value in (None, ""):
            return None
        return int(float(value))

    def _raise_for_status(self, response: Response, action: str) -> None:
        """Raise actionable exceptions with context instead of silent HTTP errors."""

        if response.ok:
            return

        message = (
            f"Failed to {action}. "
            f"HTTP status={response.status_code}. "
            f"Body preview={response.text[:300]!r}. "
            "Verify network reachability, credentials, and whether the Xplora endpoint contract changed."
        )
        if response.status_code in {401, 403}:
            raise XploraAuthenticationError(message)
        raise XploraClientError(message)
