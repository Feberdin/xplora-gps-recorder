"""
Purpose: Reverse-geocode latitude/longitude pairs and cache results to reduce external API load.
Inputs: GPS positions from the ingestion pipeline and optional Redis/PostgreSQL cache backends.
Outputs: `LocationEnriched` rows linked to raw positions plus reusable cache entries.
Invariants: Public Nominatim requests must be rate-limited and always send a descriptive user agent.
Debugging: When addresses are missing, check cache precision, Nominatim limits, and the app logs around HTTP 429 errors.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import asdict, dataclass
from typing import Any

import redis
import requests
from requests.adapters import HTTPAdapter
from sqlalchemy import select
from sqlalchemy.orm import Session
from urllib3.util.retry import Retry

from app.config import Settings
from app.db.models import GPSPosition, LocationEnriched, ReverseGeocodeCache

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class ReverseGeocodeResult:
    """Human-readable location fields returned by the geocoding provider."""

    street: str | None
    city: str | None
    postcode: str | None
    country: str | None
    place_name: str | None
    raw_payload: dict[str, Any] | None


class ReverseGeocoder:
    """Reverse-geocode positions with database and optional Redis caching."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._session = self._build_http_session()
        self._rate_limit_lock = threading.Lock()
        self._last_call_monotonic = 0.0
        self._redis_client = self._build_redis_client()

    def enrich_position(
        self, db_session: Session, position: GPSPosition
    ) -> LocationEnriched | None:
        """Attach human-readable address data to one stored GPS position."""

        if not self.settings.reverse_geocode_enabled:
            return None

        if position.enrichment is not None:
            return position.enrichment

        lat_tile, lon_tile = self._cache_key_parts(position.latitude, position.longitude)
        cached = self._get_cached_result(db_session, lat_tile, lon_tile)
        result = cached or self._fetch_remote_result(position.latitude, position.longitude)
        if result is None:
            return None

        if cached is None:
            self._store_cache_result(db_session, lat_tile, lon_tile, result)

        enrichment = LocationEnriched(
            position_id=position.id,
            street=result.street,
            city=result.city,
            postcode=result.postcode,
            country=result.country,
            place_name=result.place_name,
        )
        db_session.add(enrichment)
        db_session.flush()
        return enrichment

    def _build_http_session(self) -> requests.Session:
        retry = Retry(
            total=2,
            read=2,
            connect=2,
            backoff_factor=1.0,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset({"GET"}),
            raise_on_status=False,
        )

        adapter = HTTPAdapter(max_retries=retry)
        session = requests.Session()
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        session.headers.update({"User-Agent": self.settings.reverse_geocode_user_agent})
        return session

    def _build_redis_client(self) -> redis.Redis | None:
        if not self.settings.redis_url:
            return None

        try:
            client = redis.Redis.from_url(self.settings.redis_url, decode_responses=True)
            client.ping()
            logger.info("Connected to Redis reverse-geocode cache")
            return client
        except redis.RedisError as exc:
            logger.warning(
                "Redis cache unavailable; continuing with PostgreSQL cache only", exc_info=exc
            )
            return None

    def _cache_key_parts(self, latitude: float, longitude: float) -> tuple[float, float]:
        precision = self.settings.reverse_geocode_cache_precision
        return round(latitude, precision), round(longitude, precision)

    def _redis_cache_key(self, lat_tile: float, lon_tile: float) -> str:
        return f"reverse-geocode:{lat_tile}:{lon_tile}"

    def _get_cached_result(
        self,
        db_session: Session,
        lat_tile: float,
        lon_tile: float,
    ) -> ReverseGeocodeResult | None:
        """Look up cache hits in Redis first, then in PostgreSQL."""

        redis_result = self._read_redis_cache(lat_tile, lon_tile)
        if redis_result is not None:
            return redis_result

        statement = select(ReverseGeocodeCache).where(
            ReverseGeocodeCache.lat_tile == lat_tile,
            ReverseGeocodeCache.lon_tile == lon_tile,
        )
        cache_entry = db_session.execute(statement).scalar_one_or_none()
        if cache_entry is None:
            return None

        result = ReverseGeocodeResult(
            street=cache_entry.street,
            city=cache_entry.city,
            postcode=cache_entry.postcode,
            country=cache_entry.country,
            place_name=cache_entry.place_name,
            raw_payload=cache_entry.raw_payload,
        )
        self._write_redis_cache(lat_tile, lon_tile, result)
        return result

    def _store_cache_result(
        self,
        db_session: Session,
        lat_tile: float,
        lon_tile: float,
        result: ReverseGeocodeResult,
    ) -> None:
        """Persist a new cache hit so future polls avoid a public HTTP call."""

        statement = select(ReverseGeocodeCache).where(
            ReverseGeocodeCache.lat_tile == lat_tile,
            ReverseGeocodeCache.lon_tile == lon_tile,
        )
        cache_entry = db_session.execute(statement).scalar_one_or_none()

        if cache_entry is None:
            cache_entry = ReverseGeocodeCache(lat_tile=lat_tile, lon_tile=lon_tile)
            db_session.add(cache_entry)

        cache_entry.street = result.street
        cache_entry.city = result.city
        cache_entry.postcode = result.postcode
        cache_entry.country = result.country
        cache_entry.place_name = result.place_name
        cache_entry.raw_payload = result.raw_payload
        db_session.flush()
        self._write_redis_cache(lat_tile, lon_tile, result)

    def _read_redis_cache(self, lat_tile: float, lon_tile: float) -> ReverseGeocodeResult | None:
        if self._redis_client is None:
            return None

        try:
            payload = self._redis_client.get(self._redis_cache_key(lat_tile, lon_tile))
        except redis.RedisError as exc:
            logger.warning("Redis cache read failed", exc_info=exc)
            return None

        if not payload:
            return None

        parsed = json.loads(payload)
        return ReverseGeocodeResult(**parsed)

    def _write_redis_cache(
        self, lat_tile: float, lon_tile: float, result: ReverseGeocodeResult
    ) -> None:
        if self._redis_client is None:
            return

        try:
            self._redis_client.setex(
                self._redis_cache_key(lat_tile, lon_tile),
                60 * 60 * 24 * 7,
                json.dumps(asdict(result)),
            )
        except redis.RedisError as exc:
            logger.warning("Redis cache write failed", exc_info=exc)

    def _fetch_remote_result(
        self, latitude: float, longitude: float
    ) -> ReverseGeocodeResult | None:
        """Call the public Nominatim endpoint with rate limiting and clear error handling."""

        self._respect_rate_limit()
        logger.debug(
            "Calling Nominatim reverse geocode",
            extra={"latitude": latitude, "longitude": longitude},
        )
        try:
            response = self._session.get(
                self.settings.reverse_geocode_url,
                params={
                    "lat": latitude,
                    "lon": longitude,
                    "format": "jsonv2",
                    "zoom": 18,
                    "addressdetails": 1,
                },
                timeout=10,
            )
            if not response.ok:
                logger.warning(
                    "Reverse geocoding failed",
                    extra={"status_code": response.status_code, "body": response.text[:300]},
                )
                return None
            payload = response.json()
            return self._parse_response(payload)
        except requests.RequestException as exc:
            logger.warning("Reverse geocoding request failed", exc_info=exc)
            return None

    def _respect_rate_limit(self) -> None:
        """Stay friendly to the public API by spacing requests out."""

        with self._rate_limit_lock:
            min_interval = self.settings.reverse_geocode_min_interval_seconds
            elapsed = time.monotonic() - self._last_call_monotonic
            if elapsed < min_interval:
                time.sleep(min_interval - elapsed)
            self._last_call_monotonic = time.monotonic()

    def _parse_response(self, payload: dict[str, Any]) -> ReverseGeocodeResult:
        """Convert Nominatim's address fields into the application's storage schema."""

        address = payload.get("address", {})
        street = (
            address.get("road")
            or address.get("pedestrian")
            or address.get("footway")
            or address.get("residential")
        )
        city = (
            address.get("city")
            or address.get("town")
            or address.get("village")
            or address.get("municipality")
            or address.get("county")
        )

        return ReverseGeocodeResult(
            street=street,
            city=city,
            postcode=address.get("postcode"),
            country=address.get("country"),
            place_name=payload.get("name") or payload.get("display_name"),
            raw_payload=payload,
        )
