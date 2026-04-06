from fastapi import Body, Depends, FastAPI, HTTPException, Path, Request
from fastapi.responses import JSONResponse
from ollama import RequestError, ResponseError
from pydantic import ValidationError

from app.dependencies import (
    get_analyze_service,
    get_evaluation_summary_service,
    get_investigation_service,
    get_knowledge_base_service,
    get_runtime_health_service,
    get_workflow_service,
)
from app.rag.service import KnowledgeBaseService
from app.rag.utils import curate_knowledge_search_hits
from app.schemas import (
    AnalyzeRequest,
    AnalyzeResponse,
    EvalSummaryResponse,
    InvestigateRequest,
    InvestigateResponse,
    KnowledgeIngestRequest,
    KnowledgeIngestResponse,
    KnowledgeSearchRequest,
    KnowledgeSearchResponse,
    LivenessResponse,
    ProblemDetailResponse,
    ReadinessResponse,
    WorkflowApproveRequest,
    WorkflowInvestigateRequest,
    WorkflowRejectRequest,
    WorkflowResumeRequest,
    WorkflowThreadResponse,
)
from app.services.analyze_service import AnalyzeService
from app.services.evaluation_service import EvaluationSummaryService
from app.services.investigation_service import InvestigationService
from app.services.runtime_health_service import RuntimeHealthService
from app.services.workflow_service import WorkflowService

HEALTH_RESPONSE_EXAMPLE = {
    "check_type": "liveness",
    "alive": True,
    "status": "ok",
    "summary": "API process is alive.",
    "app": {
        "name": "SentinelOps",
        "version": "0.4.0",
    },
}

READY_RESPONSE_EXAMPLE = {
    "check_type": "readiness",
    "ready": True,
    "status": "ok",
    "summary": "All configured capabilities are ready to serve traffic.",
    "app": {
        "name": "SentinelOps",
        "version": "0.4.0",
    },
    "dependencies": {
        "ollama": {
            "status": "ok",
            "detail": "Ollama is reachable and all configured models are installed.",
            "metadata": {
                "endpoint": "http://localhost:11434/api/tags",
                "analyze_model": "llama3.2",
                "investigate_model": "llama3.2",
                "embedding_model": "embeddinggemma",
                "analyze_model_ready": True,
                "investigate_model_ready": True,
                "embedding_model_ready": True,
            },
        }
    },
    "capabilities": {
        "knowledge_search_endpoint": {
            "status": "ok",
            "detail": "Knowledge search can query the configured retrieval index.",
            "metadata": {},
        }
    },
}

READY_DEGRADED_EXAMPLE = {
    "check_type": "readiness",
    "ready": False,
    "status": "degraded",
    "summary": "One or more configured capabilities are not ready to serve traffic.",
    "app": {
        "name": "SentinelOps",
        "version": "0.4.0",
    },
    "dependencies": {
        "ollama": {
            "status": "degraded",
            "detail": "Ollama is reachable but some configured models are missing: embedding_model=embeddinggemma.",
            "metadata": {
                "endpoint": "http://localhost:11434/api/tags",
                "analyze_model": "llama3.2",
                "investigate_model": "llama3.2",
                "embedding_model": "embeddinggemma",
                "analyze_model_ready": True,
                "investigate_model_ready": True,
                "embedding_model_ready": False,
            },
        }
    },
    "capabilities": {
        "analyze_endpoint": {
            "status": "degraded",
            "detail": "Analyze can still return structured log summaries, but retrieval is unavailable so RAG evidence will not be attached.",
            "metadata": {},
        },
        "knowledge_ingest_endpoint": {
            "status": "unavailable",
            "detail": "Knowledge ingest requires the configured embedding model and retrieval backend to be ready.",
            "metadata": {},
        },
    },
}

EVAL_SUMMARY_EXAMPLE = {
    "mode": "deterministic_local",
    "summary": "Deterministic local evaluation summary for SentinelOps service logic, retrieval quality, and workflow durability.",
    "generated_at": "2026-04-04T00:00:00Z",
    "totals": {
        "total_cases": 48,
        "passed_cases": 48,
        "failed_cases": 0,
        "overall_pass_rate": 1.0,
    },
    "analyze": {
        "total_cases": 18,
        "passed_cases": 18,
        "failed_cases": 0,
        "pass_rate": 1.0,
        "average_confidence": 0.89,
        "retrieval_used_rate": 1.0,
        "average_confidence_by_incident_type": {
            "database": 0.92,
            "network": 0.87,
        },
        "common_failure_reasons": {},
    },
    "investigate": {
        "total_cases": 10,
        "passed_cases": 10,
        "failed_cases": 0,
        "pass_rate": 1.0,
        "average_confidence": 0.91,
        "retrieval_used_rate": 1.0,
        "average_confidence_by_incident_type": {
            "database": 0.95,
            "configuration": 0.88,
        },
        "common_failure_reasons": {},
    },
    "rag": {
        "total_cases": 10,
        "passed_cases": 10,
        "failed_cases": 0,
        "pass_rate": 1.0,
        "retrieval_hit_rate": 1.0,
        "average_hits_returned": 3.6,
        "corpus_document_count": 36,
        "corpus_chunk_count": 90,
        "common_failure_reasons": {},
    },
    "workflow": {
        "total_cases": 10,
        "passed_cases": 10,
        "failed_cases": 0,
        "pass_rate": 1.0,
        "waiting_for_approval_rate": 0.2,
        "completed_rate": 0.8,
        "approval_required_rate": 0.8,
        "approved_completion_count": 4,
        "rejected_completion_count": 2,
        "average_confidence": 0.88,
        "average_confidence_by_incident_type": {
            "database": 0.92,
            "network": 0.86,
        },
        "common_failure_reasons": {},
    },
}

WORKFLOW_TOOL_RESULT_EXAMPLE = {
    "name": "read_log_file",
    "arguments": {
        "path": "data/logs/database-current.log",
    },
    "ok": True,
    "cached": False,
    "payload": {
        "tool": "read_log_file",
        "ok": True,
        "path": "data/logs/database-current.log",
        "selected_lines": [
            "1: 2026-03-31 09:10:22 ERROR database connection timeout after 30 seconds",
            "3: 2026-03-31 09:10:24 ERROR connection pool exhausted on primary-postgres",
        ],
        "truncated": False,
        "total_nonempty_lines": 4,
    },
}

WORKFLOW_RETRIEVAL_HIT_EXAMPLE = {
    "chunk_id": "workflow-db-runbook",
    "document_type": "runbook",
    "source_path": "data/knowledge/runbooks/database-timeout-runbook.md",
    "citation": "data/knowledge/runbooks/database-timeout-runbook.md#Symptoms",
    "snippet": "Database timeout incidents usually include connection pool exhaustion or long-running postgres transactions.",
    "title": "Database timeout runbook",
    "section_path": "Symptoms",
    "incident_type": "database",
    "similarity_score": 0.94,
    "relevance": None,
    "display_rank": None,
}

WORKFLOW_PENDING_RESPONSE_EXAMPLE = {
    "thread_id": "workflow-7f1ac5f14f4d470ab8eb52885c32416a",
    "request_id": "09f4059d5f2140f28ef2857d05166d45",
    "status": "waiting_for_approval",
    "current_stage": "awaiting_approval",
    "current_step": "approval_node",
    "available_actions": ["approve", "reject", "resume"],
    "checkpoint_id": "1f130700-a35d-6f0c-8006-49d8f1e2aa61",
    "checkpoint_created_at": "2026-04-04T00:00:00Z",
    "input_summary": "Investigate this incident using the failing run and the previous healthy run. | candidate_logs=2",
    "incident_type": "database",
    "severity": "high",
    "suspected_root_cause": "Connection pool exhaustion on primary-postgres is causing repeated database timeouts and stalled checkout requests.",
    "remediation_plan": [
        "Confirm database reachability and server-side saturation on primary-postgres.",
        "Reduce caller concurrency or recycle unhealthy workers to relieve pool pressure.",
    ],
    "top_error_lines": [
        "1: 2026-03-31 09:10:22 ERROR database connection timeout after 30 seconds"
    ],
    "engineer_summary": None,
    "manager_summary": "The current database run is failing due to connection timeouts and pool exhaustion, while the previous run was healthy.",
    "retrieved_evidence": [
        "Database timeout incidents usually include connection pool exhaustion or long-running postgres transactions."
    ],
    "source_citations": [
        "read_log_file:data/logs/database-current.log",
        "data/knowledge/runbooks/database-timeout-runbook.md#Symptoms",
    ],
    "confidence": 0.92,
    "approval_required": True,
    "approval_status": "pending",
    "approval_reason": "High-impact remediation should be reviewed before anyone executes the checklist.",
    "approval_notes": None,
    "approval_request": {
        "type": "approval_required",
        "approval_reason": "High-impact remediation should be reviewed before anyone executes the checklist.",
        "incident_type": "database",
        "severity": "high",
        "suspected_root_cause": "Connection pool exhaustion on primary-postgres is causing repeated database timeouts and stalled checkout requests.",
        "manager_summary": "The current database run is failing due to connection timeouts and pool exhaustion, while the previous run was healthy.",
        "proposed_remediation_plan": [
            "Confirm database reachability and server-side saturation on primary-postgres.",
            "Reduce caller concurrency or recycle unhealthy workers to relieve pool pressure.",
        ],
        "source_citations": [
            "read_log_file:data/logs/database-current.log",
            "data/knowledge/runbooks/database-timeout-runbook.md#Symptoms",
        ],
    },
    "retrieval_status": "used",
    "tool_results": [WORKFLOW_TOOL_RESULT_EXAMPLE],
    "retrieved_chunks": [WORKFLOW_RETRIEVAL_HIT_EXAMPLE],
    "final_report": None,
    "errors": [],
}

WORKFLOW_COMPLETED_RESPONSE_EXAMPLE = {
    **WORKFLOW_PENDING_RESPONSE_EXAMPLE,
    "status": "completed",
    "current_stage": "completed",
    "current_step": "final_report_node",
    "available_actions": [],
    "approval_required": False,
    "approval_status": "not_required",
    "approval_reason": None,
    "approval_request": None,
    "engineer_summary": "SentinelOps classified this as a high database incident and completed the workflow without an approval gate.",
    "final_report": {
        "incident_type": "database",
        "severity": "high",
        "top_error_lines": [
            "1: 2026-03-31 09:10:22 ERROR database connection timeout after 30 seconds"
        ],
        "suspected_root_cause": "Connection pool exhaustion on primary-postgres is causing repeated database timeouts and stalled checkout requests.",
        "remediation_plan": [
            "Confirm database reachability and server-side saturation on primary-postgres.",
            "Reduce caller concurrency or recycle unhealthy workers to relieve pool pressure.",
        ],
        "engineer_summary": "SentinelOps classified this as a high database incident and completed the workflow without an approval gate.",
        "manager_summary": "The current database run is failing due to connection timeouts and pool exhaustion, while the previous run was healthy.",
        "retrieved_evidence": [
            "Database timeout incidents usually include connection pool exhaustion or long-running postgres transactions."
        ],
        "source_citations": [
            "read_log_file:data/logs/database-current.log",
            "data/knowledge/runbooks/database-timeout-runbook.md#Symptoms",
        ],
        "retrieval_status": "used",
        "approval_status": "not_required",
        "approval_notes": None,
        "confidence": 0.92,
    },
}

WORKFLOW_APPROVED_RESPONSE_EXAMPLE = {
    **WORKFLOW_COMPLETED_RESPONSE_EXAMPLE,
    "approval_required": True,
    "approval_status": "approved",
    "approval_reason": "High-impact remediation should be reviewed before anyone executes the checklist.",
    "approval_notes": "Approved for the on-call team to execute.",
    "engineer_summary": "SentinelOps classified this as a high database incident. Approval was granted for the proposed remediation checklist.",
    "final_report": {
        **WORKFLOW_COMPLETED_RESPONSE_EXAMPLE["final_report"],
        "approval_status": "approved",
        "approval_notes": "Approved for the on-call team to execute.",
        "engineer_summary": "SentinelOps classified this as a high database incident. Approval was granted for the proposed remediation checklist.",
    },
}

WORKFLOW_REJECTED_RESPONSE_EXAMPLE = {
    **WORKFLOW_APPROVED_RESPONSE_EXAMPLE,
    "approval_status": "rejected",
    "approval_notes": "Use a safer reviewed checklist before making runtime changes.",
    "remediation_plan": [
        "Freeze deploys touching the checkout service until the database saturation is verified.",
        "Page the database owner and confirm a safe rollback or failover path before restarting workers.",
    ],
    "engineer_summary": "SentinelOps classified this as a high database incident. Approval was rejected and the remediation checklist was replaced by the reviewer.",
    "final_report": {
        **WORKFLOW_APPROVED_RESPONSE_EXAMPLE["final_report"],
        "approval_status": "rejected",
        "approval_notes": "Use a safer reviewed checklist before making runtime changes.",
        "remediation_plan": [
            "Freeze deploys touching the checkout service until the database saturation is verified.",
            "Page the database owner and confirm a safe rollback or failover path before restarting workers.",
        ],
        "engineer_summary": "SentinelOps classified this as a high database incident. Approval was rejected and the remediation checklist was replaced by the reviewer.",
    },
}

WORKFLOW_FAILED_RESPONSE_EXAMPLE = {
    "thread_id": "workflow-failure-demo",
    "request_id": "2f94f204d8f74b98b2f3487e6b01d420",
    "status": "failed",
    "current_stage": "failed",
    "current_step": "hypothesis_node",
    "available_actions": [],
    "checkpoint_id": "1f130700-a35d-6f0c-8006-49d8f1e2aa61",
    "checkpoint_created_at": "2026-04-04T00:00:00Z",
    "input_summary": "Investigate the failing run with the previous healthy run. | candidate_logs=2",
    "incident_type": "database",
    "severity": "high",
    "suspected_root_cause": None,
    "remediation_plan": [],
    "top_error_lines": [
        "1: 2026-03-31 09:10:22 ERROR database connection timeout after 30 seconds",
        "3: 2026-03-31 09:10:24 ERROR connection pool exhausted on primary-postgres",
    ],
    "engineer_summary": None,
    "manager_summary": None,
    "retrieved_evidence": [
        "Database timeout incidents usually include connection pool exhaustion or long-running postgres transactions.",
    ],
    "source_citations": [
        "read_log_file:data/logs/database-current.log",
        "compare_two_logs:data/logs/database-previous.log->data/logs/database-current.log",
        "data/knowledge/runbooks/database-timeout-runbook.md#Symptoms",
    ],
    "confidence": None,
    "approval_required": False,
    "approval_status": "not_required",
    "approval_reason": None,
    "approval_notes": None,
    "approval_request": None,
    "retrieval_status": "used",
    "tool_results": [WORKFLOW_TOOL_RESULT_EXAMPLE],
    "retrieved_chunks": [WORKFLOW_RETRIEVAL_HIT_EXAMPLE],
    "final_report": None,
    "errors": [
        "workflow model synthesis failed",
    ],
}

WORKFLOW_NOT_FOUND_PROBLEM_EXAMPLE = {
    "type": "urn:sentinelops:problem:workflow-thread-not-found",
    "title": "Workflow thread not found",
    "status": 404,
    "detail": "Workflow thread 'workflow-missing' was not found.",
    "instance": "/workflow/workflow-missing",
    "code": "workflow_thread_not_found",
    "thread_id": "workflow-missing",
}

WORKFLOW_CONFLICT_PROBLEM_EXAMPLE = {
    "type": "urn:sentinelops:problem:workflow-thread-conflict",
    "title": "Workflow thread state conflict",
    "status": 409,
    "detail": "Workflow thread 'workflow-complete-demo' is already complete.",
    "instance": "/workflow/workflow-complete-demo/resume",
    "code": "workflow_thread_conflict",
    "thread_id": "workflow-complete-demo",
}

WORKFLOW_INVALID_STATE_PROBLEM_EXAMPLE = {
    "type": "urn:sentinelops:problem:workflow-invalid-state",
    "title": "Workflow response validation failed",
    "status": 502,
    "detail": "Workflow returned invalid structured state.",
    "instance": "/workflow/investigate",
    "code": "workflow_invalid_state",
}

WORKFLOW_OLLAMA_UNAVAILABLE_PROBLEM_EXAMPLE = {
    "type": "urn:sentinelops:problem:model-runtime-unavailable",
    "title": "Model runtime unavailable",
    "status": 503,
    "detail": "Ollama is unavailable or not ready to serve requests. Ensure the Ollama app or `ollama serve` is running and healthy, then retry.",
    "instance": "/workflow/investigate",
    "code": "model_runtime_unavailable",
}

WORKFLOW_INVESTIGATE_REQUEST_EXAMPLES = {
    "default": {
        "summary": "Start a workflow investigation with approval enabled",
        "value": {
            "prompt": "Investigate this incident using the failing run and the previous healthy run.",
            "candidate_log_paths": [
                "data/logs/database-current.log",
                "data/logs/database-previous.log",
            ],
            "incident_type_hint": "database",
            "require_approval_for_remediation": True,
        },
    }
}

WORKFLOW_RESUME_REQUEST_EXAMPLES = {
    "approved": {
        "summary": "Resume with an approval decision",
        "value": {
            "decision": "approved",
            "review_notes": "Approved for the on-call team to execute.",
            "edited_remediation_plan": [],
        },
    },
    "rejected": {
        "summary": "Resume with a rejection and replacement checklist",
        "value": {
            "decision": "rejected",
            "review_notes": "Use a safer reviewed checklist before making runtime changes.",
            "edited_remediation_plan": [
                "Freeze deploys touching the checkout service until the database saturation is verified.",
                "Page the database owner and confirm a safe rollback or failover path before restarting workers.",
            ],
        },
    },
}

WORKFLOW_APPROVE_REQUEST_EXAMPLES = {
    "default": {
        "summary": "Approve the generated checklist",
        "value": {
            "review_notes": "Approved for the on-call team to execute.",
            "edited_remediation_plan": [],
        },
    }
}

WORKFLOW_REJECT_REQUEST_EXAMPLES = {
    "default": {
        "summary": "Reject and replace the generated checklist",
        "value": {
            "reason": "Use a safer reviewed checklist before making runtime changes.",
            "edited_remediation_plan": [
                "Freeze deploys touching the checkout service until the database saturation is verified.",
                "Page the database owner and confirm a safe rollback or failover path before restarting workers.",
            ],
        },
    }
}

app = FastAPI(
    title="SentinelOps",
    version="0.4.0",
    description=(
        "Local incident analysis API with three primary operational paths: `/analyze` for pasted log text, "
        "`/investigate` for the one-shot tool-assisted investigation flow, and `/workflow/investigate` for the "
        "checkpointed Month 4 investigation workflow with approval gates. Retrieval-backed evidence is attached "
        "whenever the local knowledge base is ready."
    ),
)


def _ollama_error_detail(exc: Exception) -> str:
    message = str(exc).strip()
    lowered = message.lower()

    if "upgrade in progress" in lowered:
        return (
            "Ollama is installed but not ready to serve requests because an upgrade is still in progress. "
            "Finish or restart Ollama, then try the request again."
        )
    if "model" in lowered and "not found" in lowered:
        return (
            "Ollama is reachable, but a configured model is missing. "
            f"Details: {message}"
        )
    return (
        "Ollama is unavailable or not ready to serve requests. "
        "Ensure the Ollama app or `ollama serve` is running and healthy, then retry."
    )


def _raise_ollama_http_exception(exc: Exception) -> None:
    raise HTTPException(status_code=503, detail=_ollama_error_detail(exc)) from exc


def _exception_message(exc: Exception) -> str:
    if getattr(exc, "args", None):
        return str(exc.args[0])
    return str(exc)


def _problem_response(
    *,
    request: Request,
    status_code: int,
    code: str,
    title: str,
    detail: str,
    thread_id: str | None = None,
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
    return JSONResponse(
        status_code=status_code,
        content=payload.model_dump(mode="json", exclude_none=True),
        media_type="application/problem+json",
    )


@app.get(
    "/health",
    response_model=LivenessResponse,
    summary="Minimal liveness check",
    description=(
        "Returns a minimal liveness response for the API process only. `/health` intentionally does not check "
        "Ollama, Chroma, or retrieval readiness, so it stays stable for container/process supervision."
    ),
    responses={
        200: {
            "description": "Liveness response",
            "content": {
                "application/json": {
                    "example": HEALTH_RESPONSE_EXAMPLE,
                }
            },
        }
    },
)
def health(
    service: RuntimeHealthService = Depends(get_runtime_health_service),
) -> LivenessResponse:
    return service.health_report()


@app.get(
    "/ready",
    response_model=ReadinessResponse,
    summary="Readiness check for configured workloads",
    description=(
        "Returns readiness for the configured SentinelOps workloads. `/ready` returns 200 only when `/analyze`, "
        "`/investigate`, `/knowledge/ingest`, and `/knowledge/search` are all ready with their configured models "
        "and retrieval backend. It returns 503 when the app would have to degrade or fail for one of those routes."
    ),
    responses={
        200: {
            "description": "Readiness success response",
            "content": {
                "application/json": {
                    "example": READY_RESPONSE_EXAMPLE,
                }
            },
        },
        503: {
            "description": "Readiness failure response",
            "content": {
                "application/json": {
                    "example": READY_DEGRADED_EXAMPLE,
                }
            },
        },
    },
)
def ready(
    service: RuntimeHealthService = Depends(get_runtime_health_service),
) -> ReadinessResponse:
    report = service.readiness_report()
    if not service.is_ready(report):
        return JSONResponse(status_code=503, content=report.model_dump(mode="json"))  # type: ignore[return-value]
    return report


@app.get(
    "/eval/summary",
    response_model=EvalSummaryResponse,
    summary="Deterministic evaluation summary",
    description=(
        "Runs the local deterministic evaluation harness and returns a summary you can use in demos, judging, "
        "or regression tracking. This endpoint does not depend on live Ollama generations; it exercises current "
        "service logic, retrieval wiring, and structured output handling against the repository eval corpus."
    ),
    responses={
        200: {
            "description": "Evaluation summary response",
            "content": {
                "application/json": {
                    "example": EVAL_SUMMARY_EXAMPLE,
                }
            },
        }
    },
)
def eval_summary(
    service: EvaluationSummaryService = Depends(get_evaluation_summary_service),
) -> EvalSummaryResponse:
    return service.build_summary()


@app.post(
    "/analyze",
    response_model=AnalyzeResponse,
    summary="Analyze pasted log text",
    description=(
        "Classifies pasted log text into a structured incident summary. When the local retrieval stack is ready, "
        "SentinelOps also retrieves supporting knowledge-base evidence and returns citations. If retrieval is not "
        "ready, the endpoint still returns 200 with `retrieval_status=\"unavailable\"`."
    ),
)
def analyze(
    request: AnalyzeRequest,
    service: AnalyzeService = Depends(get_analyze_service),
) -> AnalyzeResponse:
    try:
        return service.analyze(request)
    except ValidationError as exc:
        raise HTTPException(status_code=502, detail="Model returned invalid analyze JSON.") from exc
    except (RequestError, ResponseError) as exc:
        _raise_ollama_http_exception(exc)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post(
    "/investigate",
    response_model=InvestigateResponse,
    summary="Investigate an incident with safe local tools and retrieval",
    description=(
        "Runs the controlled investigation workflow. SentinelOps reads candidate logs, compares runs when useful, "
        "loads safe local guidance, retrieves supporting knowledge-base evidence, and then returns a structured "
        "incident report with citations. If retrieval is unavailable, the endpoint still returns 200 with "
        "`retrieval_status=\"unavailable\"`."
    ),
)
def investigate(
    request: InvestigateRequest,
    service: InvestigationService = Depends(get_investigation_service),
) -> InvestigateResponse:
    try:
        return service.investigate(request)
    except ValidationError as exc:
        raise HTTPException(status_code=502, detail="Model returned invalid investigation JSON.") from exc
    except (RequestError, ResponseError) as exc:
        _raise_ollama_http_exception(exc)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post(
    "/workflow/investigate",
    response_model=WorkflowThreadResponse,
    summary="Start the Month 4 checkpointed investigation workflow",
    description=(
        "Runs the controlled LangGraph workflow for SentinelOps Month 4. The workflow persists thread state, "
        "collects tool evidence and retrieval evidence, drafts a hypothesis and remediation checklist, and can "
        "pause for approval before producing the final report."
    ),
    responses={
        200: {
            "description": "Workflow thread created or completed.",
            "content": {
                "application/json": {
                    "examples": {
                        "waiting_for_approval": {
                            "summary": "Workflow paused for approval",
                            "value": WORKFLOW_PENDING_RESPONSE_EXAMPLE,
                        },
                        "completed_without_approval": {
                            "summary": "Workflow completed without an approval gate",
                            "value": WORKFLOW_COMPLETED_RESPONSE_EXAMPLE,
                        },
                    }
                }
            },
        },
        409: {
            "model": ProblemDetailResponse,
            "description": "The supplied thread_id already exists.",
            "content": {
                "application/problem+json": {
                    "schema": {
                        "$ref": "#/components/schemas/ProblemDetailResponse",
                    },
                    "example": WORKFLOW_CONFLICT_PROBLEM_EXAMPLE,
                }
            },
        },
        502: {
            "model": ProblemDetailResponse,
            "description": "Workflow returned an invalid or unexpected response shape.",
            "content": {
                "application/problem+json": {
                    "schema": {
                        "$ref": "#/components/schemas/ProblemDetailResponse",
                    },
                    "example": WORKFLOW_INVALID_STATE_PROBLEM_EXAMPLE,
                }
            },
        },
        503: {
            "model": ProblemDetailResponse,
            "description": "Model runtime is unavailable.",
            "content": {
                "application/problem+json": {
                    "schema": {
                        "$ref": "#/components/schemas/ProblemDetailResponse",
                    },
                    "example": WORKFLOW_OLLAMA_UNAVAILABLE_PROBLEM_EXAMPLE,
                }
            },
        },
    },
)
def workflow_investigate(
    request_context: Request,
    request: WorkflowInvestigateRequest = Body(openapi_examples=WORKFLOW_INVESTIGATE_REQUEST_EXAMPLES),
    service: WorkflowService = Depends(get_workflow_service),
) -> WorkflowThreadResponse | JSONResponse:
    try:
        return service.start_investigation(request)
    except ValueError as exc:
        return _problem_response(
            request=request_context,
            status_code=409,
            code="workflow_thread_conflict",
            title="Workflow thread state conflict",
            detail=_exception_message(exc),
            thread_id=request.thread_id,
        )
    except ValidationError as exc:
        return _problem_response(
            request=request_context,
            status_code=502,
            code="workflow_invalid_state",
            title="Workflow response validation failed",
            detail="Workflow returned invalid structured state.",
            thread_id=request.thread_id,
        )
    except (RequestError, ResponseError) as exc:
        return _problem_response(
            request=request_context,
            status_code=503,
            code="model_runtime_unavailable",
            title="Model runtime unavailable",
            detail=_ollama_error_detail(exc),
            thread_id=request.thread_id,
        )
    except Exception as exc:
        return _problem_response(
            request=request_context,
            status_code=502,
            code="workflow_runtime_error",
            title="Workflow execution failed",
            detail=_exception_message(exc),
            thread_id=request.thread_id,
        )


@app.get(
    "/workflow/{thread_id}",
    response_model=WorkflowThreadResponse,
    summary="Inspect the current workflow thread state",
    description=(
        "Returns the current checkpointed workflow state, including the current step, any pending approval "
        "request, tool evidence, retrieved chunks, and the final report when the workflow is complete."
    ),
    responses={
        200: {
            "description": "Current workflow thread state.",
            "content": {
                "application/json": {
                    "examples": {
                        "waiting_for_approval": {
                            "summary": "Thread paused for approval",
                            "value": WORKFLOW_PENDING_RESPONSE_EXAMPLE,
                        },
                        "completed": {
                            "summary": "Completed thread",
                            "value": WORKFLOW_APPROVED_RESPONSE_EXAMPLE,
                        },
                        "failed": {
                            "summary": "Failed thread preserved for inspection",
                            "value": WORKFLOW_FAILED_RESPONSE_EXAMPLE,
                        },
                    }
                }
            },
        },
        404: {
            "model": ProblemDetailResponse,
            "description": "The thread_id does not exist.",
            "content": {
                "application/problem+json": {
                    "schema": {
                        "$ref": "#/components/schemas/ProblemDetailResponse",
                    },
                    "example": WORKFLOW_NOT_FOUND_PROBLEM_EXAMPLE,
                }
            },
        },
    },
)
def get_workflow_thread(
    request_context: Request,
    thread_id: str = Path(
        ...,
        min_length=1,
        max_length=120,
        description="Workflow thread identifier returned by POST /workflow/investigate.",
    ),
    service: WorkflowService = Depends(get_workflow_service),
) -> WorkflowThreadResponse | JSONResponse:
    try:
        return service.get_thread(thread_id)
    except KeyError as exc:
        return _problem_response(
            request=request_context,
            status_code=404,
            code="workflow_thread_not_found",
            title="Workflow thread not found",
            detail=_exception_message(exc),
            thread_id=thread_id,
        )


@app.post(
    "/workflow/{thread_id}/resume",
    response_model=WorkflowThreadResponse,
    summary="Resume a paused workflow thread",
    description=(
        "Resumes the current SentinelOps workflow thread with an explicit human decision payload. In Month 4, "
        "the active interrupt is the remediation approval gate, so the resume payload carries the approval or "
        "rejection decision plus optional reviewer notes or edits."
    ),
    responses={
        200: {
            "description": "Workflow thread resumed and progressed.",
            "content": {
                "application/json": {
                    "examples": {
                        "approved": {
                            "summary": "Approval-style resume completed the workflow",
                            "value": WORKFLOW_APPROVED_RESPONSE_EXAMPLE,
                        },
                        "rejected": {
                            "summary": "Rejection-style resume completed with reviewer edits",
                            "value": WORKFLOW_REJECTED_RESPONSE_EXAMPLE,
                        },
                    }
                }
            },
        },
        404: {
            "model": ProblemDetailResponse,
            "description": "The thread_id does not exist.",
            "content": {
                "application/problem+json": {
                    "schema": {
                        "$ref": "#/components/schemas/ProblemDetailResponse",
                    },
                    "example": WORKFLOW_NOT_FOUND_PROBLEM_EXAMPLE,
                }
            },
        },
        409: {
            "model": ProblemDetailResponse,
            "description": "The thread is not waiting for input or is already finished.",
            "content": {
                "application/problem+json": {
                    "schema": {
                        "$ref": "#/components/schemas/ProblemDetailResponse",
                    },
                    "example": WORKFLOW_CONFLICT_PROBLEM_EXAMPLE,
                }
            },
        },
        502: {
            "model": ProblemDetailResponse,
            "description": "Workflow returned an invalid or unexpected response shape.",
            "content": {
                "application/problem+json": {
                    "schema": {
                        "$ref": "#/components/schemas/ProblemDetailResponse",
                    },
                    "example": {
                        **WORKFLOW_INVALID_STATE_PROBLEM_EXAMPLE,
                        "instance": "/workflow/workflow-123/resume",
                    },
                }
            },
        },
        503: {
            "model": ProblemDetailResponse,
            "description": "Model runtime is unavailable.",
            "content": {
                "application/problem+json": {
                    "schema": {
                        "$ref": "#/components/schemas/ProblemDetailResponse",
                    },
                    "example": {
                        **WORKFLOW_OLLAMA_UNAVAILABLE_PROBLEM_EXAMPLE,
                        "instance": "/workflow/workflow-123/resume",
                    },
                }
            },
        },
    },
)
def resume_workflow_thread(
    request_context: Request,
    request: WorkflowResumeRequest = Body(openapi_examples=WORKFLOW_RESUME_REQUEST_EXAMPLES),
    thread_id: str = Path(
        ...,
        min_length=1,
        max_length=120,
        description="Workflow thread identifier returned by POST /workflow/investigate.",
    ),
    service: WorkflowService = Depends(get_workflow_service),
) -> WorkflowThreadResponse | JSONResponse:
    try:
        return service.resume(thread_id, request)
    except KeyError as exc:
        return _problem_response(
            request=request_context,
            status_code=404,
            code="workflow_thread_not_found",
            title="Workflow thread not found",
            detail=_exception_message(exc),
            thread_id=thread_id,
        )
    except RuntimeError as exc:
        return _problem_response(
            request=request_context,
            status_code=409,
            code="workflow_thread_conflict",
            title="Workflow thread state conflict",
            detail=_exception_message(exc),
            thread_id=thread_id,
        )
    except ValidationError as exc:
        return _problem_response(
            request=request_context,
            status_code=502,
            code="workflow_invalid_state",
            title="Workflow response validation failed",
            detail="Workflow resume returned invalid structured state.",
            thread_id=thread_id,
        )
    except (RequestError, ResponseError) as exc:
        return _problem_response(
            request=request_context,
            status_code=503,
            code="model_runtime_unavailable",
            title="Model runtime unavailable",
            detail=_ollama_error_detail(exc),
            thread_id=thread_id,
        )
    except Exception as exc:
        return _problem_response(
            request=request_context,
            status_code=502,
            code="workflow_runtime_error",
            title="Workflow execution failed",
            detail=_exception_message(exc),
            thread_id=thread_id,
        )


@app.post(
    "/workflow/{thread_id}/approve",
    response_model=WorkflowThreadResponse,
    summary="Approve the paused remediation checklist",
    description="Approves the current approval gate and continues the workflow to the final report.",
    responses={
        200: {
            "description": "Workflow completed after approval.",
            "content": {
                "application/json": {
                    "example": WORKFLOW_APPROVED_RESPONSE_EXAMPLE,
                }
            },
        },
        404: {
            "model": ProblemDetailResponse,
            "description": "The thread_id does not exist.",
            "content": {
                "application/problem+json": {
                    "schema": {
                        "$ref": "#/components/schemas/ProblemDetailResponse",
                    },
                    "example": WORKFLOW_NOT_FOUND_PROBLEM_EXAMPLE,
                }
            },
        },
        409: {
            "model": ProblemDetailResponse,
            "description": "The thread is not waiting for approval or is already finished.",
            "content": {
                "application/problem+json": {
                    "schema": {
                        "$ref": "#/components/schemas/ProblemDetailResponse",
                    },
                    "example": WORKFLOW_CONFLICT_PROBLEM_EXAMPLE,
                }
            },
        },
        502: {
            "model": ProblemDetailResponse,
            "description": "Workflow returned an invalid or unexpected response shape.",
            "content": {
                "application/problem+json": {
                    "schema": {
                        "$ref": "#/components/schemas/ProblemDetailResponse",
                    },
                    "example": {
                        **WORKFLOW_INVALID_STATE_PROBLEM_EXAMPLE,
                        "instance": "/workflow/workflow-123/approve",
                    },
                }
            },
        },
        503: {
            "model": ProblemDetailResponse,
            "description": "Model runtime is unavailable.",
            "content": {
                "application/problem+json": {
                    "schema": {
                        "$ref": "#/components/schemas/ProblemDetailResponse",
                    },
                    "example": {
                        **WORKFLOW_OLLAMA_UNAVAILABLE_PROBLEM_EXAMPLE,
                        "instance": "/workflow/workflow-123/approve",
                    },
                }
            },
        },
    },
)
def approve_workflow_thread(
    request_context: Request,
    request: WorkflowApproveRequest = Body(openapi_examples=WORKFLOW_APPROVE_REQUEST_EXAMPLES),
    thread_id: str = Path(
        ...,
        min_length=1,
        max_length=120,
        description="Workflow thread identifier returned by POST /workflow/investigate.",
    ),
    service: WorkflowService = Depends(get_workflow_service),
) -> WorkflowThreadResponse | JSONResponse:
    try:
        return service.approve(thread_id, request)
    except KeyError as exc:
        return _problem_response(
            request=request_context,
            status_code=404,
            code="workflow_thread_not_found",
            title="Workflow thread not found",
            detail=_exception_message(exc),
            thread_id=thread_id,
        )
    except RuntimeError as exc:
        return _problem_response(
            request=request_context,
            status_code=409,
            code="workflow_thread_conflict",
            title="Workflow thread state conflict",
            detail=_exception_message(exc),
            thread_id=thread_id,
        )
    except ValidationError as exc:
        return _problem_response(
            request=request_context,
            status_code=502,
            code="workflow_invalid_state",
            title="Workflow response validation failed",
            detail="Workflow approval returned invalid structured state.",
            thread_id=thread_id,
        )
    except (RequestError, ResponseError) as exc:
        return _problem_response(
            request=request_context,
            status_code=503,
            code="model_runtime_unavailable",
            title="Model runtime unavailable",
            detail=_ollama_error_detail(exc),
            thread_id=thread_id,
        )
    except Exception as exc:
        return _problem_response(
            request=request_context,
            status_code=502,
            code="workflow_runtime_error",
            title="Workflow execution failed",
            detail=_exception_message(exc),
            thread_id=thread_id,
        )


@app.post(
    "/workflow/{thread_id}/reject",
    response_model=WorkflowThreadResponse,
    summary="Reject or edit the paused remediation checklist",
    description=(
        "Rejects the current approval gate. You can optionally attach an edited remediation checklist so the final "
        "thread report captures the reviewer-adjusted plan."
    ),
    responses={
        200: {
            "description": "Workflow completed after rejection or plan replacement.",
            "content": {
                "application/json": {
                    "example": WORKFLOW_REJECTED_RESPONSE_EXAMPLE,
                }
            },
        },
        404: {
            "model": ProblemDetailResponse,
            "description": "The thread_id does not exist.",
            "content": {
                "application/problem+json": {
                    "schema": {
                        "$ref": "#/components/schemas/ProblemDetailResponse",
                    },
                    "example": WORKFLOW_NOT_FOUND_PROBLEM_EXAMPLE,
                }
            },
        },
        409: {
            "model": ProblemDetailResponse,
            "description": "The thread is not waiting for approval or is already finished.",
            "content": {
                "application/problem+json": {
                    "schema": {
                        "$ref": "#/components/schemas/ProblemDetailResponse",
                    },
                    "example": WORKFLOW_CONFLICT_PROBLEM_EXAMPLE,
                }
            },
        },
        502: {
            "model": ProblemDetailResponse,
            "description": "Workflow returned an invalid or unexpected response shape.",
            "content": {
                "application/problem+json": {
                    "schema": {
                        "$ref": "#/components/schemas/ProblemDetailResponse",
                    },
                    "example": {
                        **WORKFLOW_INVALID_STATE_PROBLEM_EXAMPLE,
                        "instance": "/workflow/workflow-123/reject",
                    },
                }
            },
        },
        503: {
            "model": ProblemDetailResponse,
            "description": "Model runtime is unavailable.",
            "content": {
                "application/problem+json": {
                    "schema": {
                        "$ref": "#/components/schemas/ProblemDetailResponse",
                    },
                    "example": {
                        **WORKFLOW_OLLAMA_UNAVAILABLE_PROBLEM_EXAMPLE,
                        "instance": "/workflow/workflow-123/reject",
                    },
                }
            },
        },
    },
)
def reject_workflow_thread(
    request_context: Request,
    request: WorkflowRejectRequest = Body(openapi_examples=WORKFLOW_REJECT_REQUEST_EXAMPLES),
    thread_id: str = Path(
        ...,
        min_length=1,
        max_length=120,
        description="Workflow thread identifier returned by POST /workflow/investigate.",
    ),
    service: WorkflowService = Depends(get_workflow_service),
) -> WorkflowThreadResponse | JSONResponse:
    try:
        return service.reject(thread_id, request)
    except KeyError as exc:
        return _problem_response(
            request=request_context,
            status_code=404,
            code="workflow_thread_not_found",
            title="Workflow thread not found",
            detail=_exception_message(exc),
            thread_id=thread_id,
        )
    except RuntimeError as exc:
        return _problem_response(
            request=request_context,
            status_code=409,
            code="workflow_thread_conflict",
            title="Workflow thread state conflict",
            detail=_exception_message(exc),
            thread_id=thread_id,
        )
    except ValidationError as exc:
        return _problem_response(
            request=request_context,
            status_code=502,
            code="workflow_invalid_state",
            title="Workflow response validation failed",
            detail="Workflow rejection returned invalid structured state.",
            thread_id=thread_id,
        )
    except (RequestError, ResponseError) as exc:
        return _problem_response(
            request=request_context,
            status_code=503,
            code="model_runtime_unavailable",
            title="Model runtime unavailable",
            detail=_ollama_error_detail(exc),
            thread_id=thread_id,
        )
    except Exception as exc:
        return _problem_response(
            request=request_context,
            status_code=502,
            code="workflow_runtime_error",
            title="Workflow execution failed",
            detail=_exception_message(exc),
            thread_id=thread_id,
        )


@app.post(
    "/knowledge/ingest",
    response_model=KnowledgeIngestResponse,
    summary="Rebuild the local knowledge index",
    description=(
        "Reads the curated local knowledge corpus, chunks documents, generates embeddings through Ollama, and "
        "rebuilds the configured retrieval index. The response reports both source-document counts and indexed "
        "chunk counts by document type. This endpoint requires the configured embedding model and knowledge-store "
        "backend to be ready."
    ),
)
def ingest_knowledge(
    request: KnowledgeIngestRequest,
    service: KnowledgeBaseService = Depends(get_knowledge_base_service),
) -> KnowledgeIngestResponse:
    if request.reset and not request.confirm_reset:
        raise HTTPException(
            status_code=400,
            detail="Destructive reset requires confirm_reset=true.",
        )
    try:
        return service.rebuild_index(reset=request.reset)
    except RequestError as exc:
        _raise_ollama_http_exception(exc)
    except ResponseError as exc:
        _raise_ollama_http_exception(exc)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post(
    "/knowledge/search",
    response_model=KnowledgeSearchResponse,
    summary="Search the local knowledge base",
    description=(
        "Runs semantic search over the indexed local knowledge base and returns top matching chunks with metadata "
        "and citations. Results are lightly curated for diversity so the response surfaces a more useful mix of "
        "supporting sources instead of multiple near-duplicate chunks from the same document. Raw `similarity_score` "
        "values are still returned, while `relevance`, `display_rank`, and `ranking_strategy` explain the final "
        "presentation order. This endpoint "
        "requires the configured embedding model and knowledge-store backend to be ready."
    ),
)
def search_knowledge(
    request: KnowledgeSearchRequest,
    service: KnowledgeBaseService = Depends(get_knowledge_base_service),
) -> KnowledgeSearchResponse:
    try:
        candidate_results = service.search(
            query=request.query,
            top_k=min(max(request.top_k * 4, request.top_k), 12),
            document_types=request.document_types or None,
            incident_type_hint=request.incident_type_hint,
        )
        results = curate_knowledge_search_hits(
            candidate_results,
            query=request.query,
            limit=request.top_k,
        )
        return KnowledgeSearchResponse(
            query=request.query,
            total_results=len(results),
            collection_name=service.collection_name,
            ranking_strategy="diversified_semantic_search",
            results=results,
        )
    except ValidationError as exc:
        raise HTTPException(status_code=502, detail="Knowledge search returned invalid retrieval data.") from exc
    except RequestError as exc:
        _raise_ollama_http_exception(exc)
    except ResponseError as exc:
        _raise_ollama_http_exception(exc)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
