from __future__ import annotations

from functools import lru_cache

from fastapi import Depends, HTTPException, Request, status

from app.audit import WorkflowAuditTrail
from app.auth import AuthenticatedUser, AuthenticationService
from app.metadata_store import WorkflowThreadStore
from app.ollama_client import OllamaGateway
from app.rag.chunker import MarkdownChunker
from app.rag.loader import KnowledgeDocumentLoader
from app.rag.service import KnowledgeBaseService, OllamaEmbeddingProvider
from app.rag.store_factory import build_knowledge_store
from app.runtime_metrics import RuntimeMetrics
from app.services.analyze_service import AnalyzeService
from app.services.console_service import ConsoleService
from app.services.evaluation_service import EvaluationSummaryService
from app.services.investigation_service import InvestigationService
from app.services.runtime_health_service import RuntimeHealthService
from app.services.workflow_service import WorkflowService
from app.settings import Settings
from app.tools.file_tools import FileTools
from app.tools.incident_tools import IncidentTools
from app.tools.tool_registry import ToolRegistry


@lru_cache
def get_settings() -> Settings:
    return Settings()


@lru_cache
def get_runtime_metrics() -> RuntimeMetrics:
    return RuntimeMetrics()


@lru_cache
def get_authentication_service() -> AuthenticationService:
    return AuthenticationService(get_settings())


@lru_cache
def get_workflow_audit_trail() -> WorkflowAuditTrail:
    return WorkflowAuditTrail(get_settings())


@lru_cache
def get_workflow_thread_store() -> WorkflowThreadStore:
    return WorkflowThreadStore(get_settings())


@lru_cache
def get_ollama_gateway() -> OllamaGateway:
    return OllamaGateway(get_settings(), metrics=get_runtime_metrics())


@lru_cache
def get_knowledge_base_service() -> KnowledgeBaseService:
    settings = get_settings()
    gateway = get_ollama_gateway()
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


def get_tool_registry(settings: Settings = Depends(get_settings)) -> ToolRegistry:
    file_tools = FileTools(settings)
    incident_tools = IncidentTools(settings)
    return ToolRegistry(file_tools=file_tools, incident_tools=incident_tools, settings=settings)


def get_current_user(
    request: Request,
    auth_service: AuthenticationService = Depends(get_authentication_service),
) -> AuthenticatedUser:
    user = auth_service.authenticate_request(request)
    request.state.current_user = user
    return user


def _forbidden(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail)


def require_analyst_user(
    user: AuthenticatedUser = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> AuthenticatedUser:
    if not user.has_any_role(settings.auth_analyst_roles):
        raise _forbidden("Analyst access is required for this operation.")
    return user


def require_approver_user(
    user: AuthenticatedUser = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> AuthenticatedUser:
    if not user.has_any_role(settings.auth_approver_roles):
        raise _forbidden("Approver access is required for this operation.")
    return user


def require_admin_user(
    user: AuthenticatedUser = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> AuthenticatedUser:
    if not user.has_any_role(settings.auth_admin_roles):
        raise _forbidden("Admin access is required for this operation.")
    return user


def get_runtime_health_service(
    settings: Settings = Depends(get_settings),
) -> RuntimeHealthService:
    return RuntimeHealthService(settings=settings)


def get_evaluation_summary_service(
    settings: Settings = Depends(get_settings),
) -> EvaluationSummaryService:
    return EvaluationSummaryService(settings=settings)


def get_console_service(
    settings: Settings = Depends(get_settings),
    evaluation_service: EvaluationSummaryService = Depends(get_evaluation_summary_service),
) -> ConsoleService:
    return ConsoleService(settings=settings, evaluation_service=evaluation_service)


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


def get_workflow_service(
    settings: Settings = Depends(get_settings),
    gateway: OllamaGateway = Depends(get_ollama_gateway),
    tool_registry: ToolRegistry = Depends(get_tool_registry),
    retriever: KnowledgeBaseService = Depends(get_knowledge_base_service),
    thread_store: WorkflowThreadStore = Depends(get_workflow_thread_store),
):
    service = WorkflowService(
        settings=settings,
        gateway=gateway,
        tool_registry=tool_registry,
        retriever=retriever,
        audit_trail=get_workflow_audit_trail(),
        thread_store=thread_store,
    )
    try:
        yield service
    finally:
        service.close()
