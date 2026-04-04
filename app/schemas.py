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
RuntimeStatus = Literal["ok", "degraded", "unavailable", "disabled"]
RetrievalStatus = Literal["used", "not_used", "unavailable"]
CheckType = Literal["liveness", "readiness"]
RelevanceLabel = Literal["high", "medium", "low"]
DocumentType = Literal[
    "runbook",
    "readme",
    "incident_template",
    "prior_incident",
    "github_issue",
    "troubleshooting_note",
]


class AnalyzeRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "log_text": (
                        "2026-03-29 09:10:22 ERROR database connection timeout after 30 seconds\n"
                        "2026-03-29 09:10:23 WARN retrying connection attempt 1/3\n"
                        "2026-03-29 09:10:24 ERROR connection pool exhausted on primary-postgres"
                    )
                }
            ]
        },
    )
    log_text: str = Field(
        min_length=1,
        max_length=12000,
        description="Raw log text pasted directly into the request body.",
    )


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
    retrieved_evidence: list[str] = Field(default_factory=list, max_length=5)
    source_citations: list[str] = Field(default_factory=list, max_length=8)
    confidence: float = Field(ge=0.0, le=1.0)

    @field_validator("retrieved_evidence", "source_citations")
    @classmethod
    def clean_analyze_lists(cls, value: list[str]) -> list[str]:
        return _clean_string_list(value)


class AnalyzeResponse(AnalyzeModelResponse):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "incident_type": "database",
                "severity": "high",
                "summary": "Database startup failed after repeated connection timeouts and pool exhaustion symptoms.",
                "suspected_root_cause": (
                    "The service could not obtain healthy database connections from primary-postgres. "
                    "Evidence from log: 2026-03-29 09:10:22 ERROR database connection timeout after 30 seconds; "
                    "2026-03-29 09:10:24 ERROR connection pool exhausted on primary-postgres"
                ),
                "recommended_action": "Validate database reachability, review pool saturation on primary-postgres, and slow or pause callers until connections recover.",
                "retrieved_evidence": [
                    "Database timeout incidents often include connection pool exhaustion or long-running transactions on postgres.",
                    "When retries begin before capacity recovers, startup failures usually reflect real saturation rather than a transient blip.",
                ],
                "retrieval_status": "used",
                "source_citations": [
                    "data/knowledge/runbooks/database-timeout-runbook.md#Symptoms",
                    "data/knowledge/github_issues/db-pool-exhaustion-issue.md#Summary",
                ],
                "top_error_lines": [
                    "2026-03-29 09:10:22 ERROR database connection timeout after 30 seconds",
                    "2026-03-29 09:10:24 ERROR connection pool exhausted on primary-postgres",
                ],
                "confidence": 0.91,
            }
        }
    )
    top_error_lines: list[str] = Field(min_length=1, max_length=3)
    retrieval_status: RetrievalStatus = "not_used"


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
                    "prompt": "Investigate this incident using the failing run and the previous healthy run.",
                    "candidate_log_paths": [
                        "data/logs/database-current.log",
                        "data/logs/database-previous.log",
                    ],
                    "incident_type_hint": "database",
                }
            ]
        },
    )
    prompt: str = Field(
        min_length=1,
        max_length=600,
        description="Natural-language investigation request for the incident workflow.",
    )
    candidate_log_paths: list[str] = Field(
        default_factory=list,
        max_length=6,
        description="Optional relative log paths that the investigation tools may read and compare.",
    )
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
    retrieved_evidence: list[str] = Field(default_factory=list, max_length=5)
    source_citations: list[str] = Field(default_factory=list, max_length=8)
    confidence: float = Field(ge=0.0, le=1.0)

    @field_validator("top_error_lines", "next_steps", "retrieved_evidence", "source_citations")
    @classmethod
    def clean_string_lists(cls, value: list[str]) -> list[str]:
        return _clean_string_list(value)


class InvestigateResponse(InvestigateModelResponse):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "incident_type": "database",
                "severity": "high",
                "top_error_lines": [
                    "1: 2026-03-31 09:10:22 ERROR database connection timeout after 30 seconds",
                    "3: 2026-03-31 09:10:24 ERROR connection pool exhausted on primary-postgres",
                ],
                "suspected_root_cause": "Current logs show primary-postgres saturation and exhausted connection checkout capacity after repeated timeouts.",
                "next_steps": [
                    "Confirm database reachability and server-side saturation on primary-postgres.",
                    "Reduce caller concurrency or recycle unhealthy workers to relieve pool pressure.",
                    "Validate that the previous healthy run and the current failing run differ only in the new saturation symptoms.",
                ],
                "manager_summary": "The current database run is failing due to connection timeouts and pool exhaustion, while the previous run was healthy.",
                "retrieved_evidence": [
                    "Database timeout incidents usually include connection pool exhaustion or long-running postgres transactions.",
                    "Previous healthy runs without timeout lines are a strong signal that the current failure is an active regression rather than a chronic warning.",
                ],
                "retrieval_status": "used",
                "source_citations": [
                    "read_log_file:data/logs/database-current.log",
                    "compare_two_logs:data/logs/database-previous.log->data/logs/database-current.log",
                    "data/knowledge/runbooks/database-timeout-runbook.md#Symptoms",
                ],
                "confidence": 0.93,
            }
        }
    )
    top_error_lines: list[str] = Field(min_length=1, max_length=5)
    next_steps: list[str] = Field(min_length=1, max_length=5)
    source_citations: list[str] = Field(min_length=1, max_length=8)
    retrieval_status: RetrievalStatus = "not_used"


class SavedIncidentSummary(BaseModel):
    created_at: datetime
    request: str
    candidate_log_paths: list[str] = Field(default_factory=list)
    incident_type: IncidentType
    severity: Severity
    manager_summary: str
    suspected_root_cause: str
    source_citations: list[str] = Field(default_factory=list)
    retrieval_status: RetrievalStatus = "not_used"
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


class RetrievalHit(BaseModel):
    chunk_id: str
    document_type: DocumentType
    source_path: str
    citation: str
    snippet: str
    title: str
    section_path: str | None = None
    incident_type: IncidentType | None = None
    similarity_score: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description=(
            "Raw semantic similarity score for this retrieved chunk. `/knowledge/search` may diversify the "
            "final display order, so higher-ranked results are not required to have a higher raw similarity "
            "score than later results."
        ),
    )
    relevance: RelevanceLabel | None = Field(
        default=None,
        description="Human-friendly interpretation of the similarity score for this result.",
    )
    display_rank: int | None = Field(
        default=None,
        ge=1,
        description="1-based display rank for curated knowledge-search results.",
    )


class KnowledgeIngestRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {"reset": False, "confirm_reset": False},
                {"reset": True, "confirm_reset": True},
            ]
        },
    )

    reset: bool = False
    confirm_reset: bool = False


class KnowledgeIngestResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "collection_name": "sentinelops_knowledge",
                "document_count": 36,
                "chunk_count": 90,
                "source_counts": {
                    "runbook": 5,
                    "incident_template": 12,
                    "prior_incident": 4,
                    "readme": 4,
                    "github_issue": 4,
                    "troubleshooting_note": 6,
                },
                "chunk_counts": {
                    "runbook": 9,
                    "incident_template": 12,
                    "prior_incident": 4,
                    "readme": 3,
                    "github_issue": 4,
                    "troubleshooting_note": 4,
                },
                "status": "rebuilt",
            }
        }
    )
    collection_name: str
    document_count: int = Field(ge=0)
    chunk_count: int = Field(ge=0)
    source_counts: dict[str, int] = Field(
        default_factory=dict,
        description="Count of source documents by document type.",
    )
    chunk_counts: dict[str, int] = Field(
        default_factory=dict,
        description="Count of indexed chunks by document type.",
    )
    status: str


class KnowledgeSearchRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "query": "Why did startup fail with database timeout and connection pool exhaustion?",
                    "top_k": 3,
                    "document_types": ["runbook", "github_issue"],
                    "incident_type_hint": "database",
                }
            ]
        },
    )
    query: str = Field(min_length=1, max_length=600)
    top_k: int = Field(default=4, ge=1, le=10)
    document_types: list[DocumentType] = Field(default_factory=list, max_length=6)
    incident_type_hint: IncidentType | None = None

    @field_validator("document_types")
    @classmethod
    def normalize_document_types(cls, value: list[DocumentType]) -> list[DocumentType]:
        deduped: list[DocumentType] = []
        seen: set[DocumentType] = set()
        for item in value:
            if item in seen:
                continue
            seen.add(item)
            deduped.append(item)
        return deduped


class KnowledgeSearchResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "query": "Why did startup fail with database timeout and connection pool exhaustion?",
                "total_results": 3,
                "collection_name": "sentinelops_knowledge",
                "ranking_strategy": "diversified_semantic_search",
                "results": [
                    {
                        "chunk_id": "chunk-database-timeout-runbook-01",
                        "document_type": "runbook",
                        "source_path": "data/knowledge/runbooks/database-timeout-runbook.md",
                        "citation": "data/knowledge/runbooks/database-timeout-runbook.md#Symptoms",
                        "snippet": "Database timeout incidents usually include connection pool exhaustion or long-running postgres transactions.",
                        "title": "Database timeout runbook",
                        "section_path": "Symptoms",
                        "incident_type": "database",
                        "similarity_score": 0.94,
                        "relevance": "high",
                        "display_rank": 1,
                    },
                    {
                        "chunk_id": "chunk-db-pool-exhaustion-issue-01",
                        "document_type": "github_issue",
                        "source_path": "data/knowledge/github_issues/db-pool-exhaustion-issue.md",
                        "citation": "data/knowledge/github_issues/db-pool-exhaustion-issue.md#Summary",
                        "snippet": "After a flash sale, checkout workers logged database connection timeout after 30 seconds and connection pool exhausted on primary-postgres.",
                        "title": "DB pool exhaustion issue",
                        "section_path": "Summary",
                        "incident_type": "database",
                        "similarity_score": 0.89,
                        "relevance": "medium",
                        "display_rank": 2,
                    }
                ],
            }
        }
    )
    query: str
    total_results: int = Field(ge=0)
    collection_name: str
    ranking_strategy: str = Field(
        default="diversified_semantic_search",
        description="How the final result order was chosen for display.",
    )
    results: list[RetrievalHit] = Field(default_factory=list)


class HealthDependency(BaseModel):
    status: RuntimeStatus
    detail: str
    metadata: dict[str, str | int | bool] = Field(default_factory=dict)


class HealthAppInfo(BaseModel):
    name: str
    version: str


class LivenessResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "check_type": "liveness",
                "alive": True,
                "status": "ok",
                "summary": "API process is alive.",
                "app": {
                    "name": "SentinelOps",
                    "version": "0.3.1",
                },
            }
        }
    )
    check_type: Literal["liveness"]
    alive: Literal[True]
    status: Literal["ok"]
    summary: str
    app: HealthAppInfo


class ReadinessResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "check_type": "readiness",
                "ready": False,
                "status": "degraded",
                "summary": "One or more configured capabilities are not ready to serve traffic.",
                "app": {
                    "name": "SentinelOps",
                    "version": "0.3.1",
                },
                "dependencies": {
                    "ollama": {
                        "status": "degraded",
                        "detail": "Ollama is reachable but some configured models are missing: embedding_model=embeddinggemma.",
                        "metadata": {
                            "endpoint": "http://localhost:11434/api/tags",
                            "analyze_model": "llama3.2",
                            "investigate_model": "llama3.2",
                            "embedding_model": "embeddinggemma",
                        },
                    },
                    "knowledge_store": {
                        "status": "unavailable",
                        "detail": "Knowledge retrieval is unavailable because the configured embedding model is not installed in Ollama.",
                        "metadata": {
                            "backend": "chroma",
                            "collection": "sentinelops_knowledge",
                        },
                    },
                    "chroma": {
                        "status": "ok",
                        "detail": "Chroma is reachable.",
                        "metadata": {
                            "endpoint": "http://127.0.0.1:8012/api/v2/heartbeat",
                        },
                    },
                },
                "capabilities": {
                    "analyze_endpoint": {
                        "status": "degraded",
                        "detail": "Analyze can still return structured log summaries, but retrieval is unavailable so RAG evidence will not be attached.",
                        "metadata": {},
                    },
                    "investigate_endpoint": {
                        "status": "degraded",
                        "detail": "Investigate can still use local tools, but retrieval is unavailable so knowledge citations will be missing.",
                        "metadata": {},
                    },
                    "knowledge_ingest_endpoint": {
                        "status": "unavailable",
                        "detail": "Knowledge ingest requires the configured embedding model and retrieval backend to be ready.",
                        "metadata": {},
                    },
                    "knowledge_search_endpoint": {
                        "status": "unavailable",
                        "detail": "Knowledge search requires the configured embedding model and retrieval backend to be ready.",
                        "metadata": {},
                    },
                },
            }
        }
    )
    check_type: Literal["readiness"]
    ready: bool
    status: Literal["ok", "degraded"]
    summary: str
    app: HealthAppInfo
    dependencies: dict[str, HealthDependency]
    capabilities: dict[str, HealthDependency] = Field(default_factory=dict)


class EvalScenarioSummary(BaseModel):
    total_cases: int = Field(ge=0)
    passed_cases: int = Field(ge=0)
    failed_cases: int = Field(ge=0)
    pass_rate: float = Field(ge=0.0, le=1.0)
    average_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    retrieval_used_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    average_confidence_by_incident_type: dict[str, float] = Field(default_factory=dict)
    common_failure_reasons: dict[str, int] = Field(default_factory=dict)


class RagEvalSummary(BaseModel):
    total_cases: int = Field(ge=0)
    passed_cases: int = Field(ge=0)
    failed_cases: int = Field(ge=0)
    pass_rate: float = Field(ge=0.0, le=1.0)
    retrieval_hit_rate: float = Field(ge=0.0, le=1.0)
    average_hits_returned: float = Field(ge=0.0)
    corpus_document_count: int = Field(ge=0)
    corpus_chunk_count: int = Field(ge=0)
    common_failure_reasons: dict[str, int] = Field(default_factory=dict)


class EvalTotals(BaseModel):
    total_cases: int = Field(ge=0)
    passed_cases: int = Field(ge=0)
    failed_cases: int = Field(ge=0)
    overall_pass_rate: float = Field(ge=0.0, le=1.0)


class EvalSummaryResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "mode": "deterministic_local",
                "summary": "Deterministic local evaluation summary for SentinelOps service logic and retrieval quality.",
                "generated_at": "2026-04-04T00:00:00Z",
                "totals": {
                    "total_cases": 38,
                    "passed_cases": 38,
                    "failed_cases": 0,
                    "overall_pass_rate": 1.0,
                },
                "analyze": {
                    "total_cases": 18,
                    "passed_cases": 18,
                    "failed_cases": 0,
                    "pass_rate": 1.0,
                    "average_confidence": 0.88,
                    "retrieval_used_rate": 1.0,
                    "average_confidence_by_incident_type": {
                        "database": 0.91,
                        "network": 0.85,
                    },
                    "common_failure_reasons": {},
                },
                "investigate": {
                    "total_cases": 10,
                    "passed_cases": 10,
                    "failed_cases": 0,
                    "pass_rate": 1.0,
                    "average_confidence": 0.9,
                    "retrieval_used_rate": 1.0,
                    "average_confidence_by_incident_type": {
                        "database": 0.93,
                        "configuration": 0.88,
                    },
                    "common_failure_reasons": {},
                },
                "rag": {
                    "total_cases": 10,
                    "passed_cases": 10,
                    "failed_cases": 0,
                    "pass_rate": 1.0,
                    "retrieval_hit_rate": 1.0,
                    "average_hits_returned": 4.0,
                    "corpus_document_count": 36,
                    "corpus_chunk_count": 90,
                    "common_failure_reasons": {},
                },
            }
        }
    )
    mode: Literal["deterministic_local"]
    summary: str
    generated_at: datetime
    totals: EvalTotals
    analyze: EvalScenarioSummary
    investigate: EvalScenarioSummary
    rag: RagEvalSummary
