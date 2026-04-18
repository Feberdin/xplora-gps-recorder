"""
Purpose: Verify that database configuration falls back to SQLite while still supporting PostgreSQL overrides.
Inputs: Synthetic settings values provided directly to the Pydantic settings model.
Outputs: Assertions covering SQLite defaults and explicit external database URLs.
Invariants: The add-on must be installable without an external database.
Debugging: If these tests fail, inspect the settings alias and fallback logic in `app/config.py`.
"""

from __future__ import annotations

import pytest

from app.config import Settings


def test_settings_default_to_sqlite_when_no_database_url_is_provided(monkeypatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("POSTGRES_URL", raising=False)
    monkeypatch.delenv("XPLORA_BASE_URL", raising=False)
    monkeypatch.delenv("XPLORA_USER_LANG", raising=False)
    monkeypatch.delenv("XPLORA_TIME_ZONE", raising=False)
    monkeypatch.setenv("LANG", "en_US.UTF-8")
    monkeypatch.setenv("TZ", "UTC")

    settings = Settings(
        XPLORA_USERNAME="child@example.test",
        XPLORA_PASSWORD="secret",
        SQLITE_PATH="/data/xplora_gps_recorder.db",
    )

    assert settings.database_url == "sqlite:////data/xplora_gps_recorder.db"
    assert settings.xplora_base_url == "https://api.myxplora.com/api"
    assert settings.xplora_user_lang == "en-GB"
    assert settings.xplora_time_zone == "UTC"


def test_settings_accept_postgres_url_for_advanced_setups() -> None:
    settings = Settings(
        POSTGRES_URL="postgresql+psycopg://xplora:secret@db:5432/xplora_gps",
        XPLORA_USERNAME="child@example.test",
        XPLORA_PASSWORD="secret",
    )

    assert settings.database_url == "postgresql+psycopg://xplora:secret@db:5432/xplora_gps"


def test_settings_require_country_code_for_phone_logins() -> None:
    with pytest.raises(ValueError, match="XPLORA_COUNTRY_CODE"):
        Settings(
            XPLORA_USERNAME="15123456",
            XPLORA_PASSWORD="secret",
        )
