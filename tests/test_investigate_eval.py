import json
import shutil

import pytest
from fastapi.testclient import TestClient

from app.dependencies import get_investigation_service
from app.evaluation import load_investigation_eval_cases, score_investigation_response
from app.main import app
from app.ollama_client import ChatTurn, ToolCallSpec
from app.schemas import InvestigateRequest
from app.services.investigation_service import InvestigationService
from app.settings import PROJECT_ROOT, Settings
from app.tools.file_tools import FileTools
from app.tools.incident_tools import IncidentTools
from app.tools.tool_registry import ToolRegistry

CASES = load_investigation_eval_cases()


class ScriptedGateway:
    def __init__(self, case):
        self.case = case
        self.pending_rounds = [
            [ToolCallSpec(name=plan.name, arguments=plan.arguments) for plan in tool_round]
            for tool_round in case.tool_rounds
        ]
        self.final_payload = json.dumps(case.final_response.model_dump())
        self.final_call_count = 0
        self.max_tool_message_count = 0

    def chat(self, *, model, messages, tools=None, format=None):
        tool_message_count = sum(1 for message in messages if message.get("role") == "tool")
        self.max_tool_message_count = max(self.max_tool_message_count, tool_message_count)

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

        self.final_call_count += 1
        return ChatTurn(
            content=self.final_payload,
            message={"role": "assistant", "content": self.final_payload},
            tool_calls=[],
        )


def build_investigation_service(case, tmp_path):
    history_dir = tmp_path / "recent_incidents"
    shutil.copytree(PROJECT_ROOT / "data" / "recent_incidents", history_dir)

    settings = Settings(
        allowed_log_roots=[PROJECT_ROOT / "samples", PROJECT_ROOT / "data" / "logs"],
        incident_templates_dir=PROJECT_ROOT / "data" / "incident_templates",
        incident_history_dir=history_dir,
    )
    gateway = ScriptedGateway(case)
    registry = ToolRegistry(
        file_tools=FileTools(settings),
        incident_tools=IncidentTools(settings),
        settings=settings,
    )
    service = InvestigationService(
        settings=settings,
        gateway=gateway,
        tool_registry=registry,
    )
    return service, gateway, history_dir


def build_service_with_gateway(gateway, tmp_path):
    history_dir = tmp_path / "recent_incidents"
    shutil.copytree(PROJECT_ROOT / "data" / "recent_incidents", history_dir)

    settings = Settings(
        allowed_log_roots=[PROJECT_ROOT / "samples", PROJECT_ROOT / "data" / "logs"],
        incident_templates_dir=PROJECT_ROOT / "data" / "incident_templates",
        incident_history_dir=history_dir,
    )
    registry = ToolRegistry(
        file_tools=FileTools(settings),
        incident_tools=IncidentTools(settings),
        settings=settings,
    )
    service = InvestigationService(
        settings=settings,
        gateway=gateway,
        tool_registry=registry,
    )
    return service


@pytest.mark.parametrize("case", CASES, ids=[case.id for case in CASES])
def test_investigate_eval_cases(case, tmp_path) -> None:
    service, gateway, history_dir = build_investigation_service(case, tmp_path)
    seed_count = len(list(history_dir.glob("*.json")))

    app.dependency_overrides[get_investigation_service] = lambda: service
    client = TestClient(app)

    try:
        response = client.post(
            "/investigate",
            json={
                "prompt": case.prompt,
                "candidate_log_paths": case.candidate_log_paths,
                "incident_type_hint": case.incident_type_hint,
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()

    failures = score_investigation_response(case, payload)
    assert not failures, f"{case.id} failed: {', '.join(failures)}"

    total_tool_calls = sum(len(tool_round) for tool_round in case.tool_rounds)
    assert gateway.max_tool_message_count >= total_tool_calls
    assert gateway.final_call_count == 1
    assert len(list(history_dir.glob("*.json"))) == seed_count + 1


def test_investigate_rejects_empty_prompt() -> None:
    client = TestClient(app)
    response = client.post("/investigate", json={"prompt": ""})

    assert response.status_code == 422


class NoToolGenericFinalGateway:
    def chat(self, *, model, messages, tools=None, format=None):
        if tools is not None:
            return ChatTurn(
                content="enough evidence",
                message={"role": "assistant", "content": "enough evidence"},
                tool_calls=[],
            )

        payload = {
            "incident_type": "database",
            "severity": "medium",
            "top_error_lines": [],
            "suspected_root_cause": "Active saturation symptoms and potential connection pool issues",
            "next_steps": [],
            "manager_summary": "Database is experiencing active saturation symptoms, which may be related to connection pool health.",
            "evidence_used": ["load_incident_template for database"],
            "confidence": 0.6,
        }
        body = json.dumps(payload)
        return ChatTurn(
            content=body,
            message={"role": "assistant", "content": body},
            tool_calls=[],
        )


def test_investigate_collects_baseline_log_evidence_even_without_planner_tools(tmp_path) -> None:
    service = build_service_with_gateway(NoToolGenericFinalGateway(), tmp_path)

    response = service.investigate(
        InvestigateRequest(
            prompt="Investigate this incident.",
            candidate_log_paths=[
                "data/logs/database-current.log",
                "data/logs/database-previous.log",
            ],
            incident_type_hint="database",
        )
    )

    assert response.incident_type == "database"
    assert response.top_error_lines
    assert response.top_error_lines[0].startswith("1: 2026-03-31 09:10:22 ERROR")
    assert any("connection pool exhausted" in line for line in response.top_error_lines)
    assert "No concrete error lines were captured from the available evidence." not in response.top_error_lines
    assert "read_log_file:data/logs/database-current.log" in response.evidence_used
    assert (
        "compare_two_logs:data/logs/database-previous.log->data/logs/database-current.log"
        in response.evidence_used
    )
    assert response.next_steps
    assert response.next_steps[0].startswith("Confirm database reachability")
