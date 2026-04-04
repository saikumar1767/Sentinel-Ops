from __future__ import annotations

from dataclasses import dataclass

from app.schemas import RetrievalStatus


def _clamp(value: float, *, low: float = 0.05, high: float = 0.98) -> float:
    return max(low, min(high, value))


def _round_confidence(value: float) -> float:
    return round(_clamp(value), 2)


def _blend(model_confidence: float, evidence_confidence: float) -> float:
    # Treat model confidence as a prior and let grounded evidence dominate.
    blended = (0.35 * _clamp(model_confidence)) + (0.65 * _clamp(evidence_confidence))
    return _round_confidence(blended)


@dataclass(frozen=True)
class AnalyzeConfidenceInputs:
    model_confidence: float
    top_error_line_count: int
    incident_type_matches_heuristic: bool
    retrieval_status: RetrievalStatus
    retrieval_hit_count: int
    retrieved_evidence_count: int
    source_citation_count: int
    summary_mentions_multiple_failure_signals: bool


@dataclass(frozen=True)
class InvestigationConfidenceInputs:
    model_confidence: float
    top_error_line_count: int
    successful_log_evidence: bool
    compare_evidence_present: bool
    retrieval_status: RetrievalStatus
    retrieval_hit_count: int
    retrieved_evidence_count: int
    source_citation_count: int
    any_tool_failures: bool
    incident_type_matches_hint_or_heuristic: bool


def calibrate_analyze_confidence(inputs: AnalyzeConfidenceInputs) -> float:
    evidence = 0.28

    if inputs.top_error_line_count >= 1:
        evidence += 0.18
    if inputs.top_error_line_count >= 2:
        evidence += 0.10
    if inputs.top_error_line_count >= 3:
        evidence += 0.05

    if inputs.incident_type_matches_heuristic:
        evidence += 0.12

    if inputs.summary_mentions_multiple_failure_signals:
        evidence += 0.08

    if inputs.retrieval_status == "used" and inputs.retrieval_hit_count > 0:
        evidence += 0.08
    elif inputs.retrieval_status == "unavailable":
        evidence -= 0.08

    if inputs.retrieved_evidence_count >= 1:
        evidence += 0.05
    if inputs.retrieved_evidence_count >= 2:
        evidence += 0.04

    if inputs.source_citation_count >= 1:
        evidence += 0.05
    if inputs.source_citation_count >= 2:
        evidence += 0.05

    return _blend(inputs.model_confidence, evidence)


def calibrate_investigation_confidence(inputs: InvestigationConfidenceInputs) -> float:
    evidence = 0.22

    if inputs.successful_log_evidence:
        evidence += 0.22
    else:
        evidence -= 0.14

    if inputs.top_error_line_count >= 1:
        evidence += 0.10
    if inputs.top_error_line_count >= 2:
        evidence += 0.08
    if inputs.top_error_line_count >= 3:
        evidence += 0.05

    if inputs.compare_evidence_present:
        evidence += 0.08

    if inputs.incident_type_matches_hint_or_heuristic:
        evidence += 0.10

    if inputs.retrieval_status == "used" and inputs.retrieval_hit_count > 0:
        evidence += 0.08
    elif inputs.retrieval_status == "unavailable":
        evidence -= 0.08

    if inputs.retrieved_evidence_count >= 1:
        evidence += 0.04
    if inputs.retrieved_evidence_count >= 2:
        evidence += 0.03

    if inputs.source_citation_count >= 1:
        evidence += 0.05
    if inputs.source_citation_count >= 3:
        evidence += 0.05

    if inputs.any_tool_failures:
        evidence -= 0.12

    return _blend(inputs.model_confidence, evidence)
