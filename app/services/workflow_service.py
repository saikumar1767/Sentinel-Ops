from __future__ import annotations

import json
import re
import sqlite3
from typing import Any
from uuid import uuid4

from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command

from app.audit import WorkflowAuditTrail
from app.auth import AuthenticatedUser
from app.log_utils import dedupe_preserve_order, looks_like_error
from app.metadata_store import WorkflowThreadStore
from app.ollama_client import LLMGateway
from app.persistence import is_sqlite_url, normalize_postgres_dsn, sqlite_database_path
from app.rag.models import RetrievalService
from app.schemas import (
    WorkflowApproveRequest,
    WorkflowAuditResponse,
    WorkflowInvestigateRequest,
    WorkflowRejectRequest,
    WorkflowResumeRequest,
    WorkflowThreadListResponse,
    WorkflowThreadResponse,
)
from app.settings import Settings
from app.telemetry import start_span
from app.tools.tool_registry import ToolRegistry
from app.workflows.nodes import SentinelWorkflowNodes
from app.workflows.sentinel_graph import build_sentinel_workflow


class WorkflowService:
    def __init__(
        self,
        *,
        settings: Settings,
        gateway: LLMGateway,
        tool_registry: ToolRegistry,
        retriever: RetrievalService,
        audit_trail: WorkflowAuditTrail | None = None,
        thread_store: WorkflowThreadStore | None = None,
    ) -> None:
        self.settings = settings
        self.audit_trail = audit_trail
        self.thread_store = thread_store
        self._connection: sqlite3.Connection | None = None
        self._checkpointer_context = None
        self._checkpointer = self._build_checkpointer()
        self._graph = build_sentinel_workflow(
            nodes=SentinelWorkflowNodes(
                settings=settings,
                gateway=gateway,
                tool_registry=tool_registry,
                retriever=retriever,
            ),
            checkpointer=self._checkpointer,
        )

    def close(self) -> None:
        if self._checkpointer_context is not None:
            self._checkpointer_context.__exit__(None, None, None)
            self._checkpointer_context = None
        if self._connection is not None:
            self._connection.close()
            self._connection = None

    def start_investigation(
        self,
        request: WorkflowInvestigateRequest,
        *,
        actor: AuthenticatedUser | None = None,
    ) -> WorkflowThreadResponse:
        with start_span("workflow.start", {"workflow.has_thread_id": bool(request.thread_id)}):
            thread_id = request.thread_id or f"workflow-{uuid4().hex}"
            if self._thread_exists(thread_id):
                raise ValueError(f"Workflow thread '{thread_id}' already exists.")

            response = self._invoke_workflow(
                thread_id,
                {
                    "request_id": uuid4().hex,
                    "prompt": request.prompt,
                    "candidate_log_paths": request.candidate_log_paths,
                    "incident_type_hint": request.incident_type_hint,
                    "require_approval_for_remediation": request.require_approval_for_remediation,
                    "status": "initialized",
                    "errors": [],
                    "audit_trail": [],
                },
            )
            self._record_thread_snapshot(response, actor=actor)
            return response

    def get_thread(self, thread_id: str) -> WorkflowThreadResponse:
        with start_span("workflow.get_thread", {"workflow.thread_id": thread_id}):
            snapshot = self._graph.get_state(self._config(thread_id))
            if not self._snapshot_exists(snapshot):
                raise KeyError(f"Workflow thread '{thread_id}' was not found.")
            return self._build_thread_response(thread_id, snapshot, self._audit_events(thread_id))

    def list_threads(
        self,
        *,
        limit: int | None = None,
        status: str | None = None,
        incident_type: str | None = None,
    ) -> WorkflowThreadListResponse:
        if self.thread_store is None:
            return WorkflowThreadListResponse(total_threads=0, threads=[])
        return self.thread_store.list_threads(
            limit=limit or self.settings.workflow_recent_threads_limit,
            status=status,
            incident_type=incident_type,
        )

    def resume(
        self,
        thread_id: str,
        request: WorkflowResumeRequest,
        *,
        actor: AuthenticatedUser | None = None,
    ) -> WorkflowThreadResponse:
        return self._resume_with_payload(
            thread_id,
            {
                "decision": request.decision,
                "review_notes": request.review_notes,
                "edited_remediation_plan": request.edited_remediation_plan,
            },
            action="resume",
            actor=actor,
        )

    def approve(
        self,
        thread_id: str,
        request: WorkflowApproveRequest,
        *,
        actor: AuthenticatedUser | None = None,
    ) -> WorkflowThreadResponse:
        return self._resume_with_payload(
            thread_id,
            {
                "decision": "approved",
                "review_notes": request.review_notes,
                "edited_remediation_plan": request.edited_remediation_plan,
            },
            action="approve",
            actor=actor,
        )

    def reject(
        self,
        thread_id: str,
        request: WorkflowRejectRequest,
        *,
        actor: AuthenticatedUser | None = None,
    ) -> WorkflowThreadResponse:
        return self._resume_with_payload(
            thread_id,
            {
                "decision": "rejected",
                "review_notes": request.reason,
                "edited_remediation_plan": request.edited_remediation_plan,
            },
            action="reject",
            actor=actor,
        )

    def audit_report(self, thread_id: str) -> WorkflowAuditResponse:
        if not self._thread_exists(thread_id):
            raise KeyError(f"Workflow thread '{thread_id}' was not found.")
        if self.audit_trail is None:
            return WorkflowAuditResponse(thread_id=thread_id, total_events=0, events=[])
        return self.audit_trail.thread_audit(thread_id)

    def _resume_with_payload(
        self,
        thread_id: str,
        payload: dict[str, object],
        *,
        action: str,
        actor: AuthenticatedUser | None = None,
    ) -> WorkflowThreadResponse:
        snapshot = self._graph.get_state(self._config(thread_id))
        if not self._snapshot_exists(snapshot):
            raise KeyError(f"Workflow thread '{thread_id}' was not found.")
        snapshot_values = dict(snapshot.values or {})
        if snapshot_values.get("status") == "failed":
            raise RuntimeError(f"Workflow thread '{thread_id}' is in a failed state and cannot be resumed.")
        if snapshot_values.get("status") == "completed":
            raise RuntimeError(f"Workflow thread '{thread_id}' is already complete.")
        if not snapshot.interrupts:
            raise RuntimeError(f"Workflow thread '{thread_id}' is not waiting for external input.")

        response = self._invoke_workflow(thread_id, Command(resume=payload))
        self._record_audit_event(
            thread_id=thread_id,
            action=action,
            payload=payload,
            status_after=response.status,
            request_id=response.request_id,
            actor=actor,
        )
        self._record_thread_snapshot(response, actor=actor)
        return response

    def _thread_exists(self, thread_id: str) -> bool:
        snapshot = self._graph.get_state(self._config(thread_id))
        return self._snapshot_exists(snapshot)

    def _build_checkpointer(self):
        database_url = self.settings.effective_workflow_checkpoint_database_url
        if is_sqlite_url(database_url):
            sqlite_path = sqlite_database_path(database_url) or self.settings.workflow_checkpoint_path
            sqlite_path.parent.mkdir(parents=True, exist_ok=True)
            self._connection = sqlite3.connect(
                sqlite_path,
                check_same_thread=False,
            )
            return SqliteSaver(self._connection)

        checkpoint_dsn = normalize_postgres_dsn(database_url)
        self._checkpointer_context = PostgresSaver.from_conn_string(checkpoint_dsn)
        checkpointer = self._checkpointer_context.__enter__()
        checkpointer.setup()
        return checkpointer

    def _invoke_workflow(
        self,
        thread_id: str,
        graph_input: dict[str, Any] | Command,
    ) -> WorkflowThreadResponse:
        config = self._config(thread_id)
        try:
            self._graph.invoke(graph_input, config)
        except Exception as exc:
            return self._mark_failed_thread(thread_id, exc)
        return self.get_thread(thread_id)

    def _mark_failed_thread(self, thread_id: str, exc: Exception) -> WorkflowThreadResponse:
        config = self._config(thread_id)
        snapshot = self._graph.get_state(config)
        if not self._snapshot_exists(snapshot):
            raise exc

        failed_task = self._failed_task(snapshot)
        existing_errors = list(dict(snapshot.values or {}).get("errors", []))
        task_errors = [
            self._normalize_error_message(task.error)
            for task in snapshot.tasks
            if getattr(task, "error", None)
        ]
        error_message = self._normalize_error_message(exc)
        error_lines = dedupe_preserve_order(
            [
                *existing_errors,
                *task_errors,
                error_message,
            ]
        )
        update_payload = {
            "status": "failed",
            "current_step": failed_task.name if failed_task is not None else self._current_step_from_snapshot(snapshot),
            "errors": error_lines,
            "approval_request": None,
        }
        self._graph.update_state(config, update_payload)
        return self.get_thread(thread_id)

    @staticmethod
    def _snapshot_exists(snapshot) -> bool:
        return bool(snapshot.created_at or snapshot.values)

    @staticmethod
    def _config(thread_id: str) -> dict[str, dict[str, str]]:
        return {"configurable": {"thread_id": thread_id}}

    @staticmethod
    def _build_thread_response(thread_id: str, snapshot, audit_trail: list[dict[str, Any]]) -> WorkflowThreadResponse:
        values = dict(snapshot.values or {})
        configurable = dict((snapshot.config or {}).get("configurable", {}))
        pending_interrupt = snapshot.interrupts[0].value if snapshot.interrupts else None
        failed_task = WorkflowService._failed_task(snapshot)
        current_step = (
            failed_task.name
            if failed_task is not None
            else WorkflowService._current_step_from_snapshot(snapshot)
        )
        status = values.get("status", "running")
        if failed_task is not None or status == "failed":
            status = "failed"
        elif snapshot.interrupts:
            status = "waiting_for_approval"
        elif not snapshot.next:
            status = values.get("status", "completed")

        tool_results = values.get("tool_results")
        if not tool_results:
            tool_results = [
                *values.get("baseline_records", []),
                *values.get("planner_records", []),
                *values.get("support_records", []),
            ]
        tool_results = WorkflowService._dedupe_tool_results(tool_results)
        retrieved_chunks = values.get("retrieved_chunks", [])
        top_error_lines = values.get("top_error_lines") or WorkflowService._derive_top_error_lines(tool_results)
        source_citations = values.get("source_citations") or WorkflowService._derive_source_citations(
            tool_results=tool_results,
            retrieved_chunks=retrieved_chunks,
        )
        retrieved_evidence = values.get("retrieved_evidence") or WorkflowService._derive_retrieved_evidence(
            retrieved_chunks
        )
        errors = dedupe_preserve_order(
            [
                *values.get("errors", []),
                *[
                    WorkflowService._normalize_error_message(task.error)
                    for task in snapshot.tasks
                    if getattr(task, "error", None)
                ],
            ]
        )
        available_actions = ["approve", "reject", "resume"] if status == "waiting_for_approval" else []

        return WorkflowThreadResponse(
            thread_id=thread_id,
            request_id=values.get("request_id", thread_id),
            status=status,
            current_stage=WorkflowService._stage_from_snapshot(status=status, current_step=current_step),
            current_step=current_step,
            available_actions=available_actions,
            checkpoint_id=configurable.get("checkpoint_id"),
            checkpoint_created_at=snapshot.created_at,
            input_summary=values.get("input_summary"),
            incident_type=values.get("incident_type"),
            severity=values.get("severity"),
            suspected_root_cause=values.get("suspected_root_cause"),
            remediation_plan=values.get("remediation_plan", []),
            top_error_lines=top_error_lines,
            engineer_summary=values.get("engineer_summary"),
            manager_summary=values.get("manager_summary"),
            retrieved_evidence=retrieved_evidence,
            source_citations=source_citations,
            confidence=values.get("confidence"),
            approval_required=values.get("approval_required", False),
            approval_status=values.get("approval_status", "not_required"),
            approval_reason=values.get("approval_reason"),
            approval_notes=values.get("approval_notes"),
            approval_request=(
                pending_interrupt
                if status == "waiting_for_approval" and isinstance(pending_interrupt, dict)
                else None
            ),
            audit_trail=audit_trail,
            retrieval_status=values.get("retrieval_status", "not_used"),
            tool_results=tool_results,
            retrieved_chunks=retrieved_chunks,
            final_report=values.get("final_report"),
            root_cause_diagnostics=values.get("root_cause_diagnostics"),
            errors=errors,
        )

    @staticmethod
    def _failed_task(snapshot):
        return next(
            (
                task
                for task in snapshot.tasks
                if getattr(task, "error", None)
            ),
            None,
        )

    @staticmethod
    def _current_step_from_snapshot(snapshot) -> str:
        values = dict(snapshot.values or {})
        if snapshot.next:
            return snapshot.next[0]
        return values.get("current_step", "completed")

    @staticmethod
    def _dedupe_tool_results(tool_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
        deduped: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()

        for item in tool_results:
            name = str(item.get("name", "")).strip()
            arguments = item.get("arguments", {})
            key = (name, json.dumps(arguments, sort_keys=True))
            if key in seen:
                continue
            seen.add(key)
            deduped.append(item)

        return deduped

    @staticmethod
    def _derive_top_error_lines(tool_results: list[dict[str, Any]]) -> list[str]:
        candidates: list[str] = []
        for item in tool_results:
            payload = item.get("payload", {})
            for key in ("selected_lines", "matched_lines", "new_error_lines"):
                value = payload.get(key, [])
                if not isinstance(value, list):
                    continue
                candidates.extend(
                    str(line).strip()
                    for line in value
                    if isinstance(line, str) and looks_like_error(line)
                )
        return dedupe_preserve_order(candidates)[:5]

    @staticmethod
    def _derive_source_citations(
        *,
        tool_results: list[dict[str, Any]],
        retrieved_chunks: list[dict[str, Any]],
    ) -> list[str]:
        citations: list[str] = []

        for item in tool_results:
            name = str(item.get("name", "")).strip()
            payload = item.get("payload", {})
            if name == "read_log_file" and payload.get("path"):
                citations.append(f"{name}:{payload['path']}")
            elif name == "compare_two_logs" and payload.get("path_a") and payload.get("path_b"):
                citations.append(f"{name}:{payload['path_a']}->{payload['path_b']}")
            elif name == "load_incident_template" and payload.get("incident_type"):
                citations.append(f"{name}:{payload['incident_type']}")
            elif not item.get("ok", True):
                citations.append(f"{name}:safe_failure")

        citations.extend(
            str(chunk.get("citation", "")).strip()
            for chunk in retrieved_chunks
            if str(chunk.get("citation", "")).strip()
        )
        return dedupe_preserve_order(citations)[:8]

    @staticmethod
    def _derive_retrieved_evidence(retrieved_chunks: list[dict[str, Any]]) -> list[str]:
        snippets = [
            str(chunk.get("snippet", "")).strip()
            for chunk in retrieved_chunks
            if str(chunk.get("snippet", "")).strip()
        ]
        return dedupe_preserve_order(snippets)[:5]

    @staticmethod
    def _normalize_error_message(error: object) -> str:
        if isinstance(error, BaseException):
            message = str(error).strip() or error.__class__.__name__
        else:
            message = str(error).strip()

        wrapped = re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*(?:Error|Exception)\((['\"])(.*)\1\)", message)
        if wrapped:
            message = wrapped.group(2).strip()
        return message

    @staticmethod
    def _stage_from_snapshot(*, status: str, current_step: str) -> str:
        if status == "waiting_for_approval":
            return "awaiting_approval"
        if status == "completed":
            return "completed"
        if status == "failed":
            return "failed"

        step_to_stage = {
            "intake_node": "intake",
            "incident_classifier_node": "classify_incident",
            "tool_evidence_node": "gather_evidence",
            "retrieval_node": "retrieve_supporting_docs",
            "causal_analysis_node": "analyze_root_cause",
            "hypothesis_node": "draft_hypothesis",
            "remediation_node": "draft_remediation",
            "approval_node": "awaiting_approval",
            "final_report_node": "completed",
        }
        return step_to_stage.get(current_step, "intake")

    def _record_audit_event(
        self,
        *,
        thread_id: str,
        action: str,
        payload: dict[str, object],
        status_after: str,
        request_id: str | None,
        actor: AuthenticatedUser | None,
    ) -> None:
        if self.audit_trail is None:
            return
        decision = str(payload.get("decision", "approved")).strip().lower() or "approved"
        review_notes = str(payload.get("review_notes", "")).strip() or None
        raw_plan = payload.get("edited_remediation_plan") or []
        edited_plan = [
            str(item).strip()
            for item in raw_plan
            if isinstance(raw_plan, list) and str(item).strip()
        ]
        self.audit_trail.record_event(
            thread_id=thread_id,
            action=action,
            decision=decision,
            review_notes=review_notes,
            edited_remediation_plan=edited_plan,
            status_after=status_after,
            request_id=request_id,
            actor=actor,
        )

    def _audit_events(self, thread_id: str) -> list[dict[str, Any]]:
        if self.audit_trail is None:
            return []
        return [
            event.model_dump(mode="json")
            for event in self.audit_trail.list_events(thread_id)
        ]

    def _record_thread_snapshot(
        self,
        response: WorkflowThreadResponse,
        *,
        actor: AuthenticatedUser | None,
    ) -> None:
        if self.thread_store is None:
            return
        self.thread_store.record_thread_snapshot(thread=response, actor=actor)
