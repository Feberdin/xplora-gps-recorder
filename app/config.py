"""
Purpose: Central runtime configuration for API, polling, storage, and integrations.
Inputs: Environment variables from `.env`, Docker secrets, or process environment.
Outputs: A cached `Settings` object used across the whole application.
Invariants: Secrets are read from environment variables only and never hard-coded.
Debugging: Call `get_settings().model_dump(exclude={"xplora_password", "mqtt_password"})`
carefully during local debugging to confirm configuration without leaking secrets.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_env: str = Field(default="development", alias="APP_ENV")
    app_name: str = "xplora-gps-recorder"
    api_host: str = Field(default="0.0.0.0", alias="API_HOST")
    api_port: int = Field(default=8000, alias="API_PORT")
    poll_interval_seconds: int = Field(default=60, alias="POLL_INTERVAL_SECONDS", ge=10)
    default_query_limit: int = Field(default=500, alias="DEFAULT_QUERY_LIMIT", ge=1, le=5000)

    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    log_json: bool = Field(default=True, alias="LOG_JSON")
    log_include_sql: bool = Field(default=False, alias="LOG_INCLUDE_SQL")

    database_url: str | None = Field(
        default=None,
        validation_alias=AliasChoices("DATABASE_URL", "POSTGRES_URL"),
    )
    sqlite_path: str = Field(default="/data/xplora_gps_recorder.db", alias="SQLITE_PATH")
    redis_url: str | None = Field(default=None, alias="REDIS_URL")

    xplora_base_url: str = Field(default="https://api.myxplora.com/api", alias="XPLORA_BASE_URL")
    xplora_country_code: str | None = Field(default=None, alias="XPLORA_COUNTRY_CODE")
    xplora_user_lang: str | None = Field(default=None, alias="XPLORA_USER_LANG")
    xplora_time_zone: str | None = Field(default=None, alias="XPLORA_TIME_ZONE")
    xplora_trigger_locate: bool = Field(default=True, alias="XPLORA_TRIGGER_LOCATE")
    xplora_login_path: str = Field(default="/auth/login", alias="XPLORA_LOGIN_PATH")
    xplora_devices_path: str = Field(default="/v1/devices", alias="XPLORA_DEVICES_PATH")
    xplora_location_path: str | None = Field(default=None, alias="XPLORA_LOCATION_PATH")
    xplora_username: str = Field(alias="XPLORA_USERNAME")
    xplora_password: SecretStr = Field(alias="XPLORA_PASSWORD")
    xplora_verify_ssl: bool = Field(default=True, alias="XPLORA_VERIFY_SSL")
    xplora_timeout_seconds: int = Field(default=15, alias="XPLORA_TIMEOUT_SECONDS", ge=1)
    xplora_max_retries: int = Field(default=3, alias="XPLORA_MAX_RETRIES", ge=0, le=10)

    reverse_geocode_enabled: bool = Field(default=True, alias="REVERSE_GEOCODE_ENABLED")
    reverse_geocode_url: str = Field(
        default="https://nominatim.openstreetmap.org/reverse",
        alias="REVERSE_GEOCODE_URL",
    )
    reverse_geocode_user_agent: str = Field(
        default="xplora-gps-recorder/1.0",
        alias="REVERSE_GEOCODE_USER_AGENT",
    )
    reverse_geocode_cache_precision: int = Field(
        default=4,
        alias="REVERSE_GEOCODE_CACHE_PRECISION",
        ge=2,
        le=6,
    )
    reverse_geocode_min_interval_seconds: float = Field(
        default=1.0,
        alias="REVERSE_GEOCODE_MIN_INTERVAL_SECONDS",
        ge=0.0,
    )

    stationary_distance_meters: float = Field(
        default=20.0,
        alias="STATIONARY_DISTANCE_METERS",
        ge=0.0,
    )
    stationary_window_seconds: int = Field(
        default=300,
        alias="STATIONARY_WINDOW_SECONDS",
        ge=60,
    )
    heatmap_tile_precision: int = Field(default=3, alias="HEATMAP_TILE_PRECISION", ge=1, le=6)

    mqtt_enabled: bool = Field(default=False, alias="MQTT_ENABLED")
    mqtt_host: str | None = Field(default=None, alias="MQTT_HOST")
    mqtt_port: int = Field(default=1883, alias="MQTT_PORT", ge=1, le=65535)
    mqtt_user: str | None = Field(default=None, alias="MQTT_USER")
    mqtt_password: SecretStr | None = Field(default=None, alias="MQTT_PASSWORD")
    mqtt_topic_prefix: str = Field(default="kids/watch", alias="MQTT_TOPIC_PREFIX")
    mqtt_tls_enabled: bool = Field(default=False, alias="MQTT_TLS_ENABLED")

    @model_validator(mode="after")
    def resolve_database_url(self) -> "Settings":
        """Allow SQLite as the zero-setup default while keeping external databases optional."""

        if self.database_url:
            return self

        sqlite_path = self.sqlite_path.strip()
        if not sqlite_path:
            raise ValueError("Either DATABASE_URL/POSTGRES_URL or SQLITE_PATH must be configured.")

        normalized_path = Path(sqlite_path)
        self.database_url = f"sqlite:///{normalized_path}"
        return self

    @model_validator(mode="after")
    def resolve_xplora_defaults(self) -> "Settings":
        """Fill in safe defaults for the GraphQL client and validate login requirements."""

        self.xplora_base_url = self.xplora_base_url.strip() or "https://api.myxplora.com/api"

        if not self.xplora_user_lang:
            lang = os.getenv("LANG", "").lower()
            self.xplora_user_lang = "de-DE" if lang.startswith("de") else "en-GB"

        if not self.xplora_time_zone:
            self.xplora_time_zone = os.getenv("TZ", "UTC") or "UTC"

        username = self.xplora_username.strip()
        if "@" not in username and not (self.xplora_country_code and self.xplora_country_code.strip()):
            raise ValueError(
                "XPLORA_COUNTRY_CODE is required when XPLORA_USERNAME is a phone number instead of an e-mail address."
            )

        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached settings object so every module shares the same configuration."""

    return Settings()
