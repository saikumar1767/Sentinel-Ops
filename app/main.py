from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api.routers import (
    analysis_router,
    console_router,
    evaluation_router,
    knowledge_router,
    system_router,
    workflow_router,
)
from app.dependencies import get_settings
from app.http_errors import install_exception_handlers
from app.http_runtime import configure_logging, install_http_middleware, install_openapi_contracts
from app.settings import PROJECT_ROOT
from app.startup import run_startup_validation
from app.telemetry import configure_telemetry

APP_SETTINGS = get_settings()
STATIC_ASSETS_DIR = PROJECT_ROOT / "app" / "static"
OPENAPI_TAGS = [
    {
        "name": "system",
        "description": "Operational readiness, liveness, and metrics endpoints used to supervise the local service.",
    },
    {
        "name": "analysis",
        "description": "One-shot incident analysis and investigation routes for fast operator workflows.",
    },
    {
        "name": "workflow",
        "description": "Checkpointed incident workflow routes for approval-gated investigations and durable thread inspection.",
    },
    {
        "name": "knowledge",
        "description": "Knowledge-base ingestion and semantic search routes for the local retrieval layer.",
    },
    {
        "name": "evaluation",
        "description": "Deterministic local evaluation summary used for regression tracking and operational proof.",
    },
    {
        "name": "console",
        "description": "Operator console routes for the incident library, timeline, and console overview.",
    },
]


@asynccontextmanager
async def lifespan(app_instance: FastAPI):
    settings = get_settings()
    run_startup_validation(app_instance, settings)
    configure_telemetry(app_instance, settings)
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title=APP_SETTINGS.app_name,
        version=APP_SETTINGS.app_version,
        description=(
            "SentinelOps is a local-first incident copilot for log analysis, safe investigation workflows, "
            "retrieval-backed evidence gathering, and operator-facing incident workflows."
        ),
        openapi_tags=OPENAPI_TAGS,
        lifespan=lifespan,
    )

    configure_logging()
    install_exception_handlers(app)
    install_http_middleware(app)
    install_openapi_contracts(app)
    app.mount("/static", StaticFiles(directory=STATIC_ASSETS_DIR), name="static")

    app.include_router(console_router)
    app.include_router(system_router)
    app.include_router(evaluation_router)
    app.include_router(analysis_router)
    app.include_router(workflow_router)
    app.include_router(knowledge_router)
    return app


app = create_app()
