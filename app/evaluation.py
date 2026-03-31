import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from app.schemas import ALLOWED_SEVERITIES, IncidentType, Severity

REQUIRED_RESPONSE_KEYS = {
    "incident_type",
    "severity",
    "summary",
    "suspected_root_cause",
    "recommended_action",
    "top_error_lines",
    "confidence",
}


class EvalCase(BaseModel):
    id: str
    input_log: str
    expected_incident_type: IncidentType
    expected_severity: Severity
    expected_root_cause_keywords: list[str] = Field(min_length=1)


def eval_cases_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "data" / "eval_cases"


def load_eval_cases(directory: Path | None = None) -> list[EvalCase]:
    case_dir = directory or eval_cases_dir()
    cases: list[EvalCase] = []

    for path in sorted(case_dir.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        cases.append(EvalCase(**payload))

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
