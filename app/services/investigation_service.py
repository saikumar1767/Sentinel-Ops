from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from app.log_utils import dedupe_preserve_order, looks_like_error, strip_json_fences
from app.ollama_client import LLMGateway, ToolCallSpec
from app.prompts import (
    build_investigation_final_messages,
    build_investigation_planner_messages,
)
from app.schemas import InvestigateModelResponse, InvestigateRequest, InvestigateResponse
from app.settings import Settings
from app.tools.tool_registry import ToolExecutionRecord, ToolRegistry

logger = logging.getLogger(__name__)

LOG_EVIDENCE_TOOLS = {"read_log_file", "grep_error_pattern", "compare_two_logs"}
PLACEHOLDER_TOP_ERROR_LINES = {
    "No concrete error lines were captured from the available evidence.",
}
GENERIC_NEXT_STEPS = (
    "Review the cited log evidence and confirm the suspected failure mode.",
    "Follow the matching incident checklist and validate remediation in the affected service.",
)


@dataclass
class InvestigationContext:
    candidate_log_paths: list[str]
    cached_results: dict[tuple[str, str], tuple[str, ToolExecutionRecord]]
    baseline_records: list[ToolExecutionRecord]
    planner_records: list[ToolExecutionRecord]
    support_records: list[ToolExecutionRecord]

    @property
    def all_records(self) -> list[ToolExecutionRecord]:
        return [*self.baseline_records, *self.planner_records, *self.support_records]


class InvestigationService:
    def __init__(self, settings: Settings, gateway: LLMGateway, tool_registry: ToolRegistry):
        self.settings = settings
        self.gateway = gateway
        self.tool_registry = tool_registry

    def investigate(self, request: InvestigateRequest) -> InvestigateResponse:
        context = InvestigationContext(
            candidate_log_paths=self._resolve_candidate_log_paths(request),
            cached_results={},
            baseline_records=[],
            planner_records=[],
            support_records=[],
        )

        context.baseline_records = self._collect_baseline_records(request, context)
        context.planner_records = self._run_planner_loop(request, context)

        model_response = self._generate_model_response(request, context)
        context.support_records = self._collect_support_records(model_response, context)

        grounded_response = self._ground_response(model_response, context)
        try:
            self.tool_registry.incident_tools.save_incident(request, grounded_response)
        except OSError as exc:
            logger.warning("failed to persist incident summary: %s", exc)
        return grounded_response

    def _resolve_candidate_log_paths(self, request: InvestigateRequest) -> list[str]:
        if request.candidate_log_paths:
            return request.candidate_log_paths
        return self.tool_registry.file_tools.list_recent_log_paths(
            self.settings.max_recent_candidate_logs
        )

    def _collect_baseline_records(
        self,
        request: InvestigateRequest,
        context: InvestigationContext,
    ) -> list[ToolExecutionRecord]:
        records: list[ToolExecutionRecord] = []

        for path in context.candidate_log_paths:
            _, record = self._execute_named_tool(
                "read_log_file",
                {"path": path},
                context.cached_results,
            )
            records.append(record)

        compare_pair = self._select_compare_pair(context.candidate_log_paths)
        if compare_pair is not None:
            _, record = self._execute_named_tool(
                "compare_two_logs",
                {
                    "path_a": compare_pair[0],
                    "path_b": compare_pair[1],
                },
                context.cached_results,
            )
            records.append(record)

        if request.incident_type_hint is not None:
            _, record = self._execute_named_tool(
                "load_incident_template",
                {"incident_type": request.incident_type_hint},
                context.cached_results,
            )
            records.append(record)

        return records

    def _run_planner_loop(
        self,
        request: InvestigateRequest,
        context: InvestigationContext,
    ) -> list[ToolExecutionRecord]:
        baseline_summary = self._build_evidence_summary(context.baseline_records)
        baseline_citations = dedupe_preserve_order(
            self._collect_evidence_citations(context.baseline_records)
        )
        planner_messages = build_investigation_planner_messages(
            request=request,
            candidate_log_paths=context.candidate_log_paths,
            baseline_evidence_summary=baseline_summary,
            completed_evidence_citations=baseline_citations,
        )

        records: list[ToolExecutionRecord] = []

        for _ in range(self.settings.tool_max_iterations):
            turn = self.gateway.chat(
                model=self.settings.investigate_model,
                messages=planner_messages,
                tools=self.tool_registry.tools,
            )
            if not turn.tool_calls:
                break

            planner_messages.append(turn.message)
            for tool_call in turn.tool_calls:
                result_text, record = self._execute_tool_call(tool_call, context.cached_results)
                planner_messages.append(
                    {
                        "role": "tool",
                        "tool_name": tool_call.name,
                        "content": result_text,
                    }
                )
                records.append(record)
                logger.info(
                    "investigation_tool_call tool=%s ok=%s cached=%s args=%s",
                    record.name,
                    record.ok,
                    record.cached,
                    record.arguments,
                )

        return records

    def _generate_model_response(
        self,
        request: InvestigateRequest,
        context: InvestigationContext,
    ) -> InvestigateModelResponse:
        records = context.all_records
        evidence_summary = self._build_evidence_summary(records)
        evidence_citations = dedupe_preserve_order(self._collect_evidence_citations(records))
        schema = InvestigateModelResponse.model_json_schema()
        final_messages = build_investigation_final_messages(
            request=request,
            evidence_summary=evidence_summary,
            schema=schema,
            evidence_citations=evidence_citations,
        )
        final_turn = self.gateway.chat(
            model=self.settings.investigate_model,
            messages=final_messages,
            format=schema,
        )

        return InvestigateModelResponse.model_validate_json(
            strip_json_fences(final_turn.content)
        )

    def _collect_support_records(
        self,
        model_response: InvestigateModelResponse,
        context: InvestigationContext,
    ) -> list[ToolExecutionRecord]:
        if self._has_template_record(context.all_records, model_response.incident_type):
            return []

        _, record = self._execute_named_tool(
            "load_incident_template",
            {"incident_type": model_response.incident_type},
            context.cached_results,
        )
        return [record]

    def _execute_tool_call(
        self,
        tool_call: ToolCallSpec,
        cached_results: dict[tuple[str, str], tuple[str, ToolExecutionRecord]],
    ) -> tuple[str, ToolExecutionRecord]:
        return self._execute_named_tool(
            tool_call.name,
            tool_call.arguments,
            cached_results,
        )

    def _execute_named_tool(
        self,
        tool_name: str,
        arguments: dict[str, str | int],
        cached_results: dict[tuple[str, str], tuple[str, ToolExecutionRecord]],
    ) -> tuple[str, ToolExecutionRecord]:
        cache_key = (tool_name, json.dumps(arguments, sort_keys=True))
        if cache_key in cached_results:
            result_text, cached_record = cached_results[cache_key]
            return result_text, ToolExecutionRecord(
                name=cached_record.name,
                arguments=cached_record.arguments,
                ok=cached_record.ok,
                cached=True,
                payload=cached_record.payload,
            )

        result_text, record = self.tool_registry.execute_tool_call(tool_name, arguments)
        cached_results[cache_key] = (result_text, record)
        return result_text, record

    def _build_evidence_summary(self, records: list[ToolExecutionRecord]) -> str:
        if not records:
            return "No tool evidence was collected. Respond conservatively and lower confidence."

        evidence_lines: list[str] = []
        for record in records:
            if not record.ok:
                evidence_lines.append(
                    f"- {record.name}: safe failure -> {record.payload.get('error', 'unknown error')}"
                )
                continue

            payload = record.payload
            if selected_lines := payload.get("selected_lines"):
                joined = "; ".join(selected_lines[:3])
                evidence_lines.append(f"- {record.name} on {payload.get('path')}: {joined}")
                continue

            if matched_lines := payload.get("matched_lines"):
                joined = "; ".join(matched_lines[:3])
                evidence_lines.append(
                    f"- {record.name} on {payload.get('path')} using {payload.get('pattern')}: {joined}"
                )
                continue

            if differences := payload.get("differences"):
                joined = "; ".join(differences[:3])
                evidence_lines.append(f"- {record.name}: {joined}")
                continue

            if checklist := payload.get("checklist"):
                joined = "; ".join(checklist[:3])
                evidence_lines.append(
                    f"- {record.name} for {payload.get('incident_type')}: {joined}"
                )
                continue

            if incidents := payload.get("incidents"):
                summaries = [
                    f"{item['incident_type']}/{item['severity']}: {item['manager_summary']}"
                    for item in incidents[:2]
                ]
                evidence_lines.append(f"- {record.name}: {'; '.join(summaries)}")
                continue

            evidence_lines.append(f"- {record.name}: evidence collected")

        return "\n".join(evidence_lines)

    def _ground_response(
        self,
        model_response: InvestigateModelResponse,
        context: InvestigationContext,
    ) -> InvestigateResponse:
        records = context.all_records
        fallback_error_lines = dedupe_preserve_order(self._collect_top_error_lines(records))
        fallback_evidence = dedupe_preserve_order(self._collect_evidence_citations(records))

        model_error_lines = [
            line
            for line in model_response.top_error_lines
            if line.strip() and line.strip() not in PLACEHOLDER_TOP_ERROR_LINES
        ]
        top_error_lines = dedupe_preserve_order([*model_error_lines, *fallback_error_lines])
        if not top_error_lines:
            top_error_lines = ["No concrete error lines were captured from the available evidence."]

        next_steps = self._ground_next_steps(model_response, records)
        evidence_used = self._ground_evidence_used(model_response, fallback_evidence)

        confidence = model_response.confidence
        if not self._has_successful_log_evidence(records):
            confidence = min(confidence, 0.45)
        elif any(not record.ok for record in records):
            confidence = min(confidence, 0.75)

        return InvestigateResponse(
            incident_type=model_response.incident_type,
            severity=model_response.severity,
            top_error_lines=top_error_lines[:5],
            suspected_root_cause=model_response.suspected_root_cause,
            next_steps=next_steps[:5],
            manager_summary=model_response.manager_summary,
            evidence_used=evidence_used[:6],
            confidence=confidence,
        )

    def _ground_next_steps(
        self,
        model_response: InvestigateModelResponse,
        records: list[ToolExecutionRecord],
    ) -> list[str]:
        model_steps = [
            step
            for step in model_response.next_steps
            if step.strip() and step.strip() not in GENERIC_NEXT_STEPS
        ]
        if model_steps:
            return model_steps

        template_steps: list[str] = []
        for record in records:
            if record.name != "load_incident_template" or not record.ok:
                continue
            checklist = record.payload.get("checklist")
            if isinstance(checklist, list):
                template_steps.extend(str(item) for item in checklist)

        grounded_steps = dedupe_preserve_order(template_steps)
        if grounded_steps:
            return grounded_steps[:5]

        return list(GENERIC_NEXT_STEPS)

    def _ground_evidence_used(
        self,
        model_response: InvestigateModelResponse,
        fallback_evidence: list[str],
    ) -> list[str]:
        model_evidence = dedupe_preserve_order(
            item.strip() for item in model_response.evidence_used if item.strip()
        )
        if not fallback_evidence:
            return model_evidence or ["No supporting evidence was captured beyond the initial request."]

        if not self._contains_log_evidence(model_evidence):
            return fallback_evidence

        return dedupe_preserve_order([*model_evidence, *fallback_evidence])

    def _collect_top_error_lines(self, records: list[ToolExecutionRecord]) -> list[str]:
        lines: list[str] = []
        for record in records:
            payload = record.payload
            for key in ("selected_lines", "matched_lines", "new_error_lines"):
                value = payload.get(key)
                if isinstance(value, list):
                    lines.extend(
                        str(item)
                        for item in value
                        if isinstance(item, str) and looks_like_error(item)
                    )
        return lines

    def _collect_evidence_citations(self, records: list[ToolExecutionRecord]) -> list[str]:
        citations: list[str] = []
        for record in records:
            payload = record.payload
            if not record.ok:
                citations.append(f"{record.name}:safe_failure")
                continue

            path = payload.get("path")
            if path:
                citations.append(f"{record.name}:{path}")
                continue

            if payload.get("path_a") and payload.get("path_b"):
                citations.append(f"{record.name}:{payload['path_a']}->{payload['path_b']}")
                continue

            if payload.get("incident_type"):
                citations.append(f"{record.name}:{payload['incident_type']}")
                continue

            if payload.get("incidents"):
                citations.append("list_recent_incidents:local_history")
                continue

            citations.append(record.name)

        return citations

    def _contains_log_evidence(self, evidence_used: list[str]) -> bool:
        return any(
            item.startswith(("read_log_file:", "grep_error_pattern:", "compare_two_logs:"))
            for item in evidence_used
        )

    def _has_successful_log_evidence(self, records: list[ToolExecutionRecord]) -> bool:
        return any(record.ok and record.name in LOG_EVIDENCE_TOOLS for record in records)

    def _has_template_record(
        self,
        records: list[ToolExecutionRecord],
        incident_type: str,
    ) -> bool:
        return any(
            record.ok
            and record.name == "load_incident_template"
            and record.payload.get("incident_type") == incident_type
            for record in records
        )

    def _select_compare_pair(self, candidate_log_paths: list[str]) -> tuple[str, str] | None:
        if len(candidate_log_paths) < 2:
            return None

        first, second = candidate_log_paths[0], candidate_log_paths[1]
        first_score = self._score_log_path_position(first)
        second_score = self._score_log_path_position(second)

        if first_score == second_score:
            return first, second
        if first_score < second_score:
            return first, second
        return second, first

    @staticmethod
    def _score_log_path_position(path: str) -> int:
        lower_path = path.lower()
        score = 0

        if any(token in lower_path for token in ("previous", "baseline", "healthy", "before", "old")):
            score -= 10
        if any(token in lower_path for token in ("current", "latest", "failing", "failed", "after", "new")):
            score += 10

        return score
