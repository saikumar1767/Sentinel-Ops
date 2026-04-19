from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

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
WorkflowStatus = Literal["initialized", "running", "waiting_for_approval", "completed", "failed"]
ApprovalStatus = Literal["not_required", "pending", "approved", "rejected"]
WorkflowStage = Literal[
    "intake",
    "classify_incident",
    "gather_evidence",
    "retrieve_supporting_docs",
    "draft_hypothesis",
    "draft_remediation",
    "awaiting_approval",
    "completed",
    "failed",
]
WorkflowAction = Literal["approve", "reject", "resume"]
DocumentType = Literal[
    "runbook",
    "readme",
    "incident_template",
    "prior_incident",
    "github_issue",
    "troubleshooting_note",
]
ApprovalAction = Literal["approve", "reject", "resume"]
ConsoleIncidentCategory = Literal[
    "workflow",
    "investigation",
    "analysis",
    "approval",
    "resilience",
]
ConsoleEndpoint = Literal["/analyze", "/investigate", "/workflow/investigate"]


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


class WorkflowInvestigateRequest(InvestigateRequest):
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
                    "require_approval_for_remediation": True,
                }
            ]
        },
    )

    thread_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=120,
        description="Optional caller-supplied workflow thread identifier. Omit to let SentinelOps create one.",
    )
    require_approval_for_remediation: bool = Field(
        default=True,
        description="When true, actionable remediation plans pause for approval before the workflow finalizes.",
    )


class WorkflowResumeRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "decision": "approved",
                    "review_notes": "Approved for the on-call team to execute.",
                    "edited_remediation_plan": [],
                },
                {
                    "decision": "rejected",
                    "review_notes": "Use a safer reviewed checklist before making runtime changes.",
                    "edited_remediation_plan": [
                        "Freeze deploys touching the checkout service until the database saturation is verified.",
                        "Page the database owner and confirm a safe rollback or failover path before restarting workers.",
                    ],
                },
            ]
        },
    )

    decision: Literal["approved", "rejected"] = Field(
        description="Human decision used to continue the paused workflow thread."
    )
    review_notes: str | None = Field(
        default=None,
        max_length=600,
        description="Optional reviewer notes recorded in the completed workflow report.",
    )
    edited_remediation_plan: list[str] = Field(
        default_factory=list,
        max_length=8,
        description="Optional reviewed remediation steps. Leave empty to keep the generated checklist unchanged.",
    )

    @field_validator("edited_remediation_plan")
    @classmethod
    def clean_resume_plan(cls, value: list[str]) -> list[str]:
        return _clean_string_list(value)


class WorkflowApproveRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "review_notes": "Approved for the on-call team to execute.",
                    "edited_remediation_plan": [],
                }
            ]
        },
    )

    review_notes: str | None = Field(
        default=None,
        max_length=600,
        description="Optional reviewer notes recorded with the approval decision.",
    )
    edited_remediation_plan: list[str] = Field(
        default_factory=list,
        max_length=8,
        description="Optional reviewed remediation steps. Leave empty to approve the generated checklist as-is.",
    )

    @field_validator("edited_remediation_plan")
    @classmethod
    def clean_approved_plan(cls, value: list[str]) -> list[str]:
        return _clean_string_list(value)


class WorkflowRejectRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "reason": "Use a safer reviewed checklist before making runtime changes.",
                    "edited_remediation_plan": [
                        "Freeze deploys touching the checkout service until the database saturation is verified.",
                        "Page the database owner and confirm a safe rollback or failover path before restarting workers.",
                    ],
                }
            ]
        },
    )

    reason: str = Field(
        min_length=1,
        max_length=600,
        description="Reviewer rationale for rejecting the generated remediation checklist.",
    )
    edited_remediation_plan: list[str] = Field(
        default_factory=list,
        max_length=8,
        description="Optional replacement remediation steps provided by the reviewer.",
    )

    @field_validator("edited_remediation_plan")
    @classmethod
    def clean_rejected_plan(cls, value: list[str]) -> list[str]:
        return _clean_string_list(value)


class WorkflowApprovalRequestInfo(BaseModel):
    type: Literal["approval_required"]
    approval_reason: str | None = None
    incident_type: IncidentType
    severity: Severity
    suspected_root_cause: str
    manager_summary: str
    proposed_remediation_plan: list[str] = Field(default_factory=list, max_length=8)
    source_citations: list[str] = Field(default_factory=list, max_length=8)

    @field_validator("proposed_remediation_plan", "source_citations")
    @classmethod
    def clean_approval_lists(cls, value: list[str]) -> list[str]:
        return _clean_string_list(value)


class WorkflowAuditEvent(BaseModel):
    event_id: str = Field(min_length=1, max_length=120)
    thread_id: str = Field(min_length=1, max_length=120)
    recorded_at: datetime
    action: ApprovalAction
    decision: ApprovalStatus
    review_notes: str | None = Field(default=None, max_length=600)
    edited_remediation_plan: list[str] = Field(default_factory=list, max_length=8)
    status_after: WorkflowStatus
    request_id: str | None = Field(default=None, max_length=120)
    actor_subject: str | None = Field(default=None, max_length=160)
    actor_email: str | None = Field(default=None, max_length=320)
    actor_name: str | None = Field(default=None, max_length=160)
    actor_roles: list[str] = Field(default_factory=list, max_length=12)

    @field_validator("edited_remediation_plan", "actor_roles")
    @classmethod
    def clean_audit_plan(cls, value: list[str]) -> list[str]:
        return _clean_string_list(value)


class WorkflowToolResult(BaseModel):
    name: str = Field(
        description="Stable tool identifier executed while gathering workflow evidence."
    )
    arguments: dict[str, Any] = Field(
        default_factory=dict,
        description="Normalized arguments passed to the tool.",
    )
    ok: bool = Field(
        description="Whether the tool execution completed successfully."
    )
    cached: bool = Field(
        default=False,
        description="Whether the tool output was served from the workflow-local cache.",
    )
    duration_ms: float | None = Field(
        default=None,
        ge=0.0,
        description="Wall-clock execution time for the tool call in milliseconds.",
    )
    payload: dict[str, Any] = Field(
        default_factory=dict,
        description="Tool-specific structured result payload captured for inspection.",
    )


class WorkflowFinalReport(BaseModel):
    incident_type: IncidentType
    severity: Severity
    top_error_lines: list[str] = Field(default_factory=list, max_length=5)
    suspected_root_cause: str = Field(min_length=1)
    remediation_plan: list[str] = Field(default_factory=list, max_length=5)
    engineer_summary: str = Field(min_length=1)
    manager_summary: str = Field(min_length=1)
    retrieved_evidence: list[str] = Field(default_factory=list, max_length=5)
    source_citations: list[str] = Field(default_factory=list, max_length=8)
    retrieval_status: RetrievalStatus = "not_used"
    approval_status: ApprovalStatus = "not_required"
    approval_notes: str | None = None
    confidence: float = Field(ge=0.0, le=1.0)

    @field_validator(
        "top_error_lines",
        "remediation_plan",
        "retrieved_evidence",
        "source_citations",
    )
    @classmethod
    def clean_final_report_lists(cls, value: list[str]) -> list[str]:
        return _clean_string_list(value)


class WorkflowThreadResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "thread_id": "workflow-7f1ac5f14f4d470ab8eb52885c32416a",
                "request_id": "09f4059d5f2140f28ef2857d05166d45",
                "status": "waiting_for_approval",
                "current_stage": "awaiting_approval",
                "current_step": "approval_node",
                "available_actions": ["approve", "reject", "resume"],
                "checkpoint_id": "1f130700-a35d-6f0c-8006-49d8f1e2aa61",
                "checkpoint_created_at": "2026-04-04T00:00:00Z",
                "input_summary": "Investigate this incident using the failing run and the previous healthy run. | candidate_logs=2",
                "incident_type": "database",
                "severity": "high",
                "suspected_root_cause": "Connection pool exhaustion on primary-postgres is causing repeated database timeouts and stalled checkout requests.",
                "remediation_plan": [
                    "Confirm database reachability and server-side saturation on primary-postgres.",
                    "Reduce caller concurrency or recycle unhealthy workers to relieve pool pressure.",
                ],
                "top_error_lines": [
                    "1: 2026-03-31 09:10:22 ERROR database connection timeout after 30 seconds"
                ],
                "engineer_summary": None,
                "manager_summary": "The current database run is failing due to connection timeouts and pool exhaustion, while the previous run was healthy.",
                "retrieved_evidence": [
                    "Database timeout incidents usually include connection pool exhaustion or long-running postgres transactions."
                ],
                "source_citations": [
                    "read_log_file:data/logs/database-current.log",
                    "data/knowledge/runbooks/database-timeout-runbook.md#Symptoms",
                ],
                "confidence": 0.92,
                "approval_required": True,
                "approval_status": "pending",
                "approval_reason": "High-impact remediation should be reviewed before anyone executes the checklist.",
                "approval_notes": None,
                "approval_request": {
                    "type": "approval_required",
                    "approval_reason": "High-impact remediation should be reviewed before anyone executes the checklist.",
                    "incident_type": "database",
                    "severity": "high",
                    "suspected_root_cause": "Connection pool exhaustion on primary-postgres is causing repeated database timeouts and stalled checkout requests.",
                    "manager_summary": "The current database run is failing due to connection timeouts and pool exhaustion, while the previous run was healthy.",
                    "proposed_remediation_plan": [
                        "Confirm database reachability and server-side saturation on primary-postgres.",
                        "Reduce caller concurrency or recycle unhealthy workers to relieve pool pressure.",
                    ],
                    "source_citations": [
                        "read_log_file:data/logs/database-current.log",
                        "data/knowledge/runbooks/database-timeout-runbook.md#Symptoms",
                    ],
                },
                "retrieval_status": "used",
                "tool_results": [
                    {
                        "name": "read_log_file",
                        "arguments": {
                            "path": "data/logs/database-current.log",
                        },
                        "ok": True,
                        "cached": False,
                        "payload": {
                            "tool": "read_log_file",
                            "ok": True,
                            "path": "data/logs/database-current.log",
                        },
                    }
                ],
                "retrieved_chunks": [],
                "final_report": None,
                "errors": [],
            }
        }
    )

    thread_id: str = Field(
        description="Stable workflow thread identifier returned when the investigation started."
    )
    request_id: str = Field(
        description="Request identifier for the workflow run that created this thread."
    )
    status: WorkflowStatus = Field(
        description="High-level lifecycle state of the workflow thread."
    )
    current_stage: WorkflowStage = Field(
        description="Stable client-facing workflow stage for UI logic and orchestration state displays."
    )
    current_step: str = Field(
        description="Internal workflow node name for debugging. Prefer current_stage for client behavior."
    )
    available_actions: list[WorkflowAction] = Field(
        default_factory=list,
        description="Client actions currently allowed for this thread.",
    )
    checkpoint_id: str | None = Field(
        default=None,
        description="Opaque identifier for the current persisted workflow checkpoint.",
    )
    checkpoint_created_at: datetime | None = Field(
        default=None,
        description="Timestamp of the current persisted workflow checkpoint.",
    )
    input_summary: str | None = Field(
        default=None,
        description="Short summary of the original investigation request.",
    )
    incident_type: IncidentType | None = None
    severity: Severity | None = None
    suspected_root_cause: str | None = None
    remediation_plan: list[str] = Field(default_factory=list, max_length=5)
    top_error_lines: list[str] = Field(default_factory=list, max_length=5)
    engineer_summary: str | None = None
    manager_summary: str | None = None
    retrieved_evidence: list[str] = Field(default_factory=list, max_length=5)
    source_citations: list[str] = Field(default_factory=list, max_length=8)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    approval_required: bool = False
    approval_status: ApprovalStatus = "not_required"
    approval_reason: str | None = None
    approval_notes: str | None = None
    approval_request: WorkflowApprovalRequestInfo | None = Field(
        default=None,
        description="Structured approval prompt shown when the workflow is paused for human review.",
    )
    audit_trail: list[WorkflowAuditEvent] = Field(
        default_factory=list,
        description="Recorded approval and resume events for this workflow thread.",
    )
    retrieval_status: RetrievalStatus = "not_used"
    tool_results: list[WorkflowToolResult] = Field(
        default_factory=list,
        description="Structured tool executions captured while gathering workflow evidence.",
    )
    retrieved_chunks: list[RetrievalHit] = Field(
        default_factory=list,
        description="Retrieved supporting knowledge chunks attached to the workflow state.",
    )
    final_report: WorkflowFinalReport | None = Field(
        default=None,
        description="Final workflow report returned when the thread completes.",
    )
    errors: list[str] = Field(
        default_factory=list,
        description="Accumulated workflow execution errors, if any.",
    )

    @field_validator(
        "remediation_plan",
        "top_error_lines",
        "retrieved_evidence",
        "source_citations",
        "errors",
    )
    @classmethod
    def clean_thread_lists(cls, value: list[str]) -> list[str]:
        return _clean_string_list(value)


class ProblemDetailResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "type": "urn:sentinelops:problem:workflow-thread-not-found",
                "title": "Workflow thread not found",
                "status": 404,
                "detail": "Workflow thread 'workflow-missing' was not found.",
                "instance": "/workflow/workflow-missing",
                "code": "workflow_thread_not_found",
                "thread_id": "workflow-missing",
            }
        }
    )

    type: str = Field(
        description="URI that identifies the problem type.",
    )
    title: str = Field(
        description="Short, human-readable summary of the problem."
    )
    status: int = Field(
        ge=400,
        le=599,
        description="HTTP status code associated with the problem.",
    )
    detail: str = Field(
        description="Human-readable explanation specific to this occurrence of the problem."
    )
    instance: str | None = Field(
        default=None,
        description="Request path for the failing operation.",
    )
    code: str = Field(
        description="Stable machine-readable application error code."
    )
    thread_id: str | None = Field(
        default=None,
        description="Workflow thread identifier when the problem is associated with a specific thread.",
    )


class WorkflowThreadListItem(BaseModel):
    thread_id: str = Field(min_length=1, max_length=120)
    request_id: str = Field(min_length=1, max_length=120)
    status: WorkflowStatus
    current_stage: WorkflowStage
    current_step: str = Field(min_length=1, max_length=120)
    incident_type: IncidentType | None = None
    severity: Severity | None = None
    checkpoint_id: str | None = Field(default=None, max_length=120)
    approval_required: bool = False
    approval_status: ApprovalStatus = "not_required"
    input_summary: str | None = Field(default=None, max_length=600)
    manager_summary: str | None = Field(default=None, max_length=1200)
    engineer_summary: str | None = Field(default=None, max_length=1200)
    actor_subject: str | None = Field(default=None, max_length=160)
    actor_email: str | None = Field(default=None, max_length=320)
    actor_name: str | None = Field(default=None, max_length=160)
    actor_roles: list[str] = Field(default_factory=list, max_length=12)
    created_at: datetime
    updated_at: datetime

    @field_validator("actor_roles")
    @classmethod
    def clean_actor_roles(cls, value: list[str]) -> list[str]:
        return _clean_string_list(value)


class WorkflowThreadListResponse(BaseModel):
    total_threads: int = Field(ge=0)
    threads: list[WorkflowThreadListItem] = Field(default_factory=list)


class WorkflowAuditResponse(BaseModel):
    thread_id: str = Field(min_length=1, max_length=120)
    total_events: int = Field(ge=0)
    events: list[WorkflowAuditEvent] = Field(default_factory=list)


class CurrentUserResponse(BaseModel):
    subject: str = Field(min_length=1, max_length=160)
    email: str | None = Field(default=None, max_length=320)
    name: str | None = Field(default=None, max_length=160)
    roles: list[str] = Field(default_factory=list, max_length=12)
    auth_mode: Literal["disabled", "api_key", "oidc"]

    @field_validator("roles")
    @classmethod
    def clean_roles(cls, value: list[str]) -> list[str]:
        return _clean_string_list(value)


class IncidentExpectation(BaseModel):
    incident_type: IncidentType | None = None
    severity: Severity | None = None
    retrieval_status: RetrievalStatus | None = None
    workflow_status: WorkflowStatus | None = None
    approval_status: ApprovalStatus | None = None
    citation_keywords: list[str] = Field(default_factory=list, max_length=8)
    evidence_keywords: list[str] = Field(default_factory=list, max_length=8)
    notes: list[str] = Field(default_factory=list, max_length=8)

    @field_validator("citation_keywords", "evidence_keywords", "notes")
    @classmethod
    def clean_incident_expectation_lists(cls, value: list[str]) -> list[str]:
        return _clean_string_list(value)


class IncidentProfileResponse(BaseModel):
    incident_id: str = Field(min_length=1, max_length=120)
    recommended_order: int = Field(ge=1, le=20)
    title: str = Field(min_length=1, max_length=120)
    headline: str = Field(min_length=1, max_length=180)
    category: ConsoleIncidentCategory
    endpoint: ConsoleEndpoint
    description: str = Field(min_length=1, max_length=800)
    estimated_run_seconds: int = Field(ge=15, le=240)
    artifact_paths: list[str] = Field(default_factory=list, max_length=6)
    request_body: dict[str, Any] = Field(default_factory=dict)
    expected_outcome: IncidentExpectation
    operator_steps: list[str] = Field(default_factory=list, max_length=8)

    @field_validator("artifact_paths", "operator_steps")
    @classmethod
    def clean_incident_profile_lists(cls, value: list[str]) -> list[str]:
        return _clean_string_list(value)


class IncidentLibraryResponse(BaseModel):
    incident_count: int = Field(ge=0)
    incidents: list[IncidentProfileResponse] = Field(default_factory=list)


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


class ConsoleTimelineEntry(BaseModel):
    entry_id: str = Field(min_length=1, max_length=180)
    source: Literal["runtime", "reference"]
    created_at: datetime
    incident_type: IncidentType
    severity: Severity
    manager_summary: str
    suspected_root_cause: str
    retrieval_status: RetrievalStatus = "not_used"
    confidence: float = Field(ge=0.0, le=1.0)
    source_citations: list[str] = Field(default_factory=list, max_length=8)
    candidate_log_paths: list[str] = Field(default_factory=list, max_length=6)

    @field_validator("source_citations", "candidate_log_paths")
    @classmethod
    def clean_console_timeline_lists(cls, value: list[str]) -> list[str]:
        return _clean_string_list(value)


class ConsoleTimelineResponse(BaseModel):
    total_entries: int = Field(ge=0)
    entries: list[ConsoleTimelineEntry] = Field(default_factory=list)


class ConsoleOverviewResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "generated_at": "2026-04-07T00:00:00Z",
                "launch_command": "powershell -ExecutionPolicy Bypass -File scripts/start_sentinelops.ps1",
                "console_url": "http://127.0.0.1:8000/console",
                "incident_count": 5,
                "timeline_entry_count": 12,
                "library_categories": [
                    "workflow",
                    "investigation",
                    "approval",
                    "resilience",
                    "analysis",
                ],
                "eval_total_cases": 54,
                "overall_pass_rate": 1.0,
                "analyze_pass_rate": 1.0,
                "investigate_pass_rate": 1.0,
                "rag_pass_rate": 1.0,
                "workflow_pass_rate": 1.0,
            }
        }
    )

    generated_at: datetime
    launch_command: str
    console_url: str
    incident_count: int = Field(ge=0)
    timeline_entry_count: int = Field(ge=0)
    library_categories: list[ConsoleIncidentCategory] = Field(default_factory=list)
    eval_total_cases: int = Field(ge=0)
    overall_pass_rate: float = Field(ge=0.0, le=1.0)
    analyze_pass_rate: float = Field(ge=0.0, le=1.0)
    investigate_pass_rate: float = Field(ge=0.0, le=1.0)
    rag_pass_rate: float = Field(ge=0.0, le=1.0)
    workflow_pass_rate: float = Field(ge=0.0, le=1.0)


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
                    "version": "0.6.0",
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
                "scope": "traffic",
                "ready": True,
                "traffic_ready": True,
                "strict_ready": False,
                "status": "degraded",
                "summary": "Core incident analysis traffic is ready, but one or more optional capabilities are degraded.",
                "app": {
                    "name": "SentinelOps",
                    "version": "0.6.0",
                },
                "dependencies": {
                    "ollama": {
                        "status": "degraded",
                        "detail": "Ollama is reachable but some configured models are missing: embedding_model=nomic-embed-text.",
                        "metadata": {
                            "endpoint": "http://localhost:11434/api/tags",
                            "analyze_model": "mistral:7b-instruct",
                            "investigate_model": "mistral:7b-instruct",
                            "embedding_model": "nomic-embed-text",
                        },
                    },
                    "knowledge_store": {
                        "status": "unavailable",
                        "detail": "Knowledge retrieval is unavailable because the configured embedding model is not installed in Ollama.",
                        "metadata": {
                            "backend": "simple",
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
    scope: Literal["traffic", "strict"] = "traffic"
    ready: bool
    traffic_ready: bool
    strict_ready: bool
    status: Literal["ok", "degraded", "unavailable"]
    summary: str
    app: HealthAppInfo
    dependencies: dict[str, HealthDependency]
    capabilities: dict[str, HealthDependency] = Field(default_factory=dict)


class MetricsRequestTotals(BaseModel):
    total_requests: int = Field(ge=0)
    error_requests: int = Field(ge=0)
    average_latency_ms: float = Field(ge=0.0)


class MetricsRouteUsage(BaseModel):
    method: str
    path: str
    request_count: int = Field(ge=0)
    error_count: int = Field(ge=0)
    average_latency_ms: float = Field(ge=0.0)
    p95_latency_ms: float = Field(ge=0.0)
    max_latency_ms: float = Field(ge=0.0)
    last_status_code: int | None = Field(default=None, ge=100, le=599)


class MetricsModelUsage(BaseModel):
    operation: Literal["chat", "embed"]
    model: str
    call_count: int = Field(ge=0)
    cache_hit_count: int = Field(ge=0)
    retry_count: int = Field(ge=0)
    failure_count: int = Field(ge=0)
    average_latency_ms: float = Field(ge=0.0)
    p95_latency_ms: float = Field(ge=0.0)
    max_latency_ms: float = Field(ge=0.0)
    prompt_tokens: int = Field(ge=0)
    completion_tokens: int = Field(ge=0)
    total_tokens: int = Field(ge=0)
    estimated_cost_usd: float = Field(ge=0.0)


class MetricsCacheUsage(BaseModel):
    cache_name: str
    hit_count: int = Field(ge=0)
    miss_count: int = Field(ge=0)
    set_count: int = Field(ge=0)
    eviction_count: int = Field(ge=0)
    expiration_count: int = Field(ge=0)
    current_size: int = Field(ge=0)
    max_size: int = Field(ge=0)


class MetricsResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "generated_at": "2026-04-06T00:00:00Z",
                "uptime_seconds": 132.441,
                "app": {
                    "name": "SentinelOps",
                    "version": "0.6.0",
                },
                "requests": {
                    "total_requests": 12,
                    "error_requests": 1,
                    "average_latency_ms": 84.233,
                },
                "routes": [
                    {
                        "method": "POST",
                        "path": "/analyze",
                        "request_count": 4,
                        "error_count": 0,
                        "average_latency_ms": 72.5,
                        "p95_latency_ms": 95.1,
                        "max_latency_ms": 95.1,
                        "last_status_code": 200,
                    }
                ],
                "model_usage": [
                    {
                        "operation": "chat",
                        "model": "mistral:7b-instruct",
                        "call_count": 6,
                        "cache_hit_count": 2,
                        "retry_count": 1,
                        "failure_count": 0,
                        "average_latency_ms": 248.331,
                        "p95_latency_ms": 402.118,
                        "max_latency_ms": 402.118,
                        "prompt_tokens": 1480,
                        "completion_tokens": 524,
                        "total_tokens": 2004,
                        "estimated_cost_usd": 0.0,
                    }
                ],
                "caches": [
                    {
                        "cache_name": "ollama_chat",
                        "hit_count": 2,
                        "miss_count": 4,
                        "set_count": 4,
                        "eviction_count": 0,
                        "expiration_count": 0,
                        "current_size": 4,
                        "max_size": 256,
                    }
                ],
            }
        }
    )

    generated_at: datetime
    uptime_seconds: float = Field(ge=0.0)
    app: HealthAppInfo
    requests: MetricsRequestTotals
    routes: list[MetricsRouteUsage] = Field(default_factory=list)
    model_usage: list[MetricsModelUsage] = Field(default_factory=list)
    caches: list[MetricsCacheUsage] = Field(default_factory=list)


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


class WorkflowEvalSummary(BaseModel):
    total_cases: int = Field(ge=0)
    passed_cases: int = Field(ge=0)
    failed_cases: int = Field(ge=0)
    pass_rate: float = Field(ge=0.0, le=1.0)
    waiting_for_approval_rate: float = Field(ge=0.0, le=1.0)
    completed_rate: float = Field(ge=0.0, le=1.0)
    approval_required_rate: float = Field(ge=0.0, le=1.0)
    approved_completion_count: int = Field(ge=0)
    rejected_completion_count: int = Field(ge=0)
    average_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    average_confidence_by_incident_type: dict[str, float] = Field(default_factory=dict)
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
                "summary": "Deterministic local evaluation summary for SentinelOps service logic, retrieval quality, and workflow durability.",
                "generated_at": "2026-04-04T00:00:00Z",
                "totals": {
                    "total_cases": 48,
                    "passed_cases": 48,
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
                "workflow": {
                    "total_cases": 10,
                    "passed_cases": 10,
                    "failed_cases": 0,
                    "pass_rate": 1.0,
                    "waiting_for_approval_rate": 0.2,
                    "completed_rate": 0.8,
                    "approval_required_rate": 0.8,
                    "approved_completion_count": 4,
                    "rejected_completion_count": 2,
                    "average_confidence": 0.88,
                    "average_confidence_by_incident_type": {
                        "database": 0.92,
                        "network": 0.86,
                    },
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
    workflow: WorkflowEvalSummary
