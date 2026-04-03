# Xplora GPS Recorder Add-on

This Home Assistant add-on polls Xplora smartwatches, stores GPS history in SQLite by default or PostgreSQL optionally, enriches locations, detects movement, and exposes REST and MQTT data.

## Install

1. Add this GitHub repository as a custom add-on repository:
   `https://github.com/Feberdin/xplora-gps-recorder`
2. Install **Xplora GPS Recorder**
3. Fill the add-on configuration
4. Start the add-on

## Required configuration

- `sqlite_path` can stay at the default value
- `xplora_base_url`
- `xplora_username`
- `xplora_password`

## Optional advanced database configuration

- `database_url`
- `postgres_host`
- `postgres_port`
- `postgres_db`
- `postgres_user`
- `postgres_password`

## Exposed API

- `/health`
- `/devices`
- `/devices/{device_id}/positions`
- `/devices/{device_id}/movements`
- `/devices/{device_id}/heatmap`
