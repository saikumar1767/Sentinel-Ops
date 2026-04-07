from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routers import (
    analysis_router,
    evaluation_router,
    knowledge_router,
    system_router,
    workflow_router,
)
from app.dependencies import get_settings
from app.http_errors import install_exception_handlers
from app.http_runtime import configure_logging, install_http_middleware, install_openapi_contracts
from app.startup import run_startup_validation
from app.telemetry import configure_telemetry

APP_SETTINGS = get_settings()


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
            "Local incident analysis API with operational routes for `/analyze`, `/investigate`, "
            "checkpointed `/workflow/*` investigations, and retrieval-backed knowledge search."
        ),
        lifespan=lifespan,
    )

    configure_logging()
    install_exception_handlers(app)
    install_http_middleware(app)
    install_openapi_contracts(app)

    app.include_router(system_router)
    app.include_router(evaluation_router)
    app.include_router(analysis_router)
    app.include_router(workflow_router)
    app.include_router(knowledge_router)
    return app


app = create_app()
