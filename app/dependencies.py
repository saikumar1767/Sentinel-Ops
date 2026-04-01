from __future__ import annotations

from functools import lru_cache

from fastapi import Depends

from app.ollama_client import OllamaGateway
from app.services.analyze_service import AnalyzeService
from app.services.investigation_service import InvestigationService
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


def get_analyze_service(
    settings: Settings = Depends(get_settings),
    gateway: OllamaGateway = Depends(get_ollama_gateway),
) -> AnalyzeService:
    return AnalyzeService(settings=settings, gateway=gateway)


def get_investigation_service(
    settings: Settings = Depends(get_settings),
    gateway: OllamaGateway = Depends(get_ollama_gateway),
    tool_registry: ToolRegistry = Depends(get_tool_registry),
) -> InvestigationService:
    return InvestigationService(settings=settings, gateway=gateway, tool_registry=tool_registry)
