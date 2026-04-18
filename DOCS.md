# Home Assistant Add-on Docs

## Why this is an Add-on

`xplora-gps-recorder` is packaged as a **Home Assistant add-on**, not as a native custom integration.

That is the better fit because this project is a long-running backend service with:

- its own polling scheduler
- persistent storage
- reverse-geocoding cache
- analytics endpoints
- optional MQTT publishing

Those responsibilities map much better to an add-on than to Python code running inside Home Assistant Core.

## Installation

This repository is set up to work as a **local custom add-on**.

### Install with SSH or Samba

1. Open your Home Assistant `/addons` directory.
2. Copy this whole repository into:

   ```text
   /addons/xplora_gps_recorder
   ```

3. Restart Home Assistant or reload the add-on store.
4. Open the add-on store and install **Xplora GPS Recorder**.

## Database requirement

The add-on now uses **SQLite by default**, stored locally under:

```text
/data/xplora_gps_recorder.db
```

That means you do **not** need an external database for normal installs.

You have two supported options:

- use the default embedded SQLite database
- switch to PostgreSQL later for a more advanced setup

You can either:

- keep `sqlite_path` as-is
- provide `database_url` directly
- or fill `postgres_host`, `postgres_port`, `postgres_db`, `postgres_user`, and `postgres_password`

## Add-on configuration

### Required

- `sqlite_path` can stay at the default value
- `xplora_base_url`
- `xplora_username`
- `xplora_password`

### Optional

- `database_url`
- `postgres_host`
- `postgres_port`
- `postgres_db`
- `postgres_user`
- `postgres_password`
- `xplora_country_code`
- `xplora_user_lang`
- `xplora_time_zone`
- `xplora_trigger_locate`
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
- Confirm that `sqlite_path` is writable or the PostgreSQL values are complete.
- Confirm that `xplora_username` and `xplora_password` are filled.
- If you use a phone number instead of an e-mail address, also set `xplora_country_code`.

### GPS data is missing

- Switch `log_level` to `DEBUG`.
- Keep `xplora_base_url` on the default GraphQL endpoint unless you have verified a different host.
- Check whether the Xplora account returns linked children after login.
- Inspect normalization rules in [`app/xplora_client.py`](app/xplora_client.py).

### Reverse geocoding is missing

- Check outbound internet access to Nominatim.
- Inspect rate-limit warnings in the add-on logs.

### MQTT entities do not update

- Enable MQTT.
- Confirm broker hostname and credentials.
- Subscribe manually to `kids/watch/#` to verify published payloads.
