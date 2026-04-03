#!/usr/bin/env sh
# Purpose: Start the recorder in Docker or Home Assistant add-on mode with one shared entrypoint.
# Inputs: Environment variables and, in add-on mode, `/data/options.json` written by Supervisor.
# Outputs: Validated environment variables, database initialization, and the running FastAPI service.
# Invariants: Required Xplora and PostgreSQL settings must exist before the application boots.
# Debugging: Set `XPLORA_DRY_RUN=1` to print the resolved config without starting the app process.

set -eu

OPTIONS_PATH="${XPLORA_OPTIONS_PATH:-/data/options.json}"
TEMP_ENV_FILE="/tmp/xplora-addon-env.sh"

log() {
  printf '%s\n' "$*"
}

fail() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

load_addon_options() {
  if [ ! -f "$OPTIONS_PATH" ]; then
    return 0
  fi

  log "Loading Home Assistant add-on options from $OPTIONS_PATH"
  python3 - "$OPTIONS_PATH" >"$TEMP_ENV_FILE" <<'PY'
import json
import shlex
import sys
from urllib.parse import quote


path = sys.argv[1]
with open(path, encoding="utf-8") as handle:
    options = json.load(handle)


def emit(key: str, value) -> None:
    if value is None:
        return
    if isinstance(value, bool):
        value = "true" if value else "false"
    print(f"export {key}={shlex.quote(str(value))}")


mapping = {
    "log_level": "LOG_LEVEL",
    "log_json": "LOG_JSON",
    "poll_interval_seconds": "POLL_INTERVAL_SECONDS",
    "xplora_base_url": "XPLORA_BASE_URL",
    "xplora_login_path": "XPLORA_LOGIN_PATH",
    "xplora_devices_path": "XPLORA_DEVICES_PATH",
    "xplora_location_path": "XPLORA_LOCATION_PATH",
    "xplora_username": "XPLORA_USERNAME",
    "xplora_password": "XPLORA_PASSWORD",
    "xplora_verify_ssl": "XPLORA_VERIFY_SSL",
    "reverse_geocode_enabled": "REVERSE_GEOCODE_ENABLED",
    "mqtt_enabled": "MQTT_ENABLED",
    "mqtt_host": "MQTT_HOST",
    "mqtt_port": "MQTT_PORT",
    "mqtt_user": "MQTT_USER",
    "mqtt_password": "MQTT_PASSWORD",
    "mqtt_topic_prefix": "MQTT_TOPIC_PREFIX",
}

for source_key, target_key in mapping.items():
    emit(target_key, options.get(source_key))

postgres_url = options.get("postgres_url")
if postgres_url:
    emit("POSTGRES_URL", postgres_url)
else:
    host = options.get("postgres_host")
    port = options.get("postgres_port", 5432)
    database = options.get("postgres_db")
    user = options.get("postgres_user")
    password = options.get("postgres_password")
    if host and database and user and password:
        database_url = (
            f"postgresql+psycopg://{quote(str(user), safe='')}:"
            f"{quote(str(password), safe='')}@{host}:{port}/{database}"
        )
        emit("POSTGRES_URL", database_url)
PY

  # Why this section exists:
  # Supervisor stores add-on options in JSON, but the Python app expects environment variables.
  # We convert the config once so both Docker and add-on mode use the exact same application code.
  # shellcheck disable=SC1090
  . "$TEMP_ENV_FILE"
}

require_env() {
  variable_name="$1"
  explanation="$2"
  value="$(printenv "$variable_name" 2>/dev/null || true)"
  if [ -z "$value" ]; then
    fail "$variable_name is required. $explanation"
  fi
}

validate_environment() {
  require_env "POSTGRES_URL" \
    "Provide a full PostgreSQL URL or fill postgres_host/postgres_db/postgres_user/postgres_password."
  require_env "XPLORA_BASE_URL" "Set the Xplora cloud base URL."
  require_env "XPLORA_USERNAME" "Set the Xplora account username."
  require_env "XPLORA_PASSWORD" "Set the Xplora account password."

  mqtt_enabled="$(printenv MQTT_ENABLED 2>/dev/null || printf 'false')"
  if [ "$mqtt_enabled" = "true" ] && [ -z "$(printenv MQTT_HOST 2>/dev/null || true)" ]; then
    fail "MQTT_ENABLED is true but MQTT_HOST is empty."
  fi
}

print_dry_run_summary() {
  cat <<EOF
Resolved startup configuration:
  API_HOST=${API_HOST:-0.0.0.0}
  API_PORT=${API_PORT:-8000}
  POLL_INTERVAL_SECONDS=${POLL_INTERVAL_SECONDS:-60}
  LOG_LEVEL=${LOG_LEVEL:-INFO}
  LOG_JSON=${LOG_JSON:-true}
  POSTGRES_URL=$( [ -n "${POSTGRES_URL:-}" ] && printf '<set>' || printf '<missing>' )
  XPLORA_BASE_URL=$( [ -n "${XPLORA_BASE_URL:-}" ] && printf '%s' "$XPLORA_BASE_URL" || printf '<missing>' )
  XPLORA_USERNAME=$( [ -n "${XPLORA_USERNAME:-}" ] && printf '<set>' || printf '<missing>' )
  XPLORA_PASSWORD=$( [ -n "${XPLORA_PASSWORD:-}" ] && printf '<set>' || printf '<missing>' )
  MQTT_ENABLED=${MQTT_ENABLED:-false}
  MQTT_HOST=$( [ -n "${MQTT_HOST:-}" ] && printf '%s' "$MQTT_HOST" || printf '<unset>' )
EOF
}

main() {
  load_addon_options
  export API_HOST="${API_HOST:-0.0.0.0}"
  export API_PORT="${API_PORT:-8000}"
  validate_environment

  if [ "${XPLORA_DRY_RUN:-0}" = "1" ]; then
    print_dry_run_summary
    exit 0
  fi

  python scripts/init_db.py
  exec uvicorn app.main:app --host "$API_HOST" --port "$API_PORT"
}

main "$@"

