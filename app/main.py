"""
Purpose: Assemble the FastAPI application, dependency graph, and scheduler lifecycle.
Inputs: Global settings plus the service classes defined in the rest of the application.
Outputs: A production-ready ASGI app that serves the REST API and runs background polling.
Invariants: Logging is configured exactly once and the scheduler shuts down cleanly on process exit.
Debugging: Inspect `/health` and the startup logs first when the service boots but no polling occurs.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request

from app.api.routes import router
from app.api.schemas import HealthResponse
from app.config import get_settings
from app.db.session import SessionLocal
from app.heatmap import HeatmapService
from app.logging_config import configure_logging
from app.movement_detection import MovementDetector
from app.mqtt_publisher import MqttPublisher
from app.reverse_geocode import ReverseGeocoder
from app.scheduler import PollingScheduler
from app.services.location_service import LocationIngestionService
from app.xplora_client import XploraClient

settings = get_settings()
configure_logging(settings.log_level, settings.log_json, settings.log_include_sql)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Create shared service instances and background jobs for the process lifetime."""

    xplora_client = XploraClient(settings)
    reverse_geocoder = ReverseGeocoder(settings)
    movement_detector = MovementDetector(settings)
    heatmap_service = HeatmapService(settings.heatmap_tile_precision)
    mqtt_publisher = MqttPublisher(settings)
    ingestion_service = LocationIngestionService(
        session_factory=SessionLocal,
        xplora_client=xplora_client,
        reverse_geocoder=reverse_geocoder,
        movement_detector=movement_detector,
        heatmap_service=heatmap_service,
        mqtt_publisher=mqtt_publisher,
    )
    scheduler = PollingScheduler(ingestion_service, settings.poll_interval_seconds)

    app.state.scheduler = scheduler
    app.state.settings = settings
    app.state.ingestion_service = ingestion_service
    mqtt_publisher.connect()
    scheduler.start()

    yield

    scheduler.shutdown()
    mqtt_publisher.close()


app = FastAPI(
    title="xplora-gps-recorder",
    version="1.2.1",
    summary="Periodic GPS recorder for Xplora smartwatches",
    lifespan=lifespan,
)
app.include_router(router)


@app.get("/", tags=["system"])
def root() -> dict[str, str]:
    return {
        "service": "xplora-gps-recorder",
        "docs": "/docs",
        "health": "/health",
    }


@app.get("/health", response_model=HealthResponse, tags=["system"])
def health(request: Request) -> HealthResponse:
    scheduler = request.app.state.scheduler
    settings = request.app.state.settings
    return HealthResponse(
        status="ok",
        app_name=settings.app_name,
        app_env=settings.app_env,
        scheduler_running=bool(scheduler.scheduler.running),
    )
