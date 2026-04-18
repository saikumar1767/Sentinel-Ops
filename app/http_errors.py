from __future__ import annotations

from collections.abc import Mapping
import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.schemas import ProblemDetailResponse

logger = logging.getLogger("sentinelops.errors")


def ollama_error_detail(exc: Exception) -> str:
    message = str(exc).strip()
    lowered = message.lower()

    if "upgrade in progress" in lowered:
        return (
            "Ollama is installed but not ready to serve requests because an upgrade is still in progress. "
            "Finish or restart Ollama, then try the request again."
        )
    if "model" in lowered and "not found" in lowered:
        return (
            "Ollama is reachable, but a configured model required by this route is missing."
        )
    return (
        "Ollama is unavailable or not ready to serve requests. "
        "Ensure the Ollama app or `ollama serve` is running and healthy, then retry."
    )


def raise_ollama_http_exception(exc: Exception) -> None:
    raise HTTPException(status_code=503, detail=ollama_error_detail(exc)) from exc


def exception_message(exc: Exception) -> str:
    if getattr(exc, "args", None):
        return str(exc.args[0])
    return str(exc)


def safe_detail(
    exc: Exception,
    *,
    default: str,
    expose_types: tuple[type[Exception], ...] = (),
) -> str:
    if expose_types and isinstance(exc, expose_types):
        message = exception_message(exc).strip()
        if message:
            return message
    return default


def problem_response(
    *,
    request: Request,
    status_code: int,
    code: str,
    title: str,
    detail: str,
    thread_id: str | None = None,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    payload = ProblemDetailResponse(
        type=f"urn:sentinelops:problem:{code}",
        title=title,
        status=status_code,
        detail=detail,
        instance=request.url.path,
        code=code,
        thread_id=thread_id,
    )
    response_headers = dict(headers or {})
    request_id = getattr(request.state, "request_id", None)
    if request_id:
        response_headers.setdefault("X-Request-ID", request_id)
    return JSONResponse(
        status_code=status_code,
        content=payload.model_dump(mode="json", exclude_none=True),
        headers=response_headers,
        media_type="application/problem+json",
    )


def install_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
        status_code = exc.status_code
        detail = exc.detail if isinstance(exc.detail, str) else "The request could not be completed."
        code_map = {
            400: ("invalid_request", "Invalid request"),
            401: ("authentication_required", "Authentication required"),
            403: ("forbidden", "Forbidden"),
            404: ("resource_not_found", "Resource not found"),
            409: ("request_conflict", "Request conflict"),
            422: ("request_validation_failed", "Request validation failed"),
            429: ("rate_limited", "Rate limited"),
            502: ("upstream_failure", "Upstream failure"),
            503: ("service_unavailable", "Service unavailable"),
        }
        code, title = code_map.get(status_code, ("http_error", "Request failed"))
        return problem_response(
            request=request,
            status_code=status_code,
            code=code,
            title=title,
            detail=detail,
            headers=getattr(exc, "headers", None),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        error_count = len(exc.errors())
        detail = "Request body or parameters failed validation."
        if error_count == 1:
            detail = "Request body or parameters failed validation in 1 field."
        elif error_count > 1:
            detail = f"Request body or parameters failed validation in {error_count} fields."
        return problem_response(
            request=request,
            status_code=422,
            code="request_validation_failed",
            title="Request validation failed",
            detail=detail,
        )

    @app.exception_handler(Exception)
    async def unexpected_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("unhandled_exception path=%s", request.url.path, exc_info=exc)
        return problem_response(
            request=request,
            status_code=500,
            code="internal_server_error",
            title="Internal server error",
            detail="An unexpected internal error occurred while processing the request.",
        )
