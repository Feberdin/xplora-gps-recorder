# Changelog

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
