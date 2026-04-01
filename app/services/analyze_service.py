from __future__ import annotations

from app.log_utils import extract_priority_lines, normalize_log_line, strip_json_fences
from app.ollama_client import LLMGateway
from app.prompts import build_analyze_messages
from app.schemas import AnalyzeModelResponse, AnalyzeRequest, AnalyzeResponse
from app.settings import Settings


def ground_suspected_root_cause(root_cause: str, top_error_lines: list[str]) -> str:
    cleaned_root_cause = root_cause.strip().rstrip(".")
    evidence = "; ".join(normalize_log_line(line) for line in top_error_lines[:3] if line.strip())

    if not evidence:
        return cleaned_root_cause

    evidence_clause = f"Evidence from log: {evidence}"
    if evidence_clause.lower() in cleaned_root_cause.lower():
        return cleaned_root_cause

    return f"{cleaned_root_cause}. {evidence_clause}"


class AnalyzeService:
    def __init__(self, settings: Settings, gateway: LLMGateway):
        self.settings = settings
        self.gateway = gateway

    def analyze(self, request: AnalyzeRequest) -> AnalyzeResponse:
        schema = AnalyzeModelResponse.model_json_schema()
        messages = build_analyze_messages(request.log_text, schema)
        response = self.gateway.chat(
            model=self.settings.analyze_model,
            messages=messages,
            format=schema,
        )

        model_response = AnalyzeModelResponse.model_validate_json(
            strip_json_fences(response.content)
        )
        top_error_lines = extract_priority_lines(request.log_text)
        response_payload = model_response.model_dump()
        response_payload["suspected_root_cause"] = ground_suspected_root_cause(
            model_response.suspected_root_cause,
            top_error_lines,
        )
        return AnalyzeResponse(**response_payload, top_error_lines=top_error_lines)
