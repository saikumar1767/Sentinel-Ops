from __future__ import annotations

from pathlib import Path

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
    analyze_model: str = "llama3.2"
    investigate_model: str = "llama3.2"
    ollama_host: str = "http://localhost:11434"
    ollama_timeout_seconds: int = Field(default=120, ge=10, le=600)

    allowed_log_roots: list[Path] = Field(
        default_factory=lambda: [
            PROJECT_ROOT / "samples",
            PROJECT_ROOT / "data" / "logs",
        ]
    )
    incident_templates_dir: Path = PROJECT_ROOT / "data" / "incident_templates"
    incident_history_dir: Path = PROJECT_ROOT / "data" / "recent_incidents"

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

    @field_validator("allowed_log_roots", mode="after")
    @classmethod
    def resolve_allowed_log_roots(cls, roots: list[Path]) -> list[Path]:
        return [cls._resolve_path(root) for root in roots]

    @field_validator("incident_templates_dir", "incident_history_dir", mode="after")
    @classmethod
    def resolve_directory(cls, path: Path) -> Path:
        return cls._resolve_path(path)

    @staticmethod
    def _resolve_path(path: Path) -> Path:
        return path if path.is_absolute() else (PROJECT_ROOT / path).resolve()
