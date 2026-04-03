"""
Purpose: Shared test fixtures and helpers for deterministic unit tests.
Inputs: Optional per-test overrides for application settings.
Outputs: Valid `Settings` objects without requiring a real `.env` file.
Invariants: Tests must stay isolated from the developer's local environment.
Debugging: If a test unexpectedly reads production-like config, inspect this helper first.
"""

from __future__ import annotations

import os

from app.config import Settings

# Why this section exists:
# SQLAlchemy session setup loads settings at import time, so tests need safe defaults
# before any application module imports happen.
os.environ.setdefault("DATABASE_URL", "sqlite:///./tests/test_bootstrap.sqlite3")
os.environ.setdefault("XPLORA_BASE_URL", "https://api.example.test")
os.environ.setdefault("XPLORA_USERNAME", "child@example.test")
os.environ.setdefault("XPLORA_PASSWORD", "secret")


def make_settings(**overrides) -> Settings:
    """Build a minimal valid settings object for unit tests."""

    values = {
        "DATABASE_URL": "sqlite:///./tests/test_settings.sqlite3",
        "XPLORA_BASE_URL": "https://api.example.test",
        "XPLORA_USERNAME": "child@example.test",
        "XPLORA_PASSWORD": "secret",
    }
    values.update(overrides)
    return Settings(**values)
