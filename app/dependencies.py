from __future__ import annotations

from functools import lru_cache

from fastapi import Depends

from app.ollama_client import OllamaGateway
from app.rag.chunker import MarkdownChunker
from app.rag.loader import KnowledgeDocumentLoader
from app.rag.service import KnowledgeBaseService, OllamaEmbeddingProvider
from app.rag.store_factory import build_knowledge_store
from app.services.analyze_service import AnalyzeService
from app.services.evaluation_service import EvaluationSummaryService
from app.services.investigation_service import InvestigationService
from app.services.runtime_health_service import RuntimeHealthService
from app.settings import Settings
from app.tools.file_tools import FileTools
from app.tools.incident_tools import IncidentTools
from app.tools.tool_registry import ToolRegistry


@lru_cache
def get_settings() -> Settings:
    return Settings()


def get_ollama_gateway(settings: Settings = Depends(get_settings)) -> OllamaGateway:
    return OllamaGateway(settings)


def get_tool_registry(settings: Settings = Depends(get_settings)) -> ToolRegistry:
    file_tools = FileTools(settings)
    incident_tools = IncidentTools(settings)
    return ToolRegistry(file_tools=file_tools, incident_tools=incident_tools, settings=settings)


def get_knowledge_base_service(
    settings: Settings = Depends(get_settings),
    gateway: OllamaGateway = Depends(get_ollama_gateway),
) -> KnowledgeBaseService:
    embedding_provider = OllamaEmbeddingProvider(settings=settings, gateway=gateway)
    loader = KnowledgeDocumentLoader(settings)
    chunker = MarkdownChunker(settings)
    store = build_knowledge_store(settings)
    return KnowledgeBaseService(
        settings=settings,
        embedding_provider=embedding_provider,
        loader=loader,
        chunker=chunker,
        store=store,
    )


def get_runtime_health_service(
    settings: Settings = Depends(get_settings),
) -> RuntimeHealthService:
    return RuntimeHealthService(settings=settings)


def get_evaluation_summary_service(
    settings: Settings = Depends(get_settings),
) -> EvaluationSummaryService:
    return EvaluationSummaryService(settings=settings)


def get_analyze_service(
    settings: Settings = Depends(get_settings),
    gateway: OllamaGateway = Depends(get_ollama_gateway),
    retriever: KnowledgeBaseService = Depends(get_knowledge_base_service),
) -> AnalyzeService:
    return AnalyzeService(settings=settings, gateway=gateway, retriever=retriever)


def get_investigation_service(
    settings: Settings = Depends(get_settings),
    gateway: OllamaGateway = Depends(get_ollama_gateway),
    tool_registry: ToolRegistry = Depends(get_tool_registry),
    retriever: KnowledgeBaseService = Depends(get_knowledge_base_service),
) -> InvestigationService:
    return InvestigationService(
        settings=settings,
        gateway=gateway,
        tool_registry=tool_registry,
        retriever=retriever,
    )
