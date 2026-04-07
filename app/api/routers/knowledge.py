from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from ollama import RequestError, ResponseError
from pydantic import ValidationError

from app.dependencies import get_knowledge_base_service
from app.http_errors import raise_ollama_http_exception
from app.rag.service import KnowledgeBaseService
from app.rag.utils import curate_knowledge_search_hits
from app.schemas import (
    KnowledgeIngestRequest,
    KnowledgeIngestResponse,
    KnowledgeSearchRequest,
    KnowledgeSearchResponse,
    ProblemDetailResponse,
)

logger = logging.getLogger("sentinelops.api.knowledge")
router = APIRouter(tags=["knowledge"])


@router.post(
    "/knowledge/ingest",
    response_model=KnowledgeIngestResponse,
    responses={
        400: {"model": ProblemDetailResponse},
        502: {"model": ProblemDetailResponse},
        503: {"model": ProblemDetailResponse},
    },
    summary="Rebuild the local knowledge index",
)
def ingest_knowledge(
    request: KnowledgeIngestRequest,
    service: KnowledgeBaseService = Depends(get_knowledge_base_service),
) -> KnowledgeIngestResponse:
    if request.reset and not request.confirm_reset:
        raise HTTPException(status_code=400, detail="Destructive reset requires confirm_reset=true.")
    try:
        return service.rebuild_index(reset=request.reset)
    except (RequestError, ResponseError) as exc:
        raise_ollama_http_exception(exc)
    except RuntimeError as exc:
        logger.warning("knowledge ingest unavailable: %s", exc)
        raise HTTPException(status_code=503, detail="Knowledge ingest is unavailable.") from exc
    except Exception as exc:
        logger.exception("knowledge ingest failed", exc_info=exc)
        raise HTTPException(status_code=502, detail="Knowledge ingest failed unexpectedly.") from exc


@router.post(
    "/knowledge/search",
    response_model=KnowledgeSearchResponse,
    responses={
        502: {"model": ProblemDetailResponse},
        503: {"model": ProblemDetailResponse},
    },
    summary="Search the local knowledge base",
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
    except (RequestError, ResponseError) as exc:
        raise_ollama_http_exception(exc)
    except RuntimeError as exc:
        logger.warning("knowledge search unavailable: %s", exc)
        raise HTTPException(status_code=503, detail="Knowledge search is unavailable.") from exc
    except Exception as exc:
        logger.exception("knowledge search failed", exc_info=exc)
        raise HTTPException(status_code=502, detail="Knowledge search failed unexpectedly.") from exc
