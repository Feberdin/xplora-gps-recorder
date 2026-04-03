# Changelog

## 1.2.1 - 2026-04-03

- Fixed Home Assistant add-on startup when bootstrapping the database with `python scripts/init_db.py`
- Added a defensive import-path fallback so the `app` package is found reliably inside the container
- Exported `PYTHONPATH=/app` during startup to keep direct script execution and Uvicorn imports consistent

## 1.2.0 - 2026-04-03

- Added SQLite as the default embedded database for the Home Assistant add-on
- Kept PostgreSQL as an optional advanced database mode
- Simplified the add-on configuration so no external database is required for first-time installs

## 1.1.0 - 2026-04-03

- Packaged the backend as a Home Assistant local add-on
- Added Supervisor option schema, add-on startup wrapper, and add-on-specific docs
- Kept standalone Docker Compose deployment support

## 1.0.0 - 2026-04-03

- Initial open source release of `xplora-gps-recorder`
- FastAPI REST API with device, position, movement, and heatmap endpoints
- PostgreSQL storage with Alembic migrations
- APScheduler-based polling pipeline with reverse geocoding and movement detection
- Optional MQTT publishing for Home Assistant
- Docker Compose deployment and unit tests
