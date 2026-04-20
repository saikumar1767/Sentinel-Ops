from __future__ import annotations

import logging
import re
from time import perf_counter

from app.confidence import AnalyzeConfidenceInputs, calibrate_analyze_confidence
from app.log_utils import (
    dedupe_preserve_order,
    extract_priority_lines,
    guess_incident_type,
    normalize_log_line,
    strip_json_fences,
)
from app.ollama_client import LLMGateway
from app.prompts import build_analyze_messages
from app.rag.models import RetrievalService
from app.rag.utils import (
    ANALYZE_RETRIEVAL_DOCUMENT_TYPES,
    format_retrieval_hits_for_prompt,
    retrieval_source_priority,
    retrieval_citations,
    retrieval_snippets,
)
from app.schemas import AnalyzeModelResponse, AnalyzeRequest, AnalyzeResponse, RetrievalHit, RetrievalStatus
from app.settings import Settings
from app.telemetry import set_span_attributes, start_span

logger = logging.getLogger(__name__)
SUMMARY_SPECULATION_MARKERS = (
    "potential",
    "possible",
    "likely",
    "suggest",
    "indicating",
    "may ",
    "might ",
    "reachability",
    "dns",
    "resolution",
)


def _normalized_evidence_clauses(top_error_lines: list[str]) -> list[str]:
    return [
        normalize_log_line(line).strip().rstrip(".")
        for line in top_error_lines
        if line.strip()
    ]


def _summary_clause_score(line: str) -> int:
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


def _summary_focus_clauses(top_error_lines: list[str], limit: int = 2) -> list[str]:
    candidates = [
        (clause, _summary_clause_score(line), index)
        for index, (line, clause) in enumerate(
            zip(top_error_lines, _normalized_evidence_clauses(top_error_lines), strict=False)
        )
        if clause
    ]
    ordered = sorted(candidates, key=lambda item: (-item[1], item[2]))
    return dedupe_preserve_order(clause for clause, _, _ in ordered)[:limit]


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


def _summary_mentions_clause(summary: str, clause: str) -> bool:
    summary_words = set(re.findall(r"[a-z0-9]+", summary.lower()))
    clause_words = [word for word in re.findall(r"[a-z0-9]+", clause.lower()) if len(word) > 3]
    if not clause_words:
        return False
    overlap = sum(1 for word in clause_words if word in summary_words)
    threshold = max(1, min(3, len(clause_words)))
    return overlap >= threshold


def _join_short_phrases(phrases: list[str]) -> str:
    if not phrases:
        return ""
    if len(phrases) == 1:
        return phrases[0]
    if len(phrases) == 2:
        return f"{phrases[0]} and {phrases[1]}"
    return f"{', '.join(phrases[:-1])}, and {phrases[-1]}"


def _summary_is_overreaching(summary: str) -> bool:
    lowered = summary.lower()
    return any(marker in lowered for marker in SUMMARY_SPECULATION_MARKERS)


def _synthesized_summary(incident_type: str, top_error_lines: list[str]) -> str:
    clauses = _summary_focus_clauses(top_error_lines)
    if not clauses:
        return ""
    if len(clauses) >= 2:
        return f"{incident_type.title()} incident with {clauses[0]} and {clauses[1]}."
    return f"{incident_type.title()} incident with {clauses[0]}."


def ground_summary(summary: str, incident_type: str, top_error_lines: list[str]) -> str:
    cleaned_summary = summary.strip().rstrip(".")
    clauses = _summary_focus_clauses(top_error_lines)
    synthesized = _synthesized_summary(incident_type, top_error_lines)

    if not clauses:
        return f"{cleaned_summary}." if cleaned_summary else cleaned_summary

    if not cleaned_summary or _summary_is_overreaching(cleaned_summary):
        return synthesized

    if len(clauses) >= 2:
        mentions_first = _summary_mentions_clause(cleaned_summary, clauses[0])
        mentions_second = _summary_mentions_clause(cleaned_summary, clauses[1])
        if not (mentions_first and mentions_second):
            return synthesized

    return f"{cleaned_summary}."


def ground_suspected_root_cause(root_cause: str, top_error_lines: list[str]) -> str:
    cleaned_root_cause = root_cause.strip().rstrip(".")
    humanized_lines = [normalize_log_line(line).strip().rstrip(".") for line in top_error_lines if line.strip()]
    lowered_lines = [line.lower() for line in humanized_lines]

    has_pool_exhaustion = any("pool exhausted" in line for line in lowered_lines)
    has_timeout = any("timeout" in line for line in lowered_lines)
    has_stalled_checkout = any(
        "stalled" in line or "waiting for a free database connection" in line
        for line in lowered_lines
    )
    has_deadlock = any("deadlock" in line for line in lowered_lines)
    has_lock_wait = any("lock wait" in line for line in lowered_lines)
    primary_postgres = any("primary-postgres" in line for line in lowered_lines)

    if has_deadlock:
        subject = "Database deadlocks"
    elif has_lock_wait:
        subject = "Database lock waits"
    elif has_pool_exhaustion:
        subject = (
            "Connection pool exhaustion on primary-postgres"
            if primary_postgres
            else "Database connection pool exhaustion"
        )
    elif has_timeout:
        subject = "Repeated database connection timeouts"
    elif has_stalled_checkout:
        subject = "Checkout requests stalled while waiting for a free database connection"
    else:
        subject = ""

    if subject:
        effects: list[str] = []
        if has_deadlock and "deadlock" not in subject.lower():
            effects.append("deadlock symptoms")
        if has_lock_wait and "lock wait" not in subject.lower():
            effects.append("lock wait contention")
        if has_timeout and "timeout" not in subject.lower():
            effects.append("repeated database timeouts")
        if has_stalled_checkout and "stalled" not in subject.lower():
            effects.append("stalled checkout requests")
        if effects:
            return f"{subject} is causing {_join_short_phrases(effects)}."
        return f"{subject}."

    clauses = _summary_focus_clauses(top_error_lines)
    if len(clauses) >= 2 and not (
        _summary_mentions_clause(cleaned_root_cause, clauses[0])
        and _summary_mentions_clause(cleaned_root_cause, clauses[1])
    ):
        return f"The current log shows {clauses[0]} and {clauses[1]}."
    if len(clauses) == 1 and not _summary_mentions_clause(cleaned_root_cause, clauses[0]):
        return f"The current log shows {clauses[0]}."

    return f"{cleaned_root_cause}."


def _retrieval_section_priority(hit: RetrievalHit) -> int:
    section = (hit.section_path or "").lower()
    document_type = hit.document_type

    if document_type == "runbook" and "symptom" in section:
        return 0
    if document_type == "readme" and any(
        token in section for token in ("operational notes", "investigation guidance", "troubleshooting")
    ):
        return 1
    if document_type == "github_issue" and "summary" in section:
        return 2
    if document_type == "troubleshooting_note":
        return 3
    if document_type == "runbook" and any(token in section for token in ("summary", "overview")):
        return 4
    if "mitigation" in section or "resolution" in section or "escalation" in section:
        return 5
    if "check" in section:
        return 6
    return 7


def _is_explanatory_retrieval_hit(hit: RetrievalHit) -> bool:
    section = (hit.section_path or "").lower()
    if any(token in section for token in ("check", "mitigation", "resolution", "action items", "escalation")):
        return False
    return True


class AnalyzeService:
    def __init__(self, settings: Settings, gateway: LLMGateway, retriever: RetrievalService):
        self.settings = settings
        self.gateway = gateway
        self.retriever = retriever

    def analyze(self, request: AnalyzeRequest) -> AnalyzeResponse:
        with start_span(
            "analyze.request",
            {
                "analyze.log_chars": len(request.log_text),
            },
        ) as span:
            schema = AnalyzeModelResponse.model_json_schema()
            top_error_lines = extract_priority_lines(request.log_text)
            retrieval_query = "\n".join(top_error_lines[:3])
            incident_type_hint = guess_incident_type(request.log_text)
            retrieval_hits, retrieval_status = self._retrieve_supporting_evidence(
                query=retrieval_query or request.log_text[:800],
                incident_type_hint=incident_type_hint,
            )
            messages = build_analyze_messages(
                request.log_text,
                schema,
                format_retrieval_hits_for_prompt(retrieval_hits),
                retrieval_citations(retrieval_hits),
            )
            response = self.gateway.chat(
                model=self.settings.analyze_model,
                messages=messages,
                format=schema,
            )

            model_response = AnalyzeModelResponse.model_validate_json(
                strip_json_fences(response.content)
            )
            response_payload = model_response.model_dump()
            response_payload["summary"] = ground_summary(
                model_response.summary,
                model_response.incident_type,
                top_error_lines,
            )
            response_payload["suspected_root_cause"] = ground_suspected_root_cause(
                model_response.suspected_root_cause,
                top_error_lines,
            )
            grounded_citations = self._ground_source_citations(
                model_response.source_citations,
                retrieval_hits,
            )
            response_payload["retrieved_evidence"] = self._ground_retrieved_evidence(
                model_response.retrieved_evidence,
                retrieval_hits,
                grounded_citations,
            )
            response_payload["source_citations"] = grounded_citations
            response_payload["confidence"] = self._calibrated_confidence(
                model_response=model_response,
                top_error_lines=top_error_lines,
                retrieval_hits=retrieval_hits,
                retrieval_status=retrieval_status,
                retrieved_evidence=response_payload["retrieved_evidence"],
                source_citations=grounded_citations,
                heuristic_incident_type=incident_type_hint,
            )
            set_span_attributes(
                span,
                {
                    "analyze.incident_type": model_response.incident_type,
                    "analyze.retrieval_status": retrieval_status,
                    "analyze.retrieval_hits": len(retrieval_hits),
                },
            )
            return AnalyzeResponse(
                **response_payload,
                top_error_lines=top_error_lines,
                retrieval_status=retrieval_status,
            )

    def _retrieve_supporting_evidence(
        self,
        *,
        query: str,
        incident_type_hint: str | None,
    ) -> tuple[list[RetrievalHit], RetrievalStatus]:
        started = perf_counter()
        with start_span(
            "analyze.retrieval",
            {
                "analyze.query_chars": len(query),
                "analyze.incident_type_hint": incident_type_hint,
            },
        ) as span:
            try:
                search_kwargs = {
                    "query": query,
                    "top_k": max(self.settings.retrieval_top_k * 2, 6),
                    "document_types": ANALYZE_RETRIEVAL_DOCUMENT_TYPES,
                    "incident_type_hint": incident_type_hint,
                }
                try:
                    hits = self.retriever.search(
                        **search_kwargs,
                        overfetch_multiplier=4,
                    )
                except TypeError as exc:
                    if "overfetch_multiplier" not in str(exc):
                        raise
                    hits = self.retriever.search(**search_kwargs)
            except Exception as exc:
                logger.warning("analyze retrieval unavailable: %s", exc)
                set_span_attributes(span, {"analyze.retrieval_status": "unavailable"})
                return [], "unavailable"

            reranked_hits = sorted(
                hits,
                key=lambda hit: (
                    retrieval_source_priority(hit),
                    _retrieval_section_priority(hit),
                    -(hit.similarity_score or 0.0),
                    hit.citation,
                ),
            )[: self.settings.retrieval_top_k]
            duration_ms = (perf_counter() - started) * 1000
            logger.info(
                "analyze_retrieval incident_type_hint=%s cache_candidate_query_chars=%s hits=%s duration_ms=%.3f",
                incident_type_hint,
                len(query),
                len(reranked_hits),
                duration_ms,
            )
            set_span_attributes(
                span,
                {
                    "analyze.retrieval_status": "used" if reranked_hits else "not_used",
                    "analyze.retrieval_hits": len(reranked_hits),
                    "analyze.retrieval_duration_ms": round(duration_ms, 3),
                },
            )
            return reranked_hits, ("used" if reranked_hits else "not_used")

    @staticmethod
    def _ground_source_citations(
        model_citations: list[str],
        retrieval_hits: list[RetrievalHit],
    ) -> list[str]:
        preferred_hits = AnalyzeService._preferred_retrieval_hits(retrieval_hits)
        allowed_citations = [hit.citation for hit in preferred_hits]
        filtered = [
            citation
            for citation in dedupe_preserve_order(item.strip() for item in model_citations if item.strip())
            if citation in allowed_citations
        ]
        merged = dedupe_preserve_order([*filtered, *allowed_citations])
        return merged[: max(1, len(allowed_citations))]

    @staticmethod
    def _ground_retrieved_evidence(
        model_evidence: list[str],
        retrieval_hits: list[RetrievalHit],
        selected_citations: list[str],
    ) -> list[str]:
        preferred_hits = AnalyzeService._preferred_retrieval_hits(retrieval_hits)
        hit_snippets_by_citation = {
            hit.citation: _clean_retrieval_snippet(hit.snippet)
            for hit in preferred_hits
            if _clean_retrieval_snippet(hit.snippet)
        }
        grounded_from_citations = [
            hit_snippets_by_citation[citation]
            for citation in selected_citations
            if citation in hit_snippets_by_citation
        ]
        if grounded_from_citations:
            return dedupe_preserve_order(grounded_from_citations)[:4]

        cleaned_model_evidence = dedupe_preserve_order(
            cleaned
            for cleaned in (_clean_retrieved_evidence_item(item) for item in model_evidence)
            if cleaned
        )
        if cleaned_model_evidence:
            return cleaned_model_evidence[:4]

        return [
            cleaned
            for cleaned in (_clean_retrieval_snippet(item) for item in retrieval_snippets(preferred_hits))
            if cleaned
        ][:4]

    @staticmethod
    def _preferred_retrieval_hits(retrieval_hits: list[RetrievalHit], limit: int = 2) -> list[RetrievalHit]:
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

    @staticmethod
    def _calibrated_confidence(
        *,
        model_response: AnalyzeModelResponse,
        top_error_lines: list[str],
        retrieval_hits: list[RetrievalHit],
        retrieval_status: RetrievalStatus,
        retrieved_evidence: list[str],
        source_citations: list[str],
        heuristic_incident_type: str | None,
    ) -> float:
        clauses = _summary_focus_clauses(top_error_lines)
        summary_mentions_multiple_failure_signals = (
            len(clauses) >= 2
            and _summary_mentions_clause(model_response.summary, clauses[0])
            and _summary_mentions_clause(model_response.summary, clauses[1])
        )
        inputs = AnalyzeConfidenceInputs(
            model_confidence=model_response.confidence,
            top_error_line_count=len(top_error_lines),
            incident_type_matches_heuristic=(
                heuristic_incident_type is None
                or heuristic_incident_type == model_response.incident_type
            ),
            retrieval_status=retrieval_status,
            retrieval_hit_count=len(retrieval_hits),
            retrieved_evidence_count=len(retrieved_evidence),
            source_citation_count=len(source_citations),
            summary_mentions_multiple_failure_signals=summary_mentions_multiple_failure_signals,
        )
        return calibrate_analyze_confidence(inputs)
