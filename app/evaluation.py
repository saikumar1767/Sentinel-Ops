import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from app.schemas import (
    ALLOWED_INCIDENT_TYPES,
    ALLOWED_SEVERITIES,
    IncidentType,
    InvestigateModelResponse,
    InvestigateResponse,
    Severity,
)

REQUIRED_RESPONSE_KEYS = {
    "incident_type",
    "severity",
    "summary",
    "suspected_root_cause",
    "recommended_action",
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
    "evidence_used",
    "confidence",
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


def eval_cases_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "data" / "eval_cases"


def load_eval_cases(directory: Path | None = None) -> list[EvalCase]:
    case_dir = directory or eval_cases_dir()
    cases: list[EvalCase] = []

    for path in sorted(case_dir.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        cases.append(EvalCase(**payload))

    return cases


def investigation_eval_cases_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "data" / "tool_eval_cases"


def load_investigation_eval_cases(directory: Path | None = None) -> list[InvestigationEvalCase]:
    case_dir = directory or investigation_eval_cases_dir()
    cases: list[InvestigationEvalCase] = []

    for path in sorted(case_dir.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        cases.append(InvestigationEvalCase(**payload))

    return cases


def score_analysis_response(case: EvalCase, payload: Any) -> list[str]:
    failures: list[str] = []

    if not isinstance(payload, dict):
        return ["response_not_json_object"]

    missing_keys = sorted(REQUIRED_RESPONSE_KEYS - payload.keys())
    if missing_keys:
        return [f"missing_keys:{','.join(missing_keys)}"]

    severity = str(payload["severity"]).strip().lower()
    if severity not in ALLOWED_SEVERITIES:
        failures.append("severity_not_allowed")

    top_error_lines = payload["top_error_lines"]
    if not isinstance(top_error_lines, list) or not any(
        isinstance(line, str) and line.strip() for line in top_error_lines
    ):
        failures.append("top_error_lines_empty")

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

    evidence_used = payload["evidence_used"]
    if not isinstance(evidence_used, list) or not any(
        isinstance(item, str) and item.strip() for item in evidence_used
    ):
        failures.append("evidence_used_empty")

    confidence = payload["confidence"]
    if not isinstance(confidence, (int, float)) or not 0.0 <= float(confidence) <= 1.0:
        failures.append("confidence_out_of_range")

    return failures
