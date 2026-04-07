from __future__ import annotations

import json
import logging
from dataclasses import dataclass
import re
from time import perf_counter

from app.confidence import InvestigationConfidenceInputs, calibrate_investigation_confidence
from app.log_utils import (
    dedupe_preserve_order,
    guess_incident_type,
    looks_like_error,
    normalize_log_line,
    strip_json_fences,
)
from app.ollama_client import LLMGateway, ToolCallSpec
from app.prompts import (
    build_investigation_final_messages,
    build_investigation_planner_messages,
)
from app.rag.models import RetrievalService
from app.rag.utils import (
    INVESTIGATION_RETRIEVAL_DOCUMENT_TYPES,
    format_retrieval_hits_for_prompt,
    retrieval_citations,
    retrieval_snippets,
)
from app.schemas import (
    InvestigateModelResponse,
    InvestigateRequest,
    InvestigateResponse,
    RetrievalHit,
    RetrievalStatus,
)
from app.settings import Settings
from app.telemetry import set_span_attributes, start_span
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
    retrieval_hits: list[RetrievalHit]
    retrieval_status: RetrievalStatus

    @property
    def all_records(self) -> list[ToolExecutionRecord]:
        return [*self.baseline_records, *self.planner_records, *self.support_records]


def _clean_retrieved_evidence_item(item: str) -> str:
    cleaned = item.strip().lstrip("-").strip()
    if not cleaned:
        return ""

    if ": " not in cleaned:
        return cleaned

    prefix, suffix = cleaned.split(": ", 1)
    if any(marker in prefix for marker in ("/", ".md", "#")) or prefix.startswith(
        ("read_log_file", "compare_two_logs", "load_incident_template", "list_recent_incidents")
    ):
        return suffix.strip()
    return cleaned


def _clean_retrieval_snippet(text: str) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    normalized_lines: list[str] = []
    for line in lines:
        normalized = line.lstrip("- ").strip()
        normalized = re.sub(r"\s+", " ", normalized).rstrip(" ;")
        if normalized:
            normalized_lines.append(normalized)

    if not normalized_lines:
        return ""
    if len(normalized_lines) == 1:
        return normalized_lines[0]
    return " ".join(
        sentence if sentence.endswith(".") else f"{sentence}."
        for sentence in normalized_lines
    ).strip()


def _clean_top_error_line(line: str) -> str:
    cleaned = re.sub(r"\s+", " ", line.strip())
    return cleaned.rstrip(" ;")


def _humanize_evidence_line(line: str) -> str:
    without_line_number = re.sub(r"^\d+:\s*", "", _clean_top_error_line(line))
    return normalize_log_line(without_line_number).strip().rstrip(".")


def _error_clause_score(line: str) -> int:
    upper = line.upper()
    lower = line.lower()
    score = 0

    if any(token in upper for token in ("ERROR", "CRITICAL", "FATAL", "EXCEPTION", "FAILED", "FAILURE")):
        score += 4
    if any(token in lower for token in ("pool exhausted", "timeout", "deadlock", "refused", "stalled")):
        score += 3
    if any(token in lower for token in ("retry", "attempt", "warning", "warn")):
        score -= 2

    return score


def _focus_error_clauses(top_error_lines: list[str], limit: int = 2) -> list[str]:
    candidates = [
        (_humanize_evidence_line(line), _error_clause_score(line), index)
        for index, line in enumerate(top_error_lines)
        if line.strip()
    ]
    ordered = sorted(candidates, key=lambda item: (-item[1], item[2]))
    return dedupe_preserve_order(clause for clause, _, _ in ordered if clause)[:limit]


def _summary_mentions_clause(summary: str, clause: str) -> bool:
    summary_words = set(re.findall(r"[a-z0-9]+", summary.lower()))
    clause_words = [word for word in re.findall(r"[a-z0-9]+", clause.lower()) if len(word) > 3]
    if not clause_words:
        return False
    overlap = sum(1 for word in clause_words if word in summary_words)
    threshold = max(1, min(3, len(clause_words)))
    return overlap >= threshold


def _join_clauses(clauses: list[str]) -> str:
    if not clauses:
        return ""
    if len(clauses) == 1:
        return clauses[0]
    return f"{clauses[0]} and {clauses[1]}"


def _join_short_phrases(phrases: list[str]) -> str:
    if not phrases:
        return ""
    if len(phrases) == 1:
        return phrases[0]
    if len(phrases) == 2:
        return f"{phrases[0]} and {phrases[1]}"
    return f"{', '.join(phrases[:-1])}, and {phrases[-1]}"


def _retrieval_section_priority(hit: RetrievalHit) -> int:
    section = (hit.section_path or "").lower()
    document_type = hit.document_type

    if document_type == "runbook" and "symptom" in section:
        return 0
    if document_type == "readme" and any(token in section for token in ("operational notes", "investigation guidance", "troubleshooting")):
        return 1
    if document_type == "github_issue" and "summary" in section:
        return 2
    if document_type == "troubleshooting_note":
        return 3
    if document_type == "runbook" and any(token in section for token in ("summary", "overview", "checks")):
        return 4
    if "mitigation" in section:
        return 5
    return 6


def _is_explanatory_retrieval_hit(hit: RetrievalHit) -> bool:
    section = (hit.section_path or "").lower()
    if hit.document_type == "incident_template":
        return False
    if any(token in section for token in ("check", "mitigation", "resolution", "action items")):
        return False
    return True


def _has_action_or_mitigation_step(steps: list[str]) -> bool:
    action_markers = (
        "reduce",
        "restart",
        "recycle",
        "mitigate",
        "escalate",
        "pause",
        "rollback",
        "clear",
        "kill",
        "stop",
        "throttle",
        "scale",
        "lower",
    )
    return any(any(marker in step.lower() for marker in action_markers) for step in steps)


class InvestigationService:
    def __init__(
        self,
        settings: Settings,
        gateway: LLMGateway,
        tool_registry: ToolRegistry,
        retriever: RetrievalService,
    ):
        self.settings = settings
        self.gateway = gateway
        self.tool_registry = tool_registry
        self.retriever = retriever

    def investigate(self, request: InvestigateRequest) -> InvestigateResponse:
        with start_span(
            "investigate.request",
            {
                "investigate.prompt_chars": len(request.prompt),
                "investigate.candidate_log_count": len(request.candidate_log_paths),
            },
        ) as span:
            context = InvestigationContext(
                candidate_log_paths=self._resolve_candidate_log_paths(request),
                cached_results={},
                baseline_records=[],
                planner_records=[],
                support_records=[],
                retrieval_hits=[],
                retrieval_status="not_used",
            )

            context.baseline_records = self._collect_baseline_records(request, context)
            context.planner_records = self._run_planner_loop(request, context)
            context.retrieval_hits, context.retrieval_status = self._retrieve_knowledge(request, context)

            model_response = self._generate_model_response(request, context)
            context.support_records = self._collect_support_records(model_response, context)

            grounded_response = self._ground_response(request, model_response, context)
            try:
                self.tool_registry.incident_tools.save_incident(request, grounded_response)
            except OSError as exc:
                logger.warning("failed to persist incident summary: %s", exc)
            set_span_attributes(
                span,
                {
                    "investigate.incident_type": grounded_response.incident_type,
                    "investigate.retrieval_status": grounded_response.retrieval_status,
                    "investigate.tool_record_count": len(context.all_records),
                },
            )
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
        with start_span(
            "investigate.planner_loop",
            {
                "investigate.max_iterations": self.settings.tool_max_iterations,
                "investigate.candidate_log_count": len(context.candidate_log_paths),
            },
        ) as span:
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
                        "investigation_tool_call tool=%s ok=%s cached=%s duration_ms=%s args=%s",
                        record.name,
                        record.ok,
                        record.cached,
                        record.duration_ms,
                        record.arguments,
                    )

            set_span_attributes(
                span,
                {
                    "investigate.planner_records": len(records),
                },
            )
            return records

    def _generate_model_response(
        self,
        request: InvestigateRequest,
        context: InvestigationContext,
    ) -> InvestigateModelResponse:
        with start_span(
            "investigate.model_response",
            {
                "investigate.record_count": len(context.all_records),
                "investigate.retrieval_hit_count": len(context.retrieval_hits),
            },
        ):
            records = context.all_records
            evidence_summary = self._build_evidence_summary(records)
            retrieval_summary = format_retrieval_hits_for_prompt(context.retrieval_hits)
            evidence_citations = dedupe_preserve_order(
                [
                    *self._collect_evidence_citations(records),
                    *retrieval_citations(context.retrieval_hits),
                ]
            )
            schema = InvestigateModelResponse.model_json_schema()
            final_messages = build_investigation_final_messages(
                request=request,
                evidence_summary=evidence_summary,
                retrieved_evidence_summary=retrieval_summary,
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
                duration_ms=cached_record.duration_ms,
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
        request: InvestigateRequest,
        model_response: InvestigateModelResponse,
        context: InvestigationContext,
    ) -> InvestigateResponse:
        records = context.all_records
        fallback_error_lines = dedupe_preserve_order(self._collect_top_error_lines(records))
        tool_citations = dedupe_preserve_order(self._collect_evidence_citations(records))
        retrieval_hit_citations = retrieval_citations(context.retrieval_hits)
        allowed_citations = set([*tool_citations, *retrieval_hit_citations, "request:prompt_only"])

        top_error_lines = self._ground_top_error_lines(model_response.top_error_lines, fallback_error_lines)
        if not top_error_lines:
            top_error_lines = ["No concrete error lines were captured from the available evidence."]

        next_steps = self._ground_next_steps(model_response, records)
        source_citations, selected_retrieval_citations = self._ground_source_citations(
            model_response,
            allowed_citations,
            context.retrieval_hits,
            retrieval_hit_citations,
            records,
        )
        retrieved_evidence = self._ground_retrieved_evidence(
            model_response,
            context.retrieval_hits,
            selected_retrieval_citations,
        )
        confidence = self._calibrated_confidence(
            model_response=model_response,
            request=request,
            context=context,
            top_error_lines=top_error_lines,
            retrieved_evidence=retrieved_evidence,
            source_citations=source_citations,
        )

        return InvestigateResponse(
            incident_type=model_response.incident_type,
            severity=self._ground_severity(
                model_response=model_response,
                request=request,
                top_error_lines=top_error_lines,
            ),
            top_error_lines=top_error_lines[:5],
            suspected_root_cause=self._ground_suspected_root_cause(
                model_response.suspected_root_cause,
                top_error_lines,
                records,
            ),
            next_steps=next_steps[:5],
            manager_summary=self._ground_manager_summary(
                model_response.manager_summary,
                model_response.incident_type,
                top_error_lines,
                records,
            ),
            retrieved_evidence=retrieved_evidence[:5],
            source_citations=source_citations[:8],
            retrieval_status=context.retrieval_status,
            confidence=confidence,
        )

    def _ground_top_error_lines(
        self,
        model_error_lines: list[str],
        fallback_error_lines: list[str],
    ) -> list[str]:
        ordered_candidates = [
            *(_clean_top_error_line(line) for line in fallback_error_lines),
            *(
                _clean_top_error_line(line)
                for line in model_error_lines
                if line.strip() and line.strip() not in PLACEHOLDER_TOP_ERROR_LINES
            ),
        ]

        grounded: list[str] = []
        seen_keys: set[str] = set()
        for candidate in ordered_candidates:
            if not candidate:
                continue
            key = _humanize_evidence_line(candidate).lower()
            if key in seen_keys:
                continue
            seen_keys.add(key)
            grounded.append(candidate)
        return grounded

    def _ground_next_steps(
        self,
        model_response: InvestigateModelResponse,
        records: list[ToolExecutionRecord],
    ) -> list[str]:
        template_steps = self._template_steps(records)
        model_steps = [
            step
            for step in model_response.next_steps
            if step.strip() and step.strip() not in GENERIC_NEXT_STEPS
        ]
        if model_steps:
            grounded_steps = dedupe_preserve_order(model_steps)
            if not _has_action_or_mitigation_step(grounded_steps):
                mitigation_steps = [
                    step for step in template_steps if _has_action_or_mitigation_step([step])
                ]
                grounded_steps.extend(
                    step for step in mitigation_steps if step not in grounded_steps
                )
            return grounded_steps[:5]

        grounded_steps = dedupe_preserve_order(template_steps)
        if grounded_steps:
            return grounded_steps[:5]

        return list(GENERIC_NEXT_STEPS)

    def _ground_retrieved_evidence(
        self,
        model_response: InvestigateModelResponse,
        retrieval_hits: list[RetrievalHit],
        selected_retrieval_citations: list[str],
    ) -> list[str]:
        preferred_hits = self._preferred_retrieval_hits(retrieval_hits)
        snippets_by_citation = {
            hit.citation: _clean_retrieval_snippet(hit.snippet)
            for hit in preferred_hits
            if _clean_retrieval_snippet(hit.snippet)
        }
        grounded = [
            snippets_by_citation[citation]
            for citation in selected_retrieval_citations
            if citation in snippets_by_citation
        ]
        if grounded:
            return dedupe_preserve_order(grounded)[:5]

        if preferred_hits:
            return [
                _clean_retrieval_snippet(hit.snippet)
                for hit in preferred_hits
                if _clean_retrieval_snippet(hit.snippet)
            ][:5]

        if retrieval_hits:
            return [
                cleaned
                for cleaned in (_clean_retrieval_snippet(item) for item in retrieval_snippets(retrieval_hits))
                if cleaned
            ][:5]

        cleaned_model_evidence = dedupe_preserve_order(
            cleaned
            for cleaned in (
                _clean_retrieved_evidence_item(item) for item in model_response.retrieved_evidence
            )
            if cleaned
        )
        return cleaned_model_evidence[:5]

    def _ground_source_citations(
        self,
        model_response: InvestigateModelResponse,
        allowed_citations: set[str],
        retrieval_hits: list[RetrievalHit],
        retrieval_hit_citations: list[str],
        records: list[ToolExecutionRecord],
    ) -> tuple[list[str], list[str]]:
        preferred_retrieval_citations = [
            hit.citation for hit in self._preferred_retrieval_hits(retrieval_hits)
        ]
        filtered_model_citations = [
            item
            for item in dedupe_preserve_order(
                citation.strip() for citation in model_response.source_citations if citation.strip()
            )
            if item in allowed_citations
        ]
        selected_retrieval_citations = [
            citation for citation in preferred_retrieval_citations if citation in retrieval_hit_citations
        ] or retrieval_hit_citations[:2]

        selected_tool_citations = self._prioritized_tool_citations(records)
        merged = dedupe_preserve_order(
            [
                *selected_tool_citations,
                *[
                    citation
                    for citation in filtered_model_citations
                    if citation not in retrieval_hit_citations and citation not in selected_tool_citations
                ],
                *selected_retrieval_citations,
            ]
        )
        return (merged or ["request:prompt_only"]), selected_retrieval_citations

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

    def _ground_suspected_root_cause(
        self,
        suspected_root_cause: str,
        top_error_lines: list[str],
        records: list[ToolExecutionRecord],
    ) -> str:
        cleaned_root_cause = suspected_root_cause.strip().rstrip(".")
        humanized_lines = [_humanize_evidence_line(line) for line in top_error_lines if line.strip()]
        compare_record = self._first_successful_record(records, "compare_two_logs")
        has_regression = compare_record is not None and (
            compare_record.payload.get("new_error_lines") or compare_record.payload.get("missing_success_lines")
        )

        synthesized = self._synthesize_root_cause_from_evidence(humanized_lines)
        if synthesized:
            cleaned_root_cause = synthesized
        else:
            clauses = _focus_error_clauses(top_error_lines)
            if len(clauses) >= 2 and not (
                _summary_mentions_clause(cleaned_root_cause, clauses[0])
                and _summary_mentions_clause(cleaned_root_cause, clauses[1])
            ):
                cleaned_root_cause = f"The current run shows {clauses[0]} and {clauses[1]}"
            elif len(clauses) == 1 and not _summary_mentions_clause(cleaned_root_cause, clauses[0]):
                cleaned_root_cause = f"The current run shows {clauses[0]}"

        if has_regression:
            return f"{cleaned_root_cause}. Compared with the previous run, this appears to be a current regression."
        return f"{cleaned_root_cause}."

    def _ground_manager_summary(
        self,
        manager_summary: str,
        incident_type: str,
        top_error_lines: list[str],
        records: list[ToolExecutionRecord],
    ) -> str:
        cleaned_summary = manager_summary.strip().rstrip(".")
        clauses = _focus_error_clauses(top_error_lines)
        compare_record = self._first_successful_record(records, "compare_two_logs")
        has_regression_signal = compare_record is not None and (
            compare_record.payload.get("new_error_lines") or compare_record.payload.get("missing_success_lines")
        )

        if clauses:
            clause_text = _join_clauses(clauses)
            if has_regression_signal:
                return (
                    f"The current {incident_type} run is failing with {clause_text}, while the previous run was healthy."
                )

            if not cleaned_summary or not any(
                _summary_mentions_clause(cleaned_summary, clause) for clause in clauses
            ):
                return f"The current {incident_type} incident is driven by {clause_text}."

        return f"{cleaned_summary}."

    def _ground_severity(
        self,
        *,
        model_response: InvestigateModelResponse,
        request: InvestigateRequest,
        top_error_lines: list[str],
    ) -> str:
        model_severity = model_response.severity
        if model_severity != "critical":
            return model_severity

        evidence_text = " ".join(
            [
                request.prompt,
                model_response.suspected_root_cause,
                model_response.manager_summary,
                *top_error_lines,
            ]
        ).lower()
        critical_markers = (
            "ransomware",
            "malware",
            "exfiltration",
            "security compromise",
            "data loss",
            "complete outage",
            "total outage",
            "all requests failing",
        )
        if any(marker in evidence_text for marker in critical_markers):
            return "critical"
        return "high"

    def _synthesize_root_cause_from_evidence(self, humanized_lines: list[str]) -> str:
        lowered_lines = [line.lower() for line in humanized_lines]

        has_pool_exhaustion = any("pool exhausted" in line for line in lowered_lines)
        has_timeout = any("timeout" in line for line in lowered_lines)
        has_stalled_checkout = any(
            "stalled" in line or "waiting for free database connection" in line
            for line in lowered_lines
        )
        primary_postgres = any("primary-postgres" in line for line in lowered_lines)

        if not any((has_pool_exhaustion, has_timeout, has_stalled_checkout)):
            return ""

        if has_pool_exhaustion:
            subject = (
                "Connection pool exhaustion on primary-postgres"
                if primary_postgres
                else "Database connection pool exhaustion"
            )
        elif has_timeout:
            subject = "Repeated database connection timeouts"
        else:
            subject = "Checkout requests stalled while waiting for a free database connection"

        effects: list[str] = []
        if has_timeout and "timeout" not in subject.lower():
            effects.append("repeated database timeouts")
        if has_stalled_checkout and "stalled" not in subject.lower():
            effects.append("stalled checkout requests")

        if effects:
            return f"{subject} is causing {_join_short_phrases(effects)}"
        return subject

    def _template_steps(self, records: list[ToolExecutionRecord]) -> list[str]:
        template_steps: list[str] = []
        for record in records:
            if record.name != "load_incident_template" or not record.ok:
                continue
            checklist = record.payload.get("checklist")
            if isinstance(checklist, list):
                template_steps.extend(str(item) for item in checklist)
        return template_steps

    def _preferred_retrieval_hits(self, retrieval_hits: list[RetrievalHit], limit: int = 2) -> list[RetrievalHit]:
        explanatory_hits = [hit for hit in retrieval_hits if _is_explanatory_retrieval_hit(hit)]
        selected = explanatory_hits[:limit]
        if len(selected) < limit:
            for hit in retrieval_hits:
                if hit in selected:
                    continue
                selected.append(hit)
                if len(selected) >= limit:
                    break
        return selected

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

    def _prioritized_tool_citations(self, records: list[ToolExecutionRecord]) -> list[str]:
        read_citations: list[tuple[int, str]] = []
        compare_citations: list[str] = []
        template_citations: list[str] = []
        failure_citations: list[str] = []

        for record in records:
            payload = record.payload
            if not record.ok:
                failure_citations.append(f"{record.name}:safe_failure")
                continue

            if record.name == "read_log_file" and payload.get("path"):
                path = str(payload["path"])
                read_citations.append((self._score_log_path_position(path), f"{record.name}:{path}"))
                continue

            if record.name == "compare_two_logs" and payload.get("path_a") and payload.get("path_b"):
                compare_citations.append(f"{record.name}:{payload['path_a']}->{payload['path_b']}")
                continue

            if record.name == "load_incident_template" and payload.get("incident_type"):
                template_citations.append(f"{record.name}:{payload['incident_type']}")

        ordered_reads = [citation for _, citation in sorted(read_citations, key=lambda item: (-item[0], item[1]))]
        merged = dedupe_preserve_order(
            [
                *ordered_reads[:2],
                *compare_citations[:1],
                *template_citations[:1],
                *failure_citations[:1],
            ]
        )
        return merged

    @staticmethod
    def _first_successful_record(
        records: list[ToolExecutionRecord],
        tool_name: str,
    ) -> ToolExecutionRecord | None:
        return next((record for record in records if record.ok and record.name == tool_name), None)

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

    def _retrieve_knowledge(
        self,
        request: InvestigateRequest,
        context: InvestigationContext,
    ) -> tuple[list[RetrievalHit], RetrievalStatus]:
        started = perf_counter()
        records = context.all_records
        query_parts = [
            request.prompt.strip(),
            *(self._collect_top_error_lines(records)[:3]),
        ]
        if request.incident_type_hint is not None:
            query_parts.append(f"Incident type hint: {request.incident_type_hint}")

        query = "\n".join(part for part in query_parts if part).strip()
        if not query:
            return [], "not_used"
        incident_type_hint = request.incident_type_hint or guess_incident_type(query)
        with start_span(
            "investigate.retrieval",
            {
                "investigate.query_chars": len(query),
                "investigate.incident_type_hint": incident_type_hint,
            },
        ) as span:
            try:
                hits = self.retriever.search(
                    query=query,
                    top_k=max(self.settings.retrieval_top_k * 2, 6),
                    document_types=INVESTIGATION_RETRIEVAL_DOCUMENT_TYPES,
                    incident_type_hint=incident_type_hint,
                )
            except Exception as exc:
                logger.warning("investigation retrieval unavailable: %s", exc)
                set_span_attributes(span, {"investigate.retrieval_status": "unavailable"})
                return [], "unavailable"

            reranked_hits = sorted(
                hits,
                key=lambda hit: (
                    _retrieval_section_priority(hit),
                    -(hit.similarity_score or 0.0),
                    hit.citation,
                ),
            )[: self.settings.retrieval_top_k]
            duration_ms = (perf_counter() - started) * 1000
            logger.info(
                "investigation_retrieval incident_type_hint=%s hits=%s duration_ms=%.3f",
                incident_type_hint,
                len(reranked_hits),
                duration_ms,
            )
            set_span_attributes(
                span,
                {
                    "investigate.retrieval_status": "used" if reranked_hits else "not_used",
                    "investigate.retrieval_hits": len(reranked_hits),
                    "investigate.retrieval_duration_ms": round(duration_ms, 3),
                },
            )
            return reranked_hits, ("used" if reranked_hits else "not_used")

    def _calibrated_confidence(
        self,
        *,
        model_response: InvestigateModelResponse,
        request: InvestigateRequest,
        context: InvestigationContext,
        top_error_lines: list[str],
        retrieved_evidence: list[str],
        source_citations: list[str],
    ) -> float:
        records = context.all_records
        guessed_incident_type = guess_incident_type(
            "\n".join([request.prompt, *top_error_lines[:3]])
        )
        inputs = InvestigationConfidenceInputs(
            model_confidence=model_response.confidence,
            top_error_line_count=len(top_error_lines),
            successful_log_evidence=self._has_successful_log_evidence(records),
            compare_evidence_present=any(
                record.ok and record.name == "compare_two_logs"
                for record in records
            ),
            retrieval_status=context.retrieval_status,
            retrieval_hit_count=len(context.retrieval_hits),
            retrieved_evidence_count=len(retrieved_evidence),
            source_citation_count=len(source_citations),
            any_tool_failures=any(not record.ok for record in records),
            incident_type_matches_hint_or_heuristic=(
                (request.incident_type_hint is None or request.incident_type_hint == model_response.incident_type)
                and (guessed_incident_type is None or guessed_incident_type == model_response.incident_type)
            ),
        )
        return calibrate_investigation_confidence(inputs)
