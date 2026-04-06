import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.schemas import (
    ALLOWED_INCIDENT_TYPES,
    ALLOWED_SEVERITIES,
    ApprovalStatus,
    DocumentType,
    IncidentType,
    InvestigateModelResponse,
    RetrievalHit,
    Severity,
)

REQUIRED_RESPONSE_KEYS = {
    "incident_type",
    "severity",
    "summary",
    "suspected_root_cause",
    "recommended_action",
    "retrieved_evidence",
    "retrieval_status",
    "source_citations",
    "top_error_lines",
    "confidence",
}

INVESTIGATION_REQUIRED_RESPONSE_KEYS = {
    "incident_type",
    "severity",
    "top_error_lines",
    "suspected_root_cause",
    "next_steps",
    "manager_summary",
    "retrieved_evidence",
    "retrieval_status",
    "source_citations",
    "confidence",
}

WORKFLOW_REQUIRED_RESPONSE_KEYS = {
    "thread_id",
    "request_id",
    "status",
    "current_step",
    "approval_required",
    "approval_status",
    "tool_results",
    "retrieved_chunks",
    "errors",
}


class EvalCase(BaseModel):
    id: str
    input_log: str
    expected_incident_type: IncidentType
    expected_severity: Severity
    expected_root_cause_keywords: list[str] = Field(min_length=1)


class ToolCallPlan(BaseModel):
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class InvestigationEvalCase(BaseModel):
    id: str
    prompt: str
    candidate_log_paths: list[str] = Field(default_factory=list)
    incident_type_hint: IncidentType | None = None
    tool_rounds: list[list[ToolCallPlan]] = Field(default_factory=list)
    final_response: InvestigateModelResponse
    expected_tools: list[str] = Field(default_factory=list)


class RagEvalCase(BaseModel):
    id: str
    query: str
    top_k: int = Field(default=4, ge=1, le=10)
    document_types: list[DocumentType] = Field(default_factory=list)
    incident_type_hint: IncidentType | None = None
    expected_citation_keywords: list[str] = Field(min_length=1)
    expected_snippet_keywords: list[str] = Field(min_length=1)


class WorkflowEvalCase(BaseModel):
    id: str
    prompt: str
    candidate_log_paths: list[str] = Field(default_factory=list)
    incident_type_hint: IncidentType | None = None
    require_approval_for_remediation: bool = True
    tool_rounds: list[list[ToolCallPlan]] = Field(default_factory=list)
    final_response: InvestigateModelResponse
    post_start_action: Literal["inspect_only", "approve", "reject", "auto_complete"] = "approve"
    review_notes: str | None = None
    edited_remediation_plan: list[str] = Field(default_factory=list)


def eval_cases_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "data" / "eval_cases"


def load_eval_cases(directory: Path | None = None) -> list[EvalCase]:
    case_dir = directory or eval_cases_dir()
    cases: list[EvalCase] = []

    for path in sorted(case_dir.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
        cases.append(EvalCase(**payload))

    return cases


def investigation_eval_cases_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "data" / "tool_eval_cases"


def load_investigation_eval_cases(directory: Path | None = None) -> list[InvestigationEvalCase]:
    case_dir = directory or investigation_eval_cases_dir()
    cases: list[InvestigationEvalCase] = []

    for path in sorted(case_dir.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
        cases.append(InvestigationEvalCase(**payload))

    return cases


def rag_eval_cases_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "data" / "rag_eval_cases"


def load_rag_eval_cases(directory: Path | None = None) -> list[RagEvalCase]:
    case_dir = directory or rag_eval_cases_dir()
    cases: list[RagEvalCase] = []

    for path in sorted(case_dir.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
        cases.append(RagEvalCase(**payload))

    return cases


def load_workflow_eval_cases(directory: Path | None = None) -> list[WorkflowEvalCase]:
    investigation_cases = load_investigation_eval_cases(directory=directory)
    workflow_cases: list[WorkflowEvalCase] = []

    for index, case in enumerate(investigation_cases):
        post_start_action: Literal["inspect_only", "approve", "reject", "auto_complete"]
        require_approval = True
        review_notes: str | None = None
        edited_remediation_plan: list[str] = []

        if index < 2:
            post_start_action = "inspect_only"
            review_notes = "Pending on-call review."
        elif index < 6:
            post_start_action = "approve"
            review_notes = f"Approved workflow eval case {case.id}."
        elif index < 8:
            post_start_action = "reject"
            review_notes = f"Use a safer reviewed checklist for {case.id}."
            edited_remediation_plan = _build_workflow_eval_rejection_plan(case)
        else:
            post_start_action = "auto_complete"
            require_approval = False

        workflow_cases.append(
            WorkflowEvalCase(
                id=f"workflow-{case.id}",
                prompt=case.prompt,
                candidate_log_paths=case.candidate_log_paths,
                incident_type_hint=case.incident_type_hint,
                require_approval_for_remediation=require_approval,
                tool_rounds=case.tool_rounds,
                final_response=case.final_response,
                post_start_action=post_start_action,
                review_notes=review_notes,
                edited_remediation_plan=edited_remediation_plan,
            )
        )

    return workflow_cases


def _build_workflow_eval_rejection_plan(case: InvestigationEvalCase) -> list[str]:
    incident_type = case.final_response.incident_type
    return [
        f"Pause high-risk {incident_type} remediation changes until the owning engineer reviews the evidence.",
        f"Use a safer reviewed checklist for {case.id} before applying operational changes.",
    ]


def score_analysis_response(case: EvalCase, payload: Any) -> list[str]:
    failures: list[str] = []

    if not isinstance(payload, dict):
        return ["response_not_json_object"]

    missing_keys = sorted(REQUIRED_RESPONSE_KEYS - payload.keys())
    if missing_keys:
        return [f"missing_keys:{','.join(missing_keys)}"]

    incident_type = str(payload["incident_type"]).strip().lower()
    if incident_type not in ALLOWED_INCIDENT_TYPES:
        failures.append("incident_type_not_allowed")
    elif incident_type != case.expected_incident_type:
        failures.append("incident_type_mismatch")

    severity = str(payload["severity"]).strip().lower()
    if severity not in ALLOWED_SEVERITIES:
        failures.append("severity_not_allowed")
    elif severity != case.expected_severity:
        failures.append("severity_mismatch")

    top_error_lines = payload["top_error_lines"]
    if not isinstance(top_error_lines, list) or not any(
        isinstance(line, str) and line.strip() for line in top_error_lines
    ):
        failures.append("top_error_lines_empty")

    retrieved_evidence = payload["retrieved_evidence"]
    if not isinstance(retrieved_evidence, list):
        failures.append("retrieved_evidence_not_list")
    elif not any(isinstance(item, str) and item.strip() for item in retrieved_evidence):
        failures.append("retrieved_evidence_empty")

    source_citations = payload["source_citations"]
    if not isinstance(source_citations, list):
        failures.append("source_citations_not_list")
    elif not any(isinstance(item, str) and item.strip() for item in source_citations):
        failures.append("source_citations_empty")

    retrieval_status = str(payload["retrieval_status"]).strip().lower()
    if retrieval_status not in {"used", "not_used", "unavailable"}:
        failures.append("retrieval_status_not_allowed")

    root_cause = str(payload["suspected_root_cause"]).lower()
    if not any(keyword.lower() in root_cause for keyword in case.expected_root_cause_keywords):
        failures.append("root_cause_keyword_mismatch")

    confidence = payload["confidence"]
    if not isinstance(confidence, (int, float)) or not 0.0 <= float(confidence) <= 1.0:
        failures.append("confidence_out_of_range")

    return failures


def score_investigation_response(case: InvestigationEvalCase, payload: Any) -> list[str]:
    failures: list[str] = []

    if not isinstance(payload, dict):
        return ["response_not_json_object"]

    missing_keys = sorted(INVESTIGATION_REQUIRED_RESPONSE_KEYS - payload.keys())
    if missing_keys:
        return [f"missing_keys:{','.join(missing_keys)}"]

    incident_type = str(payload["incident_type"]).strip().lower()
    if incident_type not in ALLOWED_INCIDENT_TYPES:
        failures.append("incident_type_not_allowed")

    severity = str(payload["severity"]).strip().lower()
    if severity not in ALLOWED_SEVERITIES:
        failures.append("severity_not_allowed")

    if incident_type != case.final_response.incident_type:
        failures.append("incident_type_mismatch")

    if severity != case.final_response.severity:
        failures.append("severity_mismatch")

    top_error_lines = payload["top_error_lines"]
    if not isinstance(top_error_lines, list) or not any(
        isinstance(line, str) and line.strip() for line in top_error_lines
    ):
        failures.append("top_error_lines_empty")

    next_steps = payload["next_steps"]
    if not isinstance(next_steps, list) or not any(
        isinstance(step, str) and step.strip() for step in next_steps
    ):
        failures.append("next_steps_empty")

    retrieved_evidence = payload["retrieved_evidence"]
    if not isinstance(retrieved_evidence, list):
        failures.append("retrieved_evidence_not_list")

    source_citations = payload["source_citations"]
    if not isinstance(source_citations, list) or not any(
        isinstance(item, str) and item.strip() for item in source_citations
    ):
        failures.append("source_citations_empty")

    retrieval_status = str(payload["retrieval_status"]).strip().lower()
    if retrieval_status not in {"used", "not_used", "unavailable"}:
        failures.append("retrieval_status_not_allowed")

    confidence = payload["confidence"]
    if not isinstance(confidence, (int, float)) or not 0.0 <= float(confidence) <= 1.0:
        failures.append("confidence_out_of_range")

    return failures


def score_rag_search_results(case: RagEvalCase, hits: list[RetrievalHit]) -> list[str]:
    failures: list[str] = []
    if not hits:
        return ["no_hits"]

    citations = [hit.citation.lower() for hit in hits]
    snippets = [hit.snippet.lower() for hit in hits]

    if not any(
        keyword.lower() in citation
        for keyword in case.expected_citation_keywords
        for citation in citations
    ):
        failures.append("citation_keyword_mismatch")

    if not any(
        keyword.lower() in snippet
        for keyword in case.expected_snippet_keywords
        for snippet in snippets
    ):
        failures.append("snippet_keyword_mismatch")

    return failures


def score_workflow_thread_response(case: WorkflowEvalCase, payload: Any) -> list[str]:
    failures: list[str] = []

    if not isinstance(payload, dict):
        return ["response_not_json_object"]

    missing_keys = sorted(WORKFLOW_REQUIRED_RESPONSE_KEYS - payload.keys())
    if missing_keys:
        return [f"missing_keys:{','.join(missing_keys)}"]

    status = str(payload["status"]).strip().lower()
    if status not in {"initialized", "running", "waiting_for_approval", "completed", "failed"}:
        failures.append("status_not_allowed")

    approval_status = str(payload["approval_status"]).strip().lower()
    if approval_status not in {"not_required", "pending", "approved", "rejected"}:
        failures.append("approval_status_not_allowed")

    if not isinstance(payload["tool_results"], list) or not payload["tool_results"]:
        failures.append("tool_results_empty")

    confidence = payload.get("confidence")
    if confidence is not None and (not isinstance(confidence, (int, float)) or not 0.0 <= float(confidence) <= 1.0):
        failures.append("confidence_out_of_range")

    visible_incident_type = payload.get("incident_type")
    final_report = payload.get("final_report")

    if case.post_start_action == "inspect_only":
        if status != "waiting_for_approval":
            failures.append("status_mismatch")
        if approval_status != "pending":
            failures.append("approval_status_mismatch")
        if payload.get("approval_required") is not True:
            failures.append("approval_required_mismatch")
        if not payload.get("approval_request"):
            failures.append("approval_request_missing")
        if final_report is not None:
            failures.append("final_report_present_while_pending")
        if visible_incident_type != case.final_response.incident_type:
            failures.append("incident_type_mismatch")
        if not isinstance(payload.get("remediation_plan"), list) or not payload["remediation_plan"]:
            failures.append("remediation_plan_empty")
        return failures

    if status != "completed":
        failures.append("status_mismatch")
    if final_report is None:
        failures.append("final_report_missing")
        return failures
    if not isinstance(final_report, dict):
        failures.append("final_report_not_object")
        return failures

    final_incident_type = str(final_report.get("incident_type", "")).strip().lower()
    if final_incident_type != case.final_response.incident_type:
        failures.append("incident_type_mismatch")

    final_approval_status = str(final_report.get("approval_status", "")).strip().lower()
    expected_approval_status = _expected_approval_status(case)
    if approval_status != expected_approval_status:
        failures.append("approval_status_mismatch")
    if final_approval_status != expected_approval_status:
        failures.append("final_approval_status_mismatch")

    if not isinstance(final_report.get("remediation_plan"), list) or not final_report["remediation_plan"]:
        failures.append("final_remediation_plan_empty")
    if not isinstance(final_report.get("source_citations"), list) or not final_report["source_citations"]:
        failures.append("final_source_citations_empty")

    if case.post_start_action == "reject":
        if final_report.get("remediation_plan") != case.edited_remediation_plan:
            failures.append("rejected_plan_not_applied")
    elif case.post_start_action == "auto_complete":
        if payload.get("approval_required") is not False:
            failures.append("approval_required_mismatch")
        if approval_status != "not_required":
            failures.append("approval_status_mismatch")

    return failures


def _expected_approval_status(case: WorkflowEvalCase) -> ApprovalStatus:
    if case.post_start_action == "approve":
        return "approved"
    if case.post_start_action == "reject":
        return "rejected"
    return "not_required"
