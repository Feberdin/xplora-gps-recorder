# Xplora GPS Recorder Add-on

This Home Assistant add-on polls Xplora smartwatches, stores GPS history in PostgreSQL, enriches locations, detects movement, and exposes REST and MQTT data.

## Install

1. Add this GitHub repository as a custom add-on repository:
   `https://github.com/Feberdin/xplora-gps-recorder`
2. Install **Xplora GPS Recorder**
3. Fill the add-on configuration
4. Start the add-on

## Required configuration

- `xplora_base_url`
- `xplora_username`
- `xplora_password`
- either `postgres_url` or `postgres_host` + `postgres_db` + `postgres_user` + `postgres_password`

## Exposed API

- `/health`
- `/devices`
- `/devices/{device_id}/positions`
- `/devices/{device_id}/movements`
- `/devices/{device_id}/heatmap`

