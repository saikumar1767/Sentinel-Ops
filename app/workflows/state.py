from __future__ import annotations

from typing import Any, Literal

from typing_extensions import TypedDict

from app.schemas import IncidentType, RetrievalStatus, Severity

WorkflowStatus = Literal[
    "initialized",
    "running",
    "waiting_for_approval",
    "completed",
    "failed",
]
ApprovalStatus = Literal["not_required", "pending", "approved", "rejected"]


class SentinelWorkflowState(TypedDict, total=False):
    request_id: str
    prompt: str
    input_summary: str
    candidate_log_paths: list[str]
    incident_type_hint: IncidentType | None
    require_approval_for_remediation: bool

    status: WorkflowStatus
    current_step: str
    incident_type: IncidentType
    severity: Severity

    baseline_records: list[dict[str, Any]]
    planner_records: list[dict[str, Any]]
    support_records: list[dict[str, Any]]
    tool_results: list[dict[str, Any]]

    retrieved_chunks: list[dict[str, Any]]
    retrieval_status: RetrievalStatus
    root_cause_diagnostics: dict[str, Any]
    draft_model_response: dict[str, Any]
    grounded_response: dict[str, Any]

    suspected_root_cause: str
    remediation_plan: list[str]
    top_error_lines: list[str]
    retrieved_evidence: list[str]
    source_citations: list[str]
    manager_summary: str
    engineer_summary: str
    confidence: float

    approval_required: bool
    approval_status: ApprovalStatus
    approval_reason: str | None
    approval_notes: str | None
    approval_request: dict[str, Any] | None
    audit_trail: list[dict[str, Any]]

    final_report: dict[str, Any] | None
    errors: list[str]
