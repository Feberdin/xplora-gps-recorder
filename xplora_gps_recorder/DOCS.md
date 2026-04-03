# Home Assistant Add-on Docs

## Why this is an Add-on

`xplora-gps-recorder` is packaged as a **Home Assistant add-on**, not as a native custom integration.

That is the better fit because this project is a long-running backend service with:

- its own polling scheduler
- PostgreSQL persistence
- reverse-geocoding cache
- analytics endpoints
- optional MQTT publishing

Those responsibilities map much better to an add-on than to Python code running inside Home Assistant Core.

## Installation

This repository is set up to work as a **custom add-on repository**.

### Install from GitHub

1. Open `Settings -> Add-ons -> Add-on Store`.
2. Open the three-dot menu and choose `Repositories`.
3. Add:

   ```text
   https://github.com/Feberdin/xplora-gps-recorder
   ```

4. Install **Xplora GPS Recorder**.
5. Fill the add-on configuration and start it.

### Install as local repository

1. Open your Home Assistant `/addons` directory.
2. Copy this whole repository into a subfolder such as:

   ```text
   /addons/xplora-gps-recorder
   ```

3. Restart Home Assistant or reload the add-on store.
4. Install **Xplora GPS Recorder** from the local add-on store.

## PostgreSQL requirement

The add-on still uses PostgreSQL, because long-term history and analytics are central features.

You have two supported options:

- use an external PostgreSQL server
- use a separate PostgreSQL add-on/container and enter its connection details manually

You can either:

- provide `postgres_url` directly
- or fill `postgres_host`, `postgres_port`, `postgres_db`, `postgres_user`, and `postgres_password`

## Add-on configuration

### Required

- `xplora_base_url`
- `xplora_username`
- `xplora_password`
- either `postgres_url` or full PostgreSQL host credentials

### Optional

- `xplora_location_path`
- `mqtt_enabled`
- `mqtt_host`
- `mqtt_user`
- `mqtt_password`
- `mqtt_topic_prefix`

## Accessing the service

The add-on exposes:

- ingress inside Home Assistant
- port `8000` for direct API access

Useful endpoints:

- `/health`
- `/devices`
- `/devices/{device_id}/positions`
- `/devices/{device_id}/movements`
- `/devices/{device_id}/heatmap`

## Debugging

### The add-on does not start

- Check the add-on logs in Supervisor.
- Confirm that PostgreSQL values are complete.
- Confirm that `xplora_base_url`, `xplora_username`, and `xplora_password` are filled.

### GPS data is missing

- Switch `log_level` to `DEBUG`.
- Verify the Xplora endpoint paths.
- Inspect normalization rules in [`app/xplora_client.py`](app/xplora_client.py).

### Reverse geocoding is missing

- Check outbound internet access to Nominatim.
- Inspect rate-limit warnings in the add-on logs.

### MQTT entities do not update

- Enable MQTT.
- Confirm broker hostname and credentials.
- Subscribe manually to `kids/watch/#` to verify published payloads.
