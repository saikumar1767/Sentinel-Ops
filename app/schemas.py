from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

ALLOWED_INCIDENT_TYPES = (
    "api",
    "authentication",
    "configuration",
    "database",
    "deployment",
    "disk",
    "memory",
    "network",
    "performance",
    "queue",
    "security",
    "service",
)

ALLOWED_SEVERITIES = ("critical", "high", "medium", "low")

IncidentType = Literal[
    "api",
    "authentication",
    "configuration",
    "database",
    "deployment",
    "disk",
    "memory",
    "network",
    "performance",
    "queue",
    "security",
    "service",
]

Severity = Literal["critical", "high", "medium", "low"]


class AnalyzeRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "log_text": "2026-03-29 09:10:22 ERROR database connection timeout after 30 seconds"
                }
            ]
        },
    )
    log_text: str = Field(min_length=1, max_length=12000)


class AnalyzeModelResponse(BaseModel):
    incident_type: IncidentType = Field(
        description="A short lowercase label for the kind of incident."
    )
    severity: Severity = Field(
        description="One of critical, high, medium, or low."
    )
    summary: str = Field(min_length=1)
    suspected_root_cause: str = Field(min_length=1)
    recommended_action: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)


class AnalyzeResponse(AnalyzeModelResponse):
    top_error_lines: list[str] = Field(min_length=1, max_length=3)


def _clean_string_list(values: list[str]) -> list[str]:
    cleaned: list[str] = []
    for value in values:
        stripped = value.strip()
        if stripped:
            cleaned.append(stripped)
    return cleaned


class InvestigateRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "prompt": "Investigate this incident.",
                    "candidate_log_paths": [
                        "data/logs/database-current.log",
                        "data/logs/database-previous.log",
                    ],
                    "incident_type_hint": "database",
                }
            ]
        },
    )

    prompt: str = Field(min_length=1, max_length=600)
    candidate_log_paths: list[str] = Field(default_factory=list, max_length=6)
    incident_type_hint: IncidentType | None = None

    @field_validator("candidate_log_paths")
    @classmethod
    def normalize_candidate_paths(cls, value: list[str]) -> list[str]:
        deduped: list[str] = []
        seen: set[str] = set()
        for item in value:
            cleaned = item.strip()
            if not cleaned or cleaned in seen:
                continue
            seen.add(cleaned)
            deduped.append(cleaned)
        return deduped


class InvestigateModelResponse(BaseModel):
    incident_type: IncidentType
    severity: Severity
    top_error_lines: list[str] = Field(default_factory=list, max_length=5)
    suspected_root_cause: str = Field(min_length=1)
    next_steps: list[str] = Field(default_factory=list, max_length=5)
    manager_summary: str = Field(min_length=1)
    evidence_used: list[str] = Field(default_factory=list, max_length=6)
    confidence: float = Field(ge=0.0, le=1.0)

    @field_validator("top_error_lines", "next_steps", "evidence_used")
    @classmethod
    def clean_string_lists(cls, value: list[str]) -> list[str]:
        return _clean_string_list(value)


class InvestigateResponse(InvestigateModelResponse):
    top_error_lines: list[str] = Field(min_length=1, max_length=5)
    next_steps: list[str] = Field(min_length=1, max_length=5)
    evidence_used: list[str] = Field(min_length=1, max_length=6)


class SavedIncidentSummary(BaseModel):
    created_at: datetime
    request: str
    candidate_log_paths: list[str] = Field(default_factory=list)
    incident_type: IncidentType
    severity: Severity
    manager_summary: str
    suspected_root_cause: str
    evidence_used: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)


class ReadLogFileArgs(BaseModel):
    path: str = Field(min_length=1, max_length=260)


class GrepErrorPatternArgs(BaseModel):
    path: str = Field(min_length=1, max_length=260)
    pattern: str = Field(min_length=1, max_length=80)
    max_lines: int = Field(default=6, ge=1, le=10)


class CompareTwoLogsArgs(BaseModel):
    path_a: str = Field(min_length=1, max_length=260)
    path_b: str = Field(min_length=1, max_length=260)


class LoadIncidentTemplateArgs(BaseModel):
    incident_type: IncidentType


class ListRecentIncidentsArgs(BaseModel):
    limit: int = Field(default=3, ge=1, le=10)
