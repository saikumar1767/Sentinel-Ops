from __future__ import annotations

from pathlib import Path

from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parent.parent

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="SENTINELOPS_",
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = "SentinelOps"
    app_version: str = "0.6.0"
    log_level: Literal["CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"] = "INFO"
    startup_validate_config: bool = True
    telemetry_enabled: bool = False
    telemetry_service_name: str = "sentinelops-api"
    telemetry_exporter: Literal["none", "console", "otlp"] = "none"
    telemetry_otlp_endpoint: str | None = None
    analyze_model: str = "llama3.2"
    investigate_model: str = "llama3.2"
    ollama_host: str = "http://localhost:11434"
    ollama_timeout_seconds: int = Field(default=120, ge=10, le=600)
    ollama_max_retries: int = Field(default=2, ge=0, le=5)
    ollama_retry_backoff_seconds: float = Field(default=0.35, ge=0.0, le=5.0)
    ollama_cache_enabled: bool = True
    ollama_cache_ttl_seconds: int = Field(default=900, ge=0, le=86400)
    ollama_cache_max_entries: int = Field(default=256, ge=1, le=4096)
    analyze_model_cost_per_1k_tokens: float = Field(default=0.0, ge=0.0, le=100.0)
    investigate_model_cost_per_1k_tokens: float = Field(default=0.0, ge=0.0, le=100.0)
    embedding_model_cost_per_1k_tokens: float = Field(default=0.0, ge=0.0, le=100.0)

    allowed_log_roots: list[Path] = Field(
        default_factory=lambda: [
            PROJECT_ROOT / "samples",
            PROJECT_ROOT / "data" / "logs",
        ]
    )
    incident_templates_dir: Path = PROJECT_ROOT / "data" / "incident_templates"
    incident_history_dir: Path = PROJECT_ROOT / "data" / "runtime" / "recent_incidents"
    workflow_checkpoint_path: Path = PROJECT_ROOT / "data" / "runtime" / "workflow" / "checkpoints.sqlite"
    audit_db_path: Path = PROJECT_ROOT / "data" / "runtime" / "audit" / "audit.sqlite"
    knowledge_base_dir: Path = PROJECT_ROOT / "data" / "knowledge"
    chroma_path: Path = PROJECT_ROOT / "data" / "chroma"
    knowledge_index_path: Path = PROJECT_ROOT / "data" / "knowledge_index.json"
    incident_library_dir: Path = PROJECT_ROOT / "data" / "incident_library"
    reference_incidents_dir: Path = PROJECT_ROOT / "data" / "reference_incidents"
    knowledge_collection_name: str = "sentinelops_knowledge"
    knowledge_store_backend: Literal["simple", "chroma"] = "chroma"
    chroma_client_mode: Literal["http", "persistent"] = "http"
    chroma_host: str = "127.0.0.1"
    chroma_port: int = Field(default=8012, ge=1, le=65535)
    chroma_ssl: bool = False
    chroma_auto_start: bool = False
    chroma_start_timeout_seconds: int = Field(default=90, ge=5, le=180)
    chroma_wsl_distro: str = "Ubuntu"
    chroma_wsl_binary: str = "$HOME/.local/bin/chroma"
    chroma_wsl_data_dir: str = "$HOME/.sentinelops/chroma-data"
    embedding_model: str = "embeddinggemma"
    retrieval_top_k: int = Field(default=4, ge=1, le=8)
    retrieval_snippet_chars: int = Field(default=260, ge=80, le=600)
    chunk_target_chars: int = Field(default=900, ge=200, le=2000)
    chunk_overlap_chars: int = Field(default=120, ge=0, le=400)
    knowledge_auto_ingest: bool = True
    embedding_batch_size: int = Field(default=16, ge=1, le=64)
    retrieval_cache_enabled: bool = True
    retrieval_cache_ttl_seconds: int = Field(default=900, ge=0, le=86400)
    retrieval_cache_max_entries: int = Field(default=256, ge=1, le=4096)
    console_timeline_limit: int = Field(default=12, ge=4, le=40)

    max_recent_candidate_logs: int = Field(default=5, ge=1, le=20)
    tool_max_iterations: int = Field(default=4, ge=1, le=8)
    read_log_line_limit: int = Field(default=12, ge=1, le=40)
    grep_max_lines_default: int = Field(default=6, ge=1, le=20)
    compare_difference_limit: int = Field(default=6, ge=1, le=20)
    tool_result_max_chars: int = Field(default=1600, ge=200, le=4000)
    persisted_incident_limit: int = Field(default=100, ge=10, le=500)

    @field_validator("allowed_log_roots", mode="before")
    @classmethod
    def parse_allowed_log_roots(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @field_validator("telemetry_otlp_endpoint", mode="before")
    @classmethod
    def normalize_optional_strings(cls, value: object) -> object:
        if isinstance(value, str):
            cleaned = value.strip()
            return cleaned or None
        return value

    @field_validator("allowed_log_roots", mode="after")
    @classmethod
    def resolve_allowed_log_roots(cls, roots: list[Path]) -> list[Path]:
        return [cls._resolve_path(root) for root in roots]

    @field_validator(
        "incident_templates_dir",
        "incident_history_dir",
        "workflow_checkpoint_path",
        "audit_db_path",
        "knowledge_base_dir",
        "chroma_path",
        "knowledge_index_path",
        "incident_library_dir",
        "reference_incidents_dir",
        mode="after",
    )
    @classmethod
    def resolve_directory(cls, path: Path) -> Path:
        return cls._resolve_path(path)

    @staticmethod
    def _resolve_path(path: Path) -> Path:
        return path if path.is_absolute() else (PROJECT_ROOT / path).resolve()
