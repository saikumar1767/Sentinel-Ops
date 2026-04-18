from __future__ import annotations

import logging

from fastapi import APIRouter, Body, Depends, Path, Request
from fastapi.responses import JSONResponse
from ollama import RequestError, ResponseError
from pydantic import ValidationError

from app.dependencies import get_workflow_service
from app.http_errors import ollama_error_detail, problem_response, safe_detail
from app.schemas import (
    ProblemDetailResponse,
    WorkflowApproveRequest,
    WorkflowAuditResponse,
    WorkflowInvestigateRequest,
    WorkflowRejectRequest,
    WorkflowResumeRequest,
    WorkflowThreadResponse,
)
from app.services.workflow_service import WorkflowService

logger = logging.getLogger("sentinelops.api.workflow")
router = APIRouter(tags=["workflow"])


@router.post(
    "/workflow/investigate",
    response_model=WorkflowThreadResponse,
    responses={
        409: {"model": ProblemDetailResponse},
        502: {"model": ProblemDetailResponse},
        503: {"model": ProblemDetailResponse},
    },
    summary="Start the checkpointed investigation workflow",
)
def workflow_investigate(
    request_context: Request,
    request: WorkflowInvestigateRequest = Body(...),
    service: WorkflowService = Depends(get_workflow_service),
) -> WorkflowThreadResponse | JSONResponse:
    try:
        return service.start_investigation(request)
    except ValueError as exc:
        return problem_response(
            request=request_context,
            status_code=409,
            code="workflow_thread_conflict",
            title="Workflow thread state conflict",
            detail=safe_detail(exc, default="Workflow thread state conflict.", expose_types=(ValueError,)),
            thread_id=request.thread_id,
        )
    except ValidationError:
        return problem_response(
            request=request_context,
            status_code=502,
            code="workflow_invalid_state",
            title="Workflow response validation failed",
            detail="Workflow returned invalid structured state.",
            thread_id=request.thread_id,
        )
    except (RequestError, ResponseError) as exc:
        return problem_response(
            request=request_context,
            status_code=503,
            code="model_runtime_unavailable",
            title="Model runtime unavailable",
            detail=ollama_error_detail(exc),
            thread_id=request.thread_id,
        )
    except Exception as exc:
        logger.exception("workflow start failed", exc_info=exc)
        return problem_response(
            request=request_context,
            status_code=502,
            code="workflow_runtime_error",
            title="Workflow execution failed",
            detail="Workflow execution failed unexpectedly.",
            thread_id=request.thread_id,
        )


@router.get(
    "/workflow/{thread_id}",
    response_model=WorkflowThreadResponse,
    responses={404: {"model": ProblemDetailResponse}},
    summary="Inspect the current workflow thread state",
)
def get_workflow_thread(
    request_context: Request,
    thread_id: str = Path(..., min_length=1, max_length=120),
    service: WorkflowService = Depends(get_workflow_service),
) -> WorkflowThreadResponse | JSONResponse:
    try:
        return service.get_thread(thread_id)
    except KeyError as exc:
        return problem_response(
            request=request_context,
            status_code=404,
            code="workflow_thread_not_found",
            title="Workflow thread not found",
            detail=safe_detail(exc, default="Workflow thread was not found.", expose_types=(KeyError,)),
            thread_id=thread_id,
        )


@router.get(
    "/workflow/{thread_id}/audit",
    response_model=WorkflowAuditResponse,
    responses={404: {"model": ProblemDetailResponse}},
    summary="Read the workflow approval audit trail",
)
def get_workflow_audit(
    request_context: Request,
    thread_id: str = Path(..., min_length=1, max_length=120),
    service: WorkflowService = Depends(get_workflow_service),
) -> WorkflowAuditResponse | JSONResponse:
    try:
        return service.audit_report(thread_id)
    except KeyError as exc:
        return problem_response(
            request=request_context,
            status_code=404,
            code="workflow_thread_not_found",
            title="Workflow thread not found",
            detail=safe_detail(exc, default="Workflow thread was not found.", expose_types=(KeyError,)),
            thread_id=thread_id,
        )


@router.post(
    "/workflow/{thread_id}/resume",
    response_model=WorkflowThreadResponse,
    responses={
        404: {"model": ProblemDetailResponse},
        409: {"model": ProblemDetailResponse},
        502: {"model": ProblemDetailResponse},
        503: {"model": ProblemDetailResponse},
    },
    summary="Resume a paused workflow thread",
)
def resume_workflow_thread(
    request_context: Request,
    request: WorkflowResumeRequest = Body(...),
    thread_id: str = Path(..., min_length=1, max_length=120),
    service: WorkflowService = Depends(get_workflow_service),
) -> WorkflowThreadResponse | JSONResponse:
    try:
        return service.resume(thread_id, request)
    except KeyError as exc:
        return _thread_problem(request_context, 404, "workflow_thread_not_found", "Workflow thread not found", exc, thread_id)
    except RuntimeError as exc:
        return _thread_problem(request_context, 409, "workflow_thread_conflict", "Workflow thread state conflict", exc, thread_id)
    except ValidationError:
        return problem_response(
            request=request_context,
            status_code=502,
            code="workflow_invalid_state",
            title="Workflow response validation failed",
            detail="Workflow resume returned invalid structured state.",
            thread_id=thread_id,
        )
    except (RequestError, ResponseError) as exc:
        return problem_response(
            request=request_context,
            status_code=503,
            code="model_runtime_unavailable",
            title="Model runtime unavailable",
            detail=ollama_error_detail(exc),
            thread_id=thread_id,
        )
    except Exception as exc:
        logger.exception("workflow resume failed", exc_info=exc)
        return problem_response(
            request=request_context,
            status_code=502,
            code="workflow_runtime_error",
            title="Workflow execution failed",
            detail="Workflow resume failed unexpectedly.",
            thread_id=thread_id,
        )


@router.post(
    "/workflow/{thread_id}/approve",
    response_model=WorkflowThreadResponse,
    responses={
        404: {"model": ProblemDetailResponse},
        409: {"model": ProblemDetailResponse},
        502: {"model": ProblemDetailResponse},
        503: {"model": ProblemDetailResponse},
    },
    summary="Approve the paused remediation checklist",
)
def approve_workflow_thread(
    request_context: Request,
    request: WorkflowApproveRequest = Body(...),
    thread_id: str = Path(..., min_length=1, max_length=120),
    service: WorkflowService = Depends(get_workflow_service),
) -> WorkflowThreadResponse | JSONResponse:
    try:
        return service.approve(thread_id, request)
    except KeyError as exc:
        return _thread_problem(request_context, 404, "workflow_thread_not_found", "Workflow thread not found", exc, thread_id)
    except RuntimeError as exc:
        return _thread_problem(request_context, 409, "workflow_thread_conflict", "Workflow thread state conflict", exc, thread_id)
    except ValidationError:
        return problem_response(
            request=request_context,
            status_code=502,
            code="workflow_invalid_state",
            title="Workflow response validation failed",
            detail="Workflow approval returned invalid structured state.",
            thread_id=thread_id,
        )
    except (RequestError, ResponseError) as exc:
        return problem_response(
            request=request_context,
            status_code=503,
            code="model_runtime_unavailable",
            title="Model runtime unavailable",
            detail=ollama_error_detail(exc),
            thread_id=thread_id,
        )
    except Exception as exc:
        logger.exception("workflow approval failed", exc_info=exc)
        return problem_response(
            request=request_context,
            status_code=502,
            code="workflow_runtime_error",
            title="Workflow execution failed",
            detail="Workflow approval failed unexpectedly.",
            thread_id=thread_id,
        )


@router.post(
    "/workflow/{thread_id}/reject",
    response_model=WorkflowThreadResponse,
    responses={
        404: {"model": ProblemDetailResponse},
        409: {"model": ProblemDetailResponse},
        502: {"model": ProblemDetailResponse},
        503: {"model": ProblemDetailResponse},
    },
    summary="Reject or edit the paused remediation checklist",
)
def reject_workflow_thread(
    request_context: Request,
    request: WorkflowRejectRequest = Body(...),
    thread_id: str = Path(..., min_length=1, max_length=120),
    service: WorkflowService = Depends(get_workflow_service),
) -> WorkflowThreadResponse | JSONResponse:
    try:
        return service.reject(thread_id, request)
    except KeyError as exc:
        return _thread_problem(request_context, 404, "workflow_thread_not_found", "Workflow thread not found", exc, thread_id)
    except RuntimeError as exc:
        return _thread_problem(request_context, 409, "workflow_thread_conflict", "Workflow thread state conflict", exc, thread_id)
    except ValidationError:
        return problem_response(
            request=request_context,
            status_code=502,
            code="workflow_invalid_state",
            title="Workflow response validation failed",
            detail="Workflow rejection returned invalid structured state.",
            thread_id=thread_id,
        )
    except (RequestError, ResponseError) as exc:
        return problem_response(
            request=request_context,
            status_code=503,
            code="model_runtime_unavailable",
            title="Model runtime unavailable",
            detail=ollama_error_detail(exc),
            thread_id=thread_id,
        )
    except Exception as exc:
        logger.exception("workflow rejection failed", exc_info=exc)
        return problem_response(
            request=request_context,
            status_code=502,
            code="workflow_runtime_error",
            title="Workflow execution failed",
            detail="Workflow rejection failed unexpectedly.",
            thread_id=thread_id,
        )


def _thread_problem(
    request_context: Request,
    status_code: int,
    code: str,
    title: str,
    exc: Exception,
    thread_id: str,
) -> JSONResponse:
    expose = (KeyError, RuntimeError)
    return problem_response(
        request=request_context,
        status_code=status_code,
        code=code,
        title=title,
        detail=safe_detail(exc, default=title + ".", expose_types=expose),
        thread_id=thread_id,
    )
