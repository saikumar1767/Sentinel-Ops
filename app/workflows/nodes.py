from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from langgraph.types import interrupt

from app.log_utils import dedupe_preserve_order, guess_incident_type, truncate_text
from app.ollama_client import LLMGateway
from app.rag.models import RetrievalService
from app.schemas import (
    InvestigateModelResponse,
    InvestigateRequest,
    InvestigateResponse,
    RetrievalHit,
    RetrievalStatus,
    WorkflowFinalReport,
)
from app.services.investigation_service import InvestigationContext, InvestigationService
from app.settings import Settings
from app.telemetry import start_span
from app.tools.tool_registry import ToolExecutionRecord, ToolRegistry
from app.workflows.state import ApprovalStatus, SentinelWorkflowState

logger = logging.getLogger(__name__)

APPROVAL_ACTION_MARKERS = (
    "restart",
    "recycle",
    "rollback",
    "pause",
    "stop",
    "kill",
    "throttle",
    "scale",
    "failover",
    "restore",
    "rotate",
    "revoke",
    "block",
    "isolate",
    "drain",
    "clear",
    "mitigate",
)


@dataclass
class ApprovalDecision:
    status: ApprovalStatus
    review_notes: str | None
    edited_remediation_plan: list[str]


class SentinelWorkflowNodes:
    def __init__(
        self,
        *,
        settings: Settings,
        gateway: LLMGateway,
        tool_registry: ToolRegistry,
        retriever: RetrievalService,
    ) -> None:
        self.settings = settings
        self.tool_registry = tool_registry
        self.investigation_service = InvestigationService(
            settings=settings,
            gateway=gateway,
            tool_registry=tool_registry,
            retriever=retriever,
        )

    def intake_node(self, state: SentinelWorkflowState) -> dict[str, Any]:
        with start_span("workflow.node.intake"):
            prompt = state["prompt"].strip()
            candidate_log_paths = list(state.get("candidate_log_paths", []))
            input_summary = truncate_text(prompt, 180)
            if candidate_log_paths:
                input_summary = f"{input_summary} | candidate_logs={len(candidate_log_paths)}"

            return {
                "current_step": "intake_node",
                "status": "running",
                "input_summary": input_summary,
                "candidate_log_paths": candidate_log_paths,
                "approval_required": False,
                "approval_status": "not_required",
                "approval_reason": None,
                "approval_notes": None,
                "approval_request": None,
                "audit_trail": list(state.get("audit_trail", [])),
                "retrieval_status": "not_used",
                "errors": list(state.get("errors", [])),
            }

    def incident_classifier_node(self, state: SentinelWorkflowState) -> dict[str, Any]:
        with start_span("workflow.node.classify_incident"):
            request = self._request_from_state(state)
            incident_type = request.incident_type_hint or guess_incident_type(request.prompt) or "service"
            severity = self._classify_prompt_severity(request.prompt)

            return {
                "current_step": "incident_classifier_node",
                "status": "running",
                "incident_type": incident_type,
                "severity": severity,
            }

    def tool_evidence_node(self, state: SentinelWorkflowState) -> dict[str, Any]:
        with start_span("workflow.node.gather_evidence"):
            request = self._request_from_state(state)
            context = InvestigationContext(
                candidate_log_paths=self.investigation_service._resolve_candidate_log_paths(request),
                cached_results={},
                baseline_records=[],
                planner_records=[],
                support_records=[],
                retrieval_hits=[],
                retrieval_status="not_used",
            )

            context.baseline_records = self.investigation_service._collect_baseline_records(request, context)
            context.planner_records = self.investigation_service._run_planner_loop(request, context)
            top_error_lines = dedupe_preserve_order(
                self.investigation_service._collect_top_error_lines(context.all_records)
            )[:5]

            return {
                "current_step": "tool_evidence_node",
                "status": "running",
                "candidate_log_paths": context.candidate_log_paths,
                "baseline_records": self._serialize_records(context.baseline_records),
                "planner_records": self._serialize_records(context.planner_records),
                "tool_results": self._serialize_records(context.all_records),
                "top_error_lines": top_error_lines,
                "severity": self._severity_from_evidence(
                    top_error_lines=top_error_lines,
                    fallback=state.get("severity", "low"),
                ),
            }

    def retrieval_node(self, state: SentinelWorkflowState) -> dict[str, Any]:
        with start_span("workflow.node.retrieve_supporting_docs"):
            request = self._request_from_state(state)
            context = self._context_from_state(state)
            retrieval_hits, retrieval_status = self.investigation_service._retrieve_knowledge(
                request,
                context,
            )

            return {
                "current_step": "retrieval_node",
                "status": "running",
                "retrieved_chunks": [hit.model_dump(mode="json") for hit in retrieval_hits],
                "retrieval_status": retrieval_status,
            }

    def hypothesis_node(self, state: SentinelWorkflowState) -> dict[str, Any]:
        with start_span("workflow.node.draft_hypothesis"):
            request = self._request_from_state(state)
            context = self._context_from_state(state)
            model_response = self.investigation_service._generate_model_response(request, context)

            return {
                "current_step": "hypothesis_node",
                "status": "running",
                "draft_model_response": model_response.model_dump(mode="json"),
                "incident_type": model_response.incident_type,
                "severity": model_response.severity,
                "suspected_root_cause": model_response.suspected_root_cause,
            }

    def remediation_node(self, state: SentinelWorkflowState) -> dict[str, Any]:
        with start_span("workflow.node.draft_remediation"):
            request = self._request_from_state(state)
            context = self._context_from_state(state)
            model_response = InvestigateModelResponse.model_validate(state["draft_model_response"])
            context.support_records = self.investigation_service._collect_support_records(model_response, context)
            grounded_response = self.investigation_service._ground_response(request, model_response, context)
            approval_required, approval_reason = self._approval_gate_for_response(
                grounded_response=grounded_response,
                require_approval=state.get("require_approval_for_remediation", True),
            )
            approval_request = (
                self._build_approval_request(grounded_response, approval_reason)
                if approval_required
                else None
            )
            approval_status: ApprovalStatus = "pending" if approval_required else "not_required"

            return {
                "current_step": "remediation_node",
                "status": "running",
                "support_records": self._serialize_records(context.support_records),
                "tool_results": self._serialize_records(context.all_records),
                "grounded_response": grounded_response.model_dump(mode="json"),
                "incident_type": grounded_response.incident_type,
                "severity": grounded_response.severity,
                "suspected_root_cause": grounded_response.suspected_root_cause,
                "remediation_plan": grounded_response.next_steps,
                "top_error_lines": grounded_response.top_error_lines,
                "manager_summary": grounded_response.manager_summary,
                "retrieved_evidence": grounded_response.retrieved_evidence,
                "source_citations": grounded_response.source_citations,
                "retrieval_status": grounded_response.retrieval_status,
                "confidence": grounded_response.confidence,
                "approval_required": approval_required,
                "approval_status": approval_status,
                "approval_reason": approval_reason,
                "approval_request": approval_request,
            }

    def approval_node(self, state: SentinelWorkflowState) -> dict[str, Any]:
        if not state.get("approval_required", False):
            return {}

        with start_span("workflow.node.awaiting_approval"):
            decision = interrupt(state.get("approval_request") or {})
            parsed = self._parse_approval_decision(decision)
            grounded_response = dict(state.get("grounded_response") or {})
            if parsed.edited_remediation_plan:
                grounded_response["next_steps"] = parsed.edited_remediation_plan

            return {
                "current_step": "approval_node",
                "status": "running",
                "approval_status": parsed.status,
                "approval_notes": parsed.review_notes,
                "approval_request": None,
                "remediation_plan": parsed.edited_remediation_plan or state.get("remediation_plan", []),
                "grounded_response": grounded_response,
            }

    def final_report_node(self, state: SentinelWorkflowState) -> dict[str, Any]:
        with start_span("workflow.node.final_report"):
            grounded_payload = dict(state.get("grounded_response") or {})
            remediation_plan = list(state.get("remediation_plan", []))
            if remediation_plan:
                grounded_payload["next_steps"] = remediation_plan

            grounded_response = InvestigateResponse.model_validate(grounded_payload)
            engineer_summary = self._build_engineer_summary(
                grounded_response=grounded_response,
                approval_status=state.get("approval_status", "not_required"),
                approval_notes=state.get("approval_notes"),
            )
            final_report = WorkflowFinalReport(
                incident_type=grounded_response.incident_type,
                severity=grounded_response.severity,
                top_error_lines=grounded_response.top_error_lines,
                suspected_root_cause=grounded_response.suspected_root_cause,
                remediation_plan=grounded_response.next_steps,
                engineer_summary=engineer_summary,
                manager_summary=grounded_response.manager_summary,
                retrieved_evidence=grounded_response.retrieved_evidence,
                source_citations=grounded_response.source_citations,
                retrieval_status=grounded_response.retrieval_status,
                approval_status=state.get("approval_status", "not_required"),
                approval_notes=state.get("approval_notes"),
                confidence=grounded_response.confidence,
            )

            try:
                self.tool_registry.incident_tools.save_incident(
                    self._request_from_state(state),
                    grounded_response,
                )
            except OSError as exc:
                logger.warning("failed to persist workflow incident summary: %s", exc)

            return {
                "current_step": "final_report_node",
                "status": "completed",
                "engineer_summary": engineer_summary,
                "manager_summary": grounded_response.manager_summary,
                "remediation_plan": grounded_response.next_steps,
                "top_error_lines": grounded_response.top_error_lines,
                "retrieved_evidence": grounded_response.retrieved_evidence,
                "source_citations": grounded_response.source_citations,
                "confidence": grounded_response.confidence,
                "final_report": final_report.model_dump(mode="json"),
            }

    @staticmethod
    def _serialize_records(records: list[ToolExecutionRecord]) -> list[dict[str, Any]]:
        return [record.model_dump(mode="json") for record in records]

    @staticmethod
    def _deserialize_records(payloads: list[dict[str, Any]]) -> list[ToolExecutionRecord]:
        return [ToolExecutionRecord.model_validate(payload) for payload in payloads]

    @staticmethod
    def _deserialize_hits(payloads: list[dict[str, Any]]) -> list[RetrievalHit]:
        return [RetrievalHit.model_validate(payload) for payload in payloads]

    def _request_from_state(self, state: SentinelWorkflowState) -> InvestigateRequest:
        return InvestigateRequest(
            prompt=state["prompt"],
            candidate_log_paths=state.get("candidate_log_paths", []),
            incident_type_hint=state.get("incident_type_hint"),
        )

    def _context_from_state(self, state: SentinelWorkflowState) -> InvestigationContext:
        return InvestigationContext(
            candidate_log_paths=list(state.get("candidate_log_paths", [])),
            cached_results={},
            baseline_records=self._deserialize_records(state.get("baseline_records", [])),
            planner_records=self._deserialize_records(state.get("planner_records", [])),
            support_records=self._deserialize_records(state.get("support_records", [])),
            retrieval_hits=self._deserialize_hits(state.get("retrieved_chunks", [])),
            retrieval_status=state.get("retrieval_status", "not_used"),
        )

    @staticmethod
    def _classify_prompt_severity(prompt: str) -> str:
        lowered = prompt.lower()
        critical_markers = (
            "ransomware",
            "malware",
            "security compromise",
            "data loss",
            "complete outage",
            "total outage",
            "all requests failing",
        )
        high_markers = (
            "timeout",
            "failed",
            "failure",
            "exception",
            "pool exhausted",
            "deadlock",
            "disk full",
            "no space left",
            "packet loss",
            "queue backlog",
            "consumer lag",
        )
        medium_markers = (
            "latency",
            "degraded",
            "retry",
            "throttle",
            "warn",
            "slow",
        )

        if any(marker in lowered for marker in critical_markers):
            return "critical"
        if any(marker in lowered for marker in high_markers):
            return "high"
        if any(marker in lowered for marker in medium_markers):
            return "medium"
        return "low"

    def _approval_gate_for_response(
        self,
        *,
        grounded_response: InvestigateResponse,
        require_approval: bool,
    ) -> tuple[bool, str | None]:
        if not require_approval:
            return False, None

        actionable_steps = [
            step
            for step in grounded_response.next_steps
            if any(marker in step.lower() for marker in APPROVAL_ACTION_MARKERS)
        ]
        if grounded_response.severity in {"high", "critical"} and grounded_response.next_steps:
            return (
                True,
                "High-impact remediation should be reviewed before anyone executes the checklist.",
            )
        if actionable_steps:
            return (
                True,
                "The remediation checklist contains operational changes that should be approved before execution.",
            )
        return False, None

    @staticmethod
    def _build_approval_request(
        grounded_response: InvestigateResponse,
        approval_reason: str | None,
    ) -> dict[str, Any]:
        return {
            "type": "approval_required",
            "approval_reason": approval_reason,
            "incident_type": grounded_response.incident_type,
            "severity": grounded_response.severity,
            "suspected_root_cause": grounded_response.suspected_root_cause,
            "manager_summary": grounded_response.manager_summary,
            "proposed_remediation_plan": grounded_response.next_steps,
            "source_citations": grounded_response.source_citations,
        }

    def _build_engineer_summary(
        self,
        *,
        grounded_response: InvestigateResponse,
        approval_status: ApprovalStatus,
        approval_notes: str | None,
    ) -> str:
        evidence_summary = "; ".join(grounded_response.top_error_lines[:2])
        approval_clause = {
            "approved": "Approval was granted for the checklist",
            "rejected": "Approval was rejected, so the checklist should be treated as a reviewed draft only",
            "pending": "Approval is still pending",
            "not_required": "No approval gate was required for this checklist",
        }[approval_status]
        checklist_summary = "; ".join(
            step.strip().rstrip(" .;")
            for step in grounded_response.next_steps[:3]
            if step.strip()
        )
        clauses = [
            f"SentinelOps classified this as a {grounded_response.severity} {grounded_response.incident_type} incident",
            f"Evidence: {evidence_summary}" if evidence_summary else None,
            f"Hypothesis: {grounded_response.suspected_root_cause}",
            f"Checklist: {checklist_summary}" if checklist_summary else None,
            approval_clause,
            f"Reviewer notes: {approval_notes.strip()}" if approval_notes else None,
        ]
        return " ".join(
            self._ensure_sentence(clause)
            for clause in clauses
            if clause
        )

    def _parse_approval_decision(self, decision: Any) -> ApprovalDecision:
        if isinstance(decision, str):
            normalized = decision.strip().lower()
            if normalized not in {"approved", "rejected"}:
                raise ValueError("Approval decision must be approved or rejected.")
            return ApprovalDecision(
                status=normalized,  # type: ignore[arg-type]
                review_notes=None,
                edited_remediation_plan=[],
            )

        if not isinstance(decision, dict):
            raise ValueError("Approval decision must be a string or object payload.")

        raw_status = str(decision.get("decision", "approved")).strip().lower()
        if raw_status not in {"approved", "rejected"}:
            raise ValueError("Approval decision must be approved or rejected.")

        raw_plan = decision.get("edited_remediation_plan") or []
        if not isinstance(raw_plan, list):
            raise ValueError("edited_remediation_plan must be a list of strings.")

        cleaned_plan = dedupe_preserve_order(str(item) for item in raw_plan if str(item).strip())
        review_notes = str(decision.get("review_notes", "")).strip() or None

        return ApprovalDecision(
            status=raw_status,  # type: ignore[arg-type]
            review_notes=review_notes,
            edited_remediation_plan=cleaned_plan,
        )

    @staticmethod
    def _ensure_sentence(text: str) -> str:
        cleaned = text.strip()
        if not cleaned:
            return ""
        if cleaned[-1] in ".!?":
            return cleaned
        return f"{cleaned}."

    @staticmethod
    def _severity_from_evidence(*, top_error_lines: list[str], fallback: str) -> str:
        if any(any(marker in line.upper() for marker in ("CRITICAL", "FATAL")) for line in top_error_lines):
            return "critical"

        ranking = {"low": 0, "medium": 1, "high": 2, "critical": 3}
        inferred = "high" if top_error_lines else fallback
        return inferred if ranking.get(inferred, 0) >= ranking.get(fallback, 0) else fallback
