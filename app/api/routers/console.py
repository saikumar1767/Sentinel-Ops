from __future__ import annotations

from fastapi import APIRouter, Depends, Path as FastAPIPath, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse

from app.dependencies import get_console_service
from app.http_errors import problem_response, safe_detail
from app.schemas import (
    ConsoleOverviewResponse,
    ConsoleTimelineResponse,
    IncidentLibraryResponse,
    IncidentProfileResponse,
    ProblemDetailResponse,
)
from app.services.console_service import ConsoleService
from app.settings import PROJECT_ROOT

router = APIRouter(tags=["console"])
_CONSOLE_HTML_PATH = PROJECT_ROOT / "app" / "static" / "console.html"


@router.get("/", include_in_schema=False)
def root_redirect() -> RedirectResponse:
    return RedirectResponse(url="/console", status_code=307)


@router.get("/console", include_in_schema=False)
def console_dashboard() -> FileResponse:
    return FileResponse(_CONSOLE_HTML_PATH)


@router.get(
    "/console/overview",
    response_model=ConsoleOverviewResponse,
    summary="Read the operator console overview",
    description=(
        "Returns the incident library count, deterministic evaluation pass rates, and startup command used for the "
        "operator console."
    ),
)
def console_overview(
    service: ConsoleService = Depends(get_console_service),
) -> ConsoleOverviewResponse:
    return service.overview()


@router.get(
    "/console/incidents",
    response_model=IncidentLibraryResponse,
    summary="List incident library entries",
    description=(
        "Returns the incident library, including operator-ready request payloads and expected outcomes for "
        "recorded incident walkthroughs."
    ),
)
def list_console_incidents(
    service: ConsoleService = Depends(get_console_service),
) -> IncidentLibraryResponse:
    return service.list_incidents()


@router.get(
    "/console/incidents/{incident_id}",
    response_model=IncidentProfileResponse,
    responses={404: {"model": ProblemDetailResponse}},
    summary="Read one incident library entry",
)
def get_console_incident(
    request_context: Request,
    incident_id: str = FastAPIPath(..., min_length=1, max_length=120),
    service: ConsoleService = Depends(get_console_service),
) -> IncidentProfileResponse | JSONResponse:
    try:
        return service.get_incident(incident_id)
    except KeyError as exc:
        return problem_response(
            request=request_context,
            status_code=404,
            code="incident_profile_not_found",
            title="Incident profile not found",
            detail=safe_detail(exc, default="Incident profile was not found.", expose_types=(KeyError,)),
        )


@router.get(
    "/console/timeline",
    response_model=ConsoleTimelineResponse,
    summary="Read the saved incident timeline",
    description=(
        "Returns the saved incident timeline, combining recorded incidents with reference incidents for operator "
        "context."
    ),
)
def get_console_timeline(
    service: ConsoleService = Depends(get_console_service),
) -> ConsoleTimelineResponse:
    return service.timeline()
