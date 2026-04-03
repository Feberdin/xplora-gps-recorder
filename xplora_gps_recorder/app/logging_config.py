"""
Purpose: Configure structured logging for the API, scheduler, and background services.
Inputs: Log level and output format flags from `app.config.Settings`.
Outputs: Root logging handlers that write reproducible diagnostics to stdout.
Invariants: Sensitive values such as passwords and access tokens must never be logged.
Debugging: Set `LOG_LEVEL=DEBUG` and `LOG_JSON=false` locally if human-readable logs are easier to inspect.
"""

from __future__ import annotations

import logging.config

from pythonjsonlogger.jsonlogger import JsonFormatter


class RecorderJsonFormatter(JsonFormatter):
    """Small wrapper that keeps timestamp and log level fields consistent."""

    def add_fields(self, log_record, record, message_dict) -> None:  # type: ignore[override]
        super().add_fields(log_record, record, message_dict)
        log_record.setdefault("level", record.levelname)
        log_record.setdefault("logger", record.name)


def configure_logging(log_level: str, json_logs: bool, include_sql: bool = False) -> None:
    """Configure process-wide logging once during startup."""

    formatter_name = "json" if json_logs else "plain"

    logging_config = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "plain": {
                "format": "%(asctime)s %(levelname)s [%(name)s] %(message)s",
            },
            "json": {
                "()": RecorderJsonFormatter,
                "fmt": "%(asctime)s %(levelname)s %(name)s %(message)s",
            },
        },
        "handlers": {
            "default": {
                "class": "logging.StreamHandler",
                "formatter": formatter_name,
            },
        },
        "root": {
            "handlers": ["default"],
            "level": log_level.upper(),
        },
        "loggers": {
            "apscheduler": {"level": "INFO"},
            "sqlalchemy.engine": {"level": "INFO" if include_sql else "WARNING"},
            "uvicorn.access": {"level": "INFO"},
        },
    }

    logging.config.dictConfig(logging_config)
