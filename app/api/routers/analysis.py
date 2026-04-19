from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from ollama import RequestError, ResponseError
from pydantic import ValidationError

from app.auth import AuthenticatedUser
from app.dependencies import (
    get_analyze_service,
    get_investigation_service,
    require_analyst_user,
)
from app.http_errors import raise_ollama_http_exception
from app.schemas import (
    AnalyzeRequest,
    AnalyzeResponse,
    InvestigateRequest,
    InvestigateResponse,
    ProblemDetailResponse,
)
from app.services.analyze_service import AnalyzeService
from app.services.investigation_service import InvestigationService

logger = logging.getLogger("sentinelops.api.analysis")
router = APIRouter(tags=["analysis"])


@router.post(
    "/analyze",
    response_model=AnalyzeResponse,
    responses={
        502: {"model": ProblemDetailResponse},
        503: {"model": ProblemDetailResponse},
    },
    summary="Analyze pasted log text",
    description=(
        "Classifies pasted log text into a structured incident summary. When the local retrieval stack is ready, "
        "SentinelOps also retrieves supporting knowledge-base evidence and returns citations."
    ),
)
def analyze(
    request: AnalyzeRequest,
    current_user: AuthenticatedUser = Depends(require_analyst_user),
    service: AnalyzeService = Depends(get_analyze_service),
) -> AnalyzeResponse:
    del current_user
    try:
        return service.analyze(request)
    except ValidationError as exc:
        raise HTTPException(status_code=502, detail="Model returned invalid analyze JSON.") from exc
    except (RequestError, ResponseError) as exc:
        raise_ollama_http_exception(exc)
    except RuntimeError as exc:
        logger.warning("analyze dependency failure: %s", exc)
        raise HTTPException(status_code=503, detail="Analysis dependencies are unavailable.") from exc
    except Exception as exc:
        logger.exception("analyze execution failed", exc_info=exc)
        raise HTTPException(status_code=502, detail="Incident analysis failed unexpectedly.") from exc


@router.post(
    "/investigate",
    response_model=InvestigateResponse,
    responses={
        502: {"model": ProblemDetailResponse},
        503: {"model": ProblemDetailResponse},
    },
    summary="Investigate an incident with safe local tools and retrieval",
    description=(
        "Runs the controlled investigation workflow. SentinelOps reads candidate logs, compares runs when useful, "
        "loads safe local guidance, retrieves supporting knowledge-base evidence, and returns a structured report."
    ),
)
def investigate(
    request: InvestigateRequest,
    current_user: AuthenticatedUser = Depends(require_analyst_user),
    service: InvestigationService = Depends(get_investigation_service),
) -> InvestigateResponse:
    del current_user
    try:
        return service.investigate(request)
    except ValidationError as exc:
        raise HTTPException(status_code=502, detail="Model returned invalid investigation JSON.") from exc
    except (RequestError, ResponseError) as exc:
        raise_ollama_http_exception(exc)
    except RuntimeError as exc:
        logger.warning("investigate dependency failure: %s", exc)
        raise HTTPException(status_code=503, detail="Investigation dependencies are unavailable.") from exc
    except Exception as exc:
        logger.exception("investigate execution failed", exc_info=exc)
        raise HTTPException(status_code=502, detail="Incident investigation failed unexpectedly.") from exc
