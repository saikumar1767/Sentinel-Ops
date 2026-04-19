from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.auth import AuthenticatedUser
from app.dependencies import (
    get_current_user,
    get_runtime_health_service,
    get_runtime_metrics,
    get_settings,
    require_admin_user,
)
from app.runtime_metrics import RuntimeMetrics
from app.schemas import CurrentUserResponse, LivenessResponse, MetricsResponse, ReadinessResponse
from app.services.runtime_health_service import RuntimeHealthService
from app.settings import Settings

router = APIRouter(tags=["system"])


@router.get(
    "/health",
    response_model=LivenessResponse,
    summary="Minimal liveness check",
    description=(
        "Returns a minimal liveness response for the API process only. `/health` intentionally does not check "
        "Ollama, Chroma, or retrieval readiness, so it stays stable for container and process supervision."
    ),
)
def health(
    service: RuntimeHealthService = Depends(get_runtime_health_service),
) -> LivenessResponse:
    return service.health_report()


@router.get(
    "/ready",
    response_model=ReadinessResponse,
    responses={503: {"model": ReadinessResponse}},
    summary="Traffic readiness for core incident workflows",
    description=(
        "Returns readiness for core SentinelOps traffic. This route stays green when `/analyze` and `/investigate` "
        "can still serve requests, even if knowledge ingest or search are degraded."
    ),
)
def ready(
    service: RuntimeHealthService = Depends(get_runtime_health_service),
) -> ReadinessResponse | JSONResponse:
    report = service.readiness_report(scope="traffic")
    if not service.is_ready(report):
        return JSONResponse(status_code=503, content=report.model_dump(mode="json"))  # type: ignore[return-value]
    return report


@router.get(
    "/ready/strict",
    response_model=ReadinessResponse,
    responses={503: {"model": ReadinessResponse}},
    summary="Strict readiness for all configured capabilities",
    description=(
        "Returns strict readiness for all configured SentinelOps capabilities. This route is useful for release "
        "rehearsals and packaging checks because it requires knowledge ingest and search to be healthy too."
    ),
)
def ready_strict(
    service: RuntimeHealthService = Depends(get_runtime_health_service),
) -> ReadinessResponse | JSONResponse:
    report = service.readiness_report(scope="strict")
    if not service.is_ready(report, strict=True):
        return JSONResponse(status_code=503, content=report.model_dump(mode="json"))  # type: ignore[return-value]
    return report


@router.get(
    "/me",
    response_model=CurrentUserResponse,
    summary="Read the authenticated SentinelOps user",
)
def me(
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> CurrentUserResponse:
    return CurrentUserResponse(**current_user.model_dump())


@router.get(
    "/metrics",
    response_model=MetricsResponse,
    summary="Runtime metrics for requests, models, and caches",
)
def metrics(
    current_user: AuthenticatedUser = Depends(require_admin_user),
    runtime_metrics: RuntimeMetrics = Depends(get_runtime_metrics),
    settings: Settings = Depends(get_settings),
) -> MetricsResponse:
    del current_user
    return runtime_metrics.snapshot(settings)
