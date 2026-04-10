from __future__ import annotations

import json
import logging
import re
from time import perf_counter
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.openapi.utils import get_openapi

from app.dependencies import get_runtime_metrics, get_settings

logger = logging.getLogger("sentinelops.http")
_WORKFLOW_THREAD_PATH_RE = re.compile(
    r"^/workflow/(?P<thread_id>[^/]+)(?P<suffix>(?:/(?:approve|reject|resume|audit))?)$"
)


def configure_logging() -> None:
    settings = get_settings()
    root_logger = logging.getLogger()
    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    if not root_logger.handlers:
        logging.basicConfig(
            level=level,
            format="%(asctime)s %(levelname)s %(name)s %(message)s",
        )
    root_logger.setLevel(level)


def install_http_middleware(app: FastAPI) -> None:
    @app.middleware("http")
    async def production_runtime_middleware(request: Request, call_next):
        metrics = get_runtime_metrics()
        request_id = request.headers.get("X-Request-ID") or uuid4().hex
        request.state.request_id = request_id
        normalized_path = _normalize_metrics_path(request.url.path)
        start = perf_counter()

        response = await call_next(request)
        duration_ms = (perf_counter() - start) * 1000
        metrics.record_request(
            method=request.method,
            path=normalized_path,
            status_code=response.status_code,
            duration_ms=duration_ms,
        )
        _log_request(
            request_id=request_id,
            method=request.method,
            path=normalized_path,
            status_code=response.status_code,
            duration_ms=duration_ms,
        )
        response.headers.setdefault("X-Request-ID", request_id)
        response.headers["X-Process-Time-Ms"] = f"{duration_ms:.3f}"
        return response


def install_openapi_contracts(app: FastAPI) -> None:
    def custom_openapi():
        if app.openapi_schema is not None:
            return app.openapi_schema

        schema = get_openapi(
            title=app.title,
            version=app.version,
            description=app.description,
            tags=app.openapi_tags,
            routes=app.routes,
        )

        for path, operations in schema.get("paths", {}).items():
            for operation in operations.values():
                if isinstance(operation, dict):
                    _ensure_problem_response(
                        operation,
                        status_code="422",
                        title="Request validation failed",
                        description="Request validation failed.",
                    )
                    _normalize_problem_detail_response_media_types(operation)

        app.openapi_schema = schema
        return app.openapi_schema

    app.openapi = custom_openapi


def _ensure_problem_response(
    operation: dict,
    *,
    status_code: str,
    title: str,
    description: str,
) -> None:
    responses = operation.setdefault("responses", {})
    response = responses.setdefault(status_code, {})
    response["description"] = response.get("description") or description
    response["content"] = {
        "application/problem+json": {
            "schema": {"$ref": "#/components/schemas/ProblemDetailResponse"},
            "example": {
                "type": f"urn:sentinelops:problem:{title.lower().replace(' ', '_')}",
                "title": title,
                "status": int(status_code),
                "detail": description,
                "instance": "/example",
                "code": title.lower().replace(" ", "_"),
            },
        }
    }


def _normalize_problem_detail_response_media_types(operation: dict) -> None:
    for response in operation.get("responses", {}).values():
        content = response.get("content")
        if not isinstance(content, dict):
            continue

        for payload in content.values():
            if not isinstance(payload, dict):
                continue
            schema = payload.get("schema")
            if not isinstance(schema, dict):
                continue
            if schema.get("$ref") != "#/components/schemas/ProblemDetailResponse":
                continue

            response["content"] = {
                "application/problem+json": {
                    **payload,
                    "schema": schema,
                }
            }
            break


def _normalize_metrics_path(path: str) -> str:
    if path == "/workflow/investigate":
        return path

    match = _WORKFLOW_THREAD_PATH_RE.match(path)
    if not match:
        return path

    suffix = match.group("suffix") or ""
    return f"/workflow/{{thread_id}}{suffix}"


def _log_request(
    *,
    request_id: str,
    method: str,
    path: str,
    status_code: int,
    duration_ms: float,
) -> None:
    logger.info(
        json.dumps(
            {
                "event": "http_request",
                "request_id": request_id,
                "method": method.upper(),
                "path": path,
                "status_code": status_code,
                "duration_ms": round(duration_ms, 3),
            },
            sort_keys=True,
        )
    )
