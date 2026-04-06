import json
import shutil

import pytest

from app.evaluation import load_workflow_eval_cases, score_workflow_thread_response
from app.ollama_client import ChatTurn, ToolCallSpec
from app.schemas import (
    RetrievalHit,
    WorkflowApproveRequest,
    WorkflowInvestigateRequest,
    WorkflowRejectRequest,
)
from app.services.workflow_service import WorkflowService
from app.settings import PROJECT_ROOT, Settings
from app.tools.file_tools import FileTools
from app.tools.incident_tools import IncidentTools
from app.tools.tool_registry import ToolRegistry

CASES = load_workflow_eval_cases()


def retrieval_hit_for_database() -> RetrievalHit:
    return RetrievalHit(
        chunk_id="workflow-db-runbook",
        document_type="runbook",
        source_path="data/knowledge/runbooks/database-timeout-runbook.md",
        citation="data/knowledge/runbooks/database-timeout-runbook.md#Symptoms",
        snippet=(
            "Database timeout incidents usually include connection pool exhaustion "
            "or long-running postgres transactions."
        ),
        title="Database timeout runbook",
        section_path="Symptoms",
        incident_type="database",
        similarity_score=0.94,
    )


class StubRetriever:
    def search(self, *, query: str, top_k: int, document_types=None, incident_type_hint=None):
        return [retrieval_hit_for_database()]


class ScriptedWorkflowGateway:
    def __init__(self, case):
        self.pending_rounds = [
            [ToolCallSpec(name=plan.name, arguments=plan.arguments) for plan in tool_round]
            for tool_round in case.tool_rounds
        ]
        self.final_payload = json.dumps(case.final_response.model_dump())

    def chat(self, *, model, messages, tools=None, format=None):
        if tools is not None:
            if self.pending_rounds:
                tool_calls = self.pending_rounds.pop(0)
                tool_call_payload = [
                    {
                        "function": {
                            "name": tool_call.name,
                            "arguments": tool_call.arguments,
                        }
                    }
                    for tool_call in tool_calls
                ]
                return ChatTurn(
                    content="",
                    message={
                        "role": "assistant",
                        "content": "",
                        "tool_calls": tool_call_payload,
                    },
                    tool_calls=tool_calls,
                )

            return ChatTurn(
                content="enough evidence",
                message={"role": "assistant", "content": "enough evidence"},
                tool_calls=[],
            )

        return ChatTurn(
            content=self.final_payload,
            message={"role": "assistant", "content": self.final_payload},
            tool_calls=[],
        )


def build_workflow_service(case, workdir) -> WorkflowService:
    history_dir = workdir / "recent_incidents"
    shutil.copytree(PROJECT_ROOT / "data" / "recent_incidents", history_dir)

    settings = Settings(
        allowed_log_roots=[PROJECT_ROOT / "samples", PROJECT_ROOT / "data" / "logs"],
        incident_templates_dir=PROJECT_ROOT / "data" / "incident_templates",
        incident_history_dir=history_dir,
        workflow_checkpoint_path=workdir / "workflow" / "checkpoints.sqlite",
    )
    registry = ToolRegistry(
        file_tools=FileTools(settings),
        incident_tools=IncidentTools(settings),
        settings=settings,
    )
    return WorkflowService(
        settings=settings,
        gateway=ScriptedWorkflowGateway(case),
        tool_registry=registry,
        retriever=StubRetriever(),
    )


@pytest.mark.parametrize("case", CASES, ids=[case.id for case in CASES])
def test_workflow_eval_cases(case, tmp_path) -> None:
    service = build_workflow_service(case, tmp_path / case.id)

    try:
        response = service.start_investigation(
            WorkflowInvestigateRequest(
                thread_id=case.id,
                prompt=case.prompt,
                candidate_log_paths=case.candidate_log_paths,
                incident_type_hint=case.incident_type_hint,
                require_approval_for_remediation=case.require_approval_for_remediation,
            )
        )

        if case.post_start_action == "approve":
            response = service.approve(
                case.id,
                WorkflowApproveRequest(review_notes=case.review_notes),
            )
        elif case.post_start_action == "reject":
            response = service.reject(
                case.id,
                WorkflowRejectRequest(
                    reason=case.review_notes or "Workflow eval rejection.",
                    edited_remediation_plan=case.edited_remediation_plan,
                ),
            )

        failures = score_workflow_thread_response(case, response.model_dump(mode="json"))
        assert not failures, f"{case.id} failed: {', '.join(failures)}"
    finally:
        service.close()
