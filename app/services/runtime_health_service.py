from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import requests

from app.rag.chroma_runtime import ChromaRuntimeManager
from app.schemas import (
    HealthAppInfo,
    HealthDependency,
    LivenessResponse,
    ReadinessResponse,
)
from app.settings import Settings


@dataclass
class OllamaInspection:
    dependency: HealthDependency
    analyze_ready: bool
    investigate_ready: bool
    embedding_ready: bool


class RuntimeHealthService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.chroma_runtime = ChromaRuntimeManager(settings)

    def health_report(self) -> LivenessResponse:
        return LivenessResponse(
            check_type="liveness",
            alive=True,
            status="ok",
            summary="API process is alive.",
            app=HealthAppInfo(
                name=self.settings.app_name,
                version=self.settings.app_version,
            ),
        )

    def readiness_report(self, *, scope: str = "traffic") -> ReadinessResponse:
        dependencies, capabilities = self._build_snapshot()
        traffic_ready = self._traffic_ready(capabilities)
        strict_ready = self._strict_ready(capabilities)
        ready = strict_ready if scope == "strict" else traffic_ready
        if traffic_ready and strict_ready:
            status = "ok"
        elif traffic_ready:
            status = "degraded"
        else:
            status = "unavailable"
        return ReadinessResponse(
            check_type="readiness",
            scope=scope,  # type: ignore[arg-type]
            ready=ready,
            traffic_ready=traffic_ready,
            strict_ready=strict_ready,
            status=status,
            summary=self._summary_for_scope(
                scope=scope,
                traffic_ready=traffic_ready,
                strict_ready=strict_ready,
            ),
            app=HealthAppInfo(
                name=self.settings.app_name,
                version=self.settings.app_version,
            ),
            dependencies=dependencies,
            capabilities=capabilities,
        )

    def _build_snapshot(self) -> tuple[dict[str, HealthDependency], dict[str, HealthDependency]]:
        ollama = self._inspect_ollama()
        chroma = self._chroma_status()
        knowledge_store = self._knowledge_store_status(ollama=ollama, chroma=chroma)
        dependencies = {
            "ollama": ollama.dependency,
            "knowledge_store": knowledge_store,
            "chroma": chroma,
        }
        capabilities = self._capability_statuses(
            ollama=ollama,
            knowledge_store=knowledge_store,
        )
        return dependencies, capabilities

    def is_ready(self, report: ReadinessResponse | None = None, *, strict: bool = False) -> bool:
        report = report or self.readiness_report(scope="strict" if strict else "traffic")
        return report.strict_ready if strict else report.traffic_ready

    def _inspect_ollama(self) -> OllamaInspection:
        endpoint = f"{self.settings.ollama_host.rstrip('/')}/api/tags"
        try:
            response = requests.get(endpoint, timeout=2)
            response.raise_for_status()
            payload = response.json()
            models = payload.get("models", [])
            installed_models = self._extract_installed_models(models)
            analyze_ready = self._model_is_available(
                self.settings.analyze_model,
                installed_models,
            )
            investigate_ready = self._model_is_available(
                self.settings.investigate_model,
                installed_models,
            )
            embedding_ready = self._model_is_available(
                self.settings.embedding_model,
                installed_models,
            )
            missing_models: list[str] = []
            if not analyze_ready:
                missing_models.append(f"analyze_model={self.settings.analyze_model}")
            if not investigate_ready:
                missing_models.append(f"investigate_model={self.settings.investigate_model}")
            if not embedding_ready:
                missing_models.append(f"embedding_model={self.settings.embedding_model}")

            status = "ok" if not missing_models else "degraded"
            detail = (
                "Ollama is reachable and all configured models are installed."
                if not missing_models
                else "Ollama is reachable but some configured models are missing: "
                + ", ".join(missing_models)
                + "."
            )
            dependency = HealthDependency(
                status=status,
                detail=detail,
                metadata={
                    "endpoint": endpoint,
                    "models": len(models),
                    "analyze_model": self.settings.analyze_model,
                    "investigate_model": self.settings.investigate_model,
                    "embedding_model": self.settings.embedding_model,
                    "analyze_model_ready": analyze_ready,
                    "investigate_model_ready": investigate_ready,
                    "embedding_model_ready": embedding_ready,
                },
            )
            return OllamaInspection(
                dependency=dependency,
                analyze_ready=analyze_ready,
                investigate_ready=investigate_ready,
                embedding_ready=embedding_ready,
            )
        except (requests.RequestException, ValueError) as exc:
            dependency = HealthDependency(
                status="unavailable",
                detail="Ollama is not reachable or did not return a valid model registry response.",
                metadata={
                    "endpoint": endpoint,
                    "analyze_model": self.settings.analyze_model,
                    "investigate_model": self.settings.investigate_model,
                    "embedding_model": self.settings.embedding_model,
                    "analyze_model_ready": False,
                    "investigate_model_ready": False,
                    "embedding_model_ready": False,
                    "error_type": exc.__class__.__name__,
                },
            )
            return OllamaInspection(
                dependency=dependency,
                analyze_ready=False,
                investigate_ready=False,
                embedding_ready=False,
            )

    def _knowledge_store_status(
        self,
        *,
        ollama: OllamaInspection,
        chroma: HealthDependency,
    ) -> HealthDependency:
        backend = self.settings.knowledge_store_backend
        metadata: dict[str, str | int | bool] = {
            "backend": backend,
            "collection": self.settings.knowledge_collection_name,
            "embedding_model": self.settings.embedding_model,
            "embedding_model_ready": ollama.embedding_ready,
        }

        if ollama.dependency.status == "unavailable":
            return HealthDependency(
                status="unavailable",
                detail="Knowledge retrieval is unavailable because Ollama is not reachable.",
                metadata=metadata,
            )

        if not ollama.embedding_ready:
            return HealthDependency(
                status="unavailable",
                detail=(
                    "Knowledge retrieval is unavailable because the configured embedding model "
                    f"'{self.settings.embedding_model}' is not installed in Ollama."
                ),
                metadata=metadata,
            )

        if backend == "simple":
            index_path = self.settings.knowledge_index_path
            parent = index_path.parent
            writable = parent.exists() or self._can_create(parent)
            return HealthDependency(
                status="ok" if writable else "unavailable",
                detail="Using simple local knowledge index."
                if writable
                else "Simple knowledge index path is not writable.",
                metadata={
                    **metadata,
                    "index_path": str(index_path),
                },
            )

        return HealthDependency(
            status=chroma.status,
            detail=(
                "Using Chroma as the retrieval backend."
                if chroma.status == "ok"
                else chroma.detail
            ),
            metadata={
                **metadata,
                "client_mode": self.settings.chroma_client_mode,
                **chroma.metadata,
            },
        )

    def _chroma_status(self) -> HealthDependency:
        if self.settings.knowledge_store_backend != "chroma":
            return HealthDependency(
                status="disabled",
                detail="Chroma is disabled because the simple backend is configured.",
                metadata={"backend": self.settings.knowledge_store_backend},
            )

        detail = "Chroma is reachable."
        status = "ok" if self.chroma_runtime.is_ready() else "unavailable"
        if status != "ok":
            detail = (
                "Chroma is not reachable. Start it externally with "
                "scripts/start_chroma_wsl.ps1 or enable auto-start explicitly."
            )

        metadata: dict[str, str | int | bool] = {
            "client_mode": self.settings.chroma_client_mode,
            "endpoint": self.chroma_runtime.heartbeat_url,
            "auto_start": self.settings.chroma_auto_start,
        }
        if self.settings.chroma_client_mode == "persistent":
            metadata["data_path"] = str(self.settings.chroma_path)
        else:
            metadata["wsl_distro"] = self.settings.chroma_wsl_distro
            metadata["wsl_data_dir"] = self.settings.chroma_wsl_data_dir

        return HealthDependency(status=status, detail=detail, metadata=metadata)

    def _capability_statuses(
        self,
        *,
        ollama: OllamaInspection,
        knowledge_store: HealthDependency,
    ) -> dict[str, HealthDependency]:
        analyze_capability = self._analyze_capability(ollama, knowledge_store)
        investigate_capability = self._investigate_capability(ollama, knowledge_store)
        knowledge_ready = knowledge_store.status == "ok"
        knowledge_ingest_detail = (
            "Knowledge ingest requires the configured embedding model and retrieval backend to be ready."
            if not knowledge_ready
            else "Knowledge ingest can rebuild the configured retrieval index."
        )
        knowledge_search_detail = (
            "Knowledge search requires the configured embedding model and retrieval backend to be ready."
            if not knowledge_ready
            else "Knowledge search can query the configured retrieval index."
        )
        return {
            "analyze_endpoint": analyze_capability,
            "investigate_endpoint": investigate_capability,
            "knowledge_ingest_endpoint": HealthDependency(
                status="ok" if knowledge_ready else "unavailable",
                detail=knowledge_ingest_detail,
            ),
            "knowledge_search_endpoint": HealthDependency(
                status="ok" if knowledge_ready else "unavailable",
                detail=knowledge_search_detail,
            ),
        }

    @staticmethod
    def _traffic_ready(capabilities: dict[str, HealthDependency]) -> bool:
        required_capabilities = [
            "analyze_endpoint",
            "investigate_endpoint",
        ]
        return all(capabilities[name].status in {"ok", "degraded"} for name in required_capabilities)

    @staticmethod
    def _strict_ready(capabilities: dict[str, HealthDependency]) -> bool:
        required_capabilities = [
            "analyze_endpoint",
            "investigate_endpoint",
            "knowledge_ingest_endpoint",
            "knowledge_search_endpoint",
        ]
        return all(capabilities[name].status == "ok" for name in required_capabilities)

    def _analyze_capability(
        self,
        ollama: OllamaInspection,
        knowledge_store: HealthDependency,
    ) -> HealthDependency:
        if ollama.dependency.status == "unavailable":
            return HealthDependency(
                status="unavailable",
                detail="Analyze is unavailable because Ollama is not reachable.",
            )
        if not ollama.analyze_ready:
            return HealthDependency(
                status="unavailable",
                detail=(
                    "Analyze is unavailable because the configured chat model "
                    f"'{self.settings.analyze_model}' is not installed in Ollama."
                ),
            )
        if knowledge_store.status == "ok":
            return HealthDependency(
                status="ok",
                detail="Analyze can classify log text and attach retrieved evidence from the local knowledge base.",
            )
        return HealthDependency(
            status="degraded",
            detail=(
                "Analyze can still return structured log summaries, but retrieval is unavailable so RAG evidence "
                "will not be attached."
            ),
        )

    def _investigate_capability(
        self,
        ollama: OllamaInspection,
        knowledge_store: HealthDependency,
    ) -> HealthDependency:
        if ollama.dependency.status == "unavailable":
            return HealthDependency(
                status="unavailable",
                detail="Investigate is unavailable because Ollama is not reachable.",
            )
        if not ollama.investigate_ready:
            return HealthDependency(
                status="unavailable",
                detail=(
                    "Investigate is unavailable because the configured chat model "
                    f"'{self.settings.investigate_model}' is not installed in Ollama."
                ),
            )
        if knowledge_store.status == "ok":
            return HealthDependency(
                status="ok",
                detail="Investigate can use safe local tools and attach retrieved knowledge citations in the final report.",
            )
        return HealthDependency(
            status="degraded",
            detail=(
                "Investigate can still use safe local tools, but retrieval is unavailable so knowledge citations "
                "will be missing."
            ),
        )

    @staticmethod
    def _summary_for_scope(
        *,
        scope: str,
        traffic_ready: bool,
        strict_ready: bool,
    ) -> str:
        if traffic_ready and strict_ready:
            return "All configured SentinelOps capabilities are ready to serve traffic."
        if traffic_ready:
            if scope == "strict":
                return "Core traffic is healthy, but one or more optional knowledge capabilities are not fully ready."
            return "Core incident analysis traffic is ready, but one or more optional capabilities are degraded."
        return "Core incident analysis traffic is unavailable because required model capabilities are not ready."

    @staticmethod
    def _extract_installed_models(models: list[dict[str, object]]) -> set[str]:
        installed: set[str] = set()
        for model in models:
            for key in ("name", "model"):
                value = model.get(key)
                if isinstance(value, str) and value.strip():
                    normalized = value.strip()
                    installed.add(normalized)
                    installed.add(normalized.split(":", 1)[0])
        return installed

    @staticmethod
    def _model_is_available(model_name: str, installed_models: set[str]) -> bool:
        normalized = model_name.strip()
        return normalized in installed_models or normalized.split(":", 1)[0] in installed_models

    @staticmethod
    def _can_create(path: Path) -> bool:
        try:
            path.mkdir(parents=True, exist_ok=True)
            return True
        except OSError:
            return False
