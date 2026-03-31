from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

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
    log_text: str


class AnalyzeModelResponse(BaseModel):
    incident_type: IncidentType = Field(
        description="A short lowercase label for the kind of incident."
    )
    severity: Severity = Field(
        description="One of critical, high, medium, or low."
    )
    summary: str
    suspected_root_cause: str
    recommended_action: str
    confidence: float = Field(ge=0.0, le=1.0)


class AnalyzeResponse(AnalyzeModelResponse):
    top_error_lines: list[str] = Field(min_length=1, max_length=3)
