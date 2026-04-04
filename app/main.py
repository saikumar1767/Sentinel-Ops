from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import JSONResponse
from ollama import RequestError, ResponseError
from pydantic import ValidationError

from app.dependencies import (
    get_analyze_service,
    get_evaluation_summary_service,
    get_investigation_service,
    get_knowledge_base_service,
    get_runtime_health_service,
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
    ReadinessResponse,
)
from app.services.analyze_service import AnalyzeService
from app.services.evaluation_service import EvaluationSummaryService
from app.services.investigation_service import InvestigationService
from app.services.runtime_health_service import RuntimeHealthService

HEALTH_RESPONSE_EXAMPLE = {
    "check_type": "liveness",
    "alive": True,
    "status": "ok",
    "summary": "API process is alive.",
    "app": {
        "name": "SentinelOps",
        "version": "0.3.1",
    },
}

READY_RESPONSE_EXAMPLE = {
    "check_type": "readiness",
    "ready": True,
    "status": "ok",
    "summary": "All configured capabilities are ready to serve traffic.",
    "app": {
        "name": "SentinelOps",
        "version": "0.3.1",
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
        "version": "0.3.1",
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
    "summary": "Deterministic local evaluation summary for SentinelOps service logic and retrieval quality.",
    "generated_at": "2026-04-04T00:00:00Z",
    "totals": {
        "total_cases": 38,
        "passed_cases": 38,
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
}

app = FastAPI(
    title="SentinelOps",
    version="0.3.1",
    description=(
        "Local incident analysis API with two primary workflows: `/analyze` for pasted log text and "
        "`/investigate` for tool-assisted investigations over local files. Both routes attempt retrieval "
        "from the local knowledge base when the embedding model and retrieval backend are ready."
    ),
)


def _raise_ollama_http_exception(exc: Exception) -> None:
    message = str(exc).strip()
    lowered = message.lower()

    if "upgrade in progress" in lowered:
        detail = (
            "Ollama is installed but not ready to serve requests because an upgrade is still in progress. "
            "Finish or restart Ollama, then try the request again."
        )
    elif "model" in lowered and "not found" in lowered:
        detail = (
            "Ollama is reachable, but a configured model is missing. "
            f"Details: {message}"
        )
    else:
        detail = (
            "Ollama is unavailable or not ready to serve requests. "
            "Ensure the Ollama app or `ollama serve` is running and healthy, then retry."
        )

    raise HTTPException(status_code=503, detail=detail) from exc


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
