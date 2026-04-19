from __future__ import annotations

import json
import os
from pathlib import Path

from typing import Any, Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict
from pydantic_settings.sources import TomlConfigSettingsSource

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config" / "sentinelops.toml"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="SENTINELOPS_",
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = "SentinelOps"
    app_version: str = "0.6.0"
    deployment_mode: Literal["local", "staging", "production"] = "local"
    public_base_url: str | None = None
    log_level: Literal["CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"] = "INFO"
    startup_validate_config: bool = True
    telemetry_enabled: bool = False
    telemetry_service_name: str = "sentinelops-api"
    telemetry_exporter: Literal["none", "console", "otlp"] = "none"
    telemetry_otlp_endpoint: str | None = None
    analyze_model: str = "mistral:7b-instruct"
    investigate_model: str = "mistral:7b-instruct"
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
    workflow_checkpoint_database_url: str | None = None
    audit_db_path: Path = PROJECT_ROOT / "data" / "runtime" / "audit" / "audit.sqlite"
    metadata_database_url: str | None = None
    knowledge_base_dir: Path = PROJECT_ROOT / "data" / "knowledge"
    chroma_path: Path = PROJECT_ROOT / "data" / "chroma"
    knowledge_index_path: Path = PROJECT_ROOT / "data" / "knowledge_index.json"
    incident_library_dir: Path = PROJECT_ROOT / "data" / "incident_library"
    reference_incidents_dir: Path = PROJECT_ROOT / "data" / "reference_incidents"
    knowledge_collection_name: str = "sentinelops_knowledge"
    knowledge_store_backend: Literal["simple", "chroma"] = "simple"
    chroma_client_mode: Literal["http", "persistent"] = "http"
    chroma_host: str = "127.0.0.1"
    chroma_port: int = Field(default=8012, ge=1, le=65535)
    chroma_ssl: bool = False
    chroma_auto_start: bool = False
    chroma_start_timeout_seconds: int = Field(default=90, ge=5, le=180)
    chroma_wsl_distro: str = "Ubuntu"
    chroma_wsl_binary: str = "$HOME/.local/bin/chroma"
    chroma_wsl_data_dir: str = "$HOME/.sentinelops/chroma-data"
    embedding_model: str = "nomic-embed-text"
    model_license_policy: Literal["permissive_only", "custom_reviewed"] = "permissive_only"
    commercially_reviewed_model_prefixes: list[str] = Field(
        default_factory=lambda: ["mistral", "ministral", "nomic-embed-text"]
    )
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
    workflow_recent_threads_limit: int = Field(default=25, ge=1, le=100)

    auth_mode: Literal["disabled", "api_key", "oidc"] = "disabled"
    auth_api_key_header_name: str = "X-API-Key"
    auth_api_key: str | None = None
    auth_bearer_tokens: dict[str, dict[str, Any]] = Field(default_factory=dict)
    auth_oidc_issuer_url: str | None = None
    auth_oidc_jwks_url: str | None = None
    auth_oidc_audience: str | None = None
    auth_role_claim_path: str = "realm_access.roles"
    auth_analyst_roles: list[str] = Field(default_factory=lambda: ["analyst", "approver", "admin"])
    auth_approver_roles: list[str] = Field(default_factory=lambda: ["approver", "admin"])
    auth_admin_roles: list[str] = Field(default_factory=lambda: ["admin"])

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        configured_path = os.getenv("SENTINELOPS_CONFIG_FILE")
        config_path = Path(configured_path) if configured_path else DEFAULT_CONFIG_PATH
        if not config_path.is_absolute():
            config_path = (PROJECT_ROOT / config_path).resolve()
        toml_settings = TomlConfigSettingsSource(settings_cls, toml_file=config_path)
        return (
            init_settings,
            env_settings,
            dotenv_settings,
            file_secret_settings,
            toml_settings,
        )

    @field_validator("allowed_log_roots", mode="before")
    @classmethod
    def parse_allowed_log_roots(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @field_validator(
        "auth_analyst_roles",
        "auth_approver_roles",
        "auth_admin_roles",
        "commercially_reviewed_model_prefixes",
        mode="before",
    )
    @classmethod
    def parse_role_lists(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @field_validator("auth_bearer_tokens", mode="before")
    @classmethod
    def parse_auth_bearer_tokens(cls, value: object) -> object:
        if isinstance(value, str):
            cleaned = value.strip()
            if not cleaned:
                return {}
            return json.loads(cleaned)
        return value

    @field_validator(
        "telemetry_otlp_endpoint",
        "public_base_url",
        "workflow_checkpoint_database_url",
        "metadata_database_url",
        "auth_api_key",
        "auth_oidc_issuer_url",
        "auth_oidc_jwks_url",
        "auth_oidc_audience",
        mode="before",
    )
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

    @property
    def effective_metadata_database_url(self) -> str:
        if self.metadata_database_url:
            return self.metadata_database_url
        return f"sqlite:///{self.audit_db_path.as_posix()}"

    @property
    def effective_workflow_checkpoint_database_url(self) -> str:
        if self.workflow_checkpoint_database_url:
            return self.workflow_checkpoint_database_url
        if self.metadata_database_url:
            return self.metadata_database_url
        return f"sqlite:///{self.workflow_checkpoint_path.as_posix()}"

    @property
    def effective_auth_oidc_jwks_url(self) -> str | None:
        if self.auth_oidc_jwks_url:
            return self.auth_oidc_jwks_url
        if not self.auth_oidc_issuer_url:
            return None
        return self.auth_oidc_issuer_url.rstrip("/") + "/protocol/openid-connect/certs"

    def model_is_allowed_by_policy(self, model_name: str) -> bool:
        if self.model_license_policy != "permissive_only":
            return True

        normalized = model_name.strip().lower()
        return any(
            normalized == prefix.strip().lower() or normalized.startswith(prefix.strip().lower() + ":")
            for prefix in self.commercially_reviewed_model_prefixes
            if prefix.strip()
        )
