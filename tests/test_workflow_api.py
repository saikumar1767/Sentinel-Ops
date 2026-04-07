import json
import shutil

from fastapi.testclient import TestClient

from app.audit import WorkflowAuditTrail
from app.dependencies import get_workflow_service
from app.main import app
from app.ollama_client import ChatTurn, ToolCallSpec
from app.schemas import RetrievalHit
from app.services.workflow_service import WorkflowService
from app.settings import PROJECT_ROOT, Settings
from app.tools.file_tools import FileTools
from app.tools.incident_tools import IncidentTools
from app.tools.tool_registry import ToolRegistry


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


class WorkflowGateway:
    def chat(self, *, model, messages, tools=None, format=None):
        if tools is not None:
            return ChatTurn(
                content="enough evidence",
                message={"role": "assistant", "content": "enough evidence"},
                tool_calls=[],
            )

        payload = {
            "incident_type": "database",
            "severity": "high",
            "top_error_lines": [],
            "suspected_root_cause": "connection pool exhaustion on primary-postgres after retries",
            "next_steps": [],
            "manager_summary": "Database is failing during startup after repeated timeout symptoms.",
            "retrieved_evidence": [],
            "source_citations": [],
            "confidence": 0.62,
        }
        body = json.dumps(payload)
        return ChatTurn(
            content=body,
            message={"role": "assistant", "content": body},
            tool_calls=[],
        )


class FailingWorkflowGateway:
    def chat(self, *, model, messages, tools=None, format=None):
        if tools is not None:
            return ChatTurn(
                content="enough evidence",
                message={"role": "assistant", "content": "enough evidence"},
                tool_calls=[],
            )
        raise RuntimeError("workflow model synthesis failed")


class RepeatingCompareWorkflowGateway:
    def __init__(self) -> None:
        self._planner_invoked = False

    def chat(self, *, model, messages, tools=None, format=None):
        if tools is not None:
            if not self._planner_invoked:
                self._planner_invoked = True
                tool_call = ToolCallSpec(
                    name="compare_two_logs",
                    arguments={
                        "path_a": "data/logs/database-previous.log",
                        "path_b": "data/logs/database-current.log",
                    },
                )
                return ChatTurn(
                    content="",
                    message={
                        "role": "assistant",
                        "content": "",
                        "tool_calls": [
                            {
                                "function": {
                                    "name": tool_call.name,
                                    "arguments": tool_call.arguments,
                                }
                            }
                        ],
                    },
                    tool_calls=[tool_call],
                )

            return ChatTurn(
                content="enough evidence",
                message={"role": "assistant", "content": "enough evidence"},
                tool_calls=[],
            )

        payload = {
            "incident_type": "database",
            "severity": "high",
            "top_error_lines": [],
            "suspected_root_cause": "connection pool exhaustion on primary-postgres after retries",
            "next_steps": [],
            "manager_summary": "Database is failing during startup after repeated timeout symptoms.",
            "retrieved_evidence": [],
            "source_citations": [],
            "confidence": 0.62,
        }
        body = json.dumps(payload)
        return ChatTurn(
            content=body,
            message={"role": "assistant", "content": body},
            tool_calls=[],
        )


def build_workflow_service(tmp_path, *, gateway=None, retriever=None, audit_trail=None) -> WorkflowService:
    history_dir = tmp_path / "recent_incidents"
    shutil.copytree(PROJECT_ROOT / "data" / "recent_incidents", history_dir)

    settings = Settings(
        allowed_log_roots=[PROJECT_ROOT / "samples", PROJECT_ROOT / "data" / "logs"],
        incident_templates_dir=PROJECT_ROOT / "data" / "incident_templates",
        incident_history_dir=history_dir,
        workflow_checkpoint_path=tmp_path / "workflow" / "checkpoints.sqlite",
    )
    registry = ToolRegistry(
        file_tools=FileTools(settings),
        incident_tools=IncidentTools(settings),
        settings=settings,
    )
    return WorkflowService(
        settings=settings,
        gateway=gateway or WorkflowGateway(),
        tool_registry=registry,
        retriever=retriever or StubRetriever(),
        audit_trail=audit_trail,
    )


def test_workflow_investigate_completes_without_approval_when_disabled(tmp_path) -> None:
    service = build_workflow_service(tmp_path)
    app.dependency_overrides[get_workflow_service] = lambda: service
    client = TestClient(app)

    try:
        response = client.post(
            "/workflow/investigate",
            json={
                "prompt": "Investigate this incident using the failing run and the previous healthy run.",
                "candidate_log_paths": [
                    "data/logs/database-current.log",
                    "data/logs/database-previous.log",
                ],
                "incident_type_hint": "database",
                "require_approval_for_remediation": False,
            },
        )
    finally:
        app.dependency_overrides.clear()
        service.close()

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "completed"
    assert payload["current_stage"] == "completed"
    assert payload["available_actions"] == []
    assert payload["approval_required"] is False
    assert payload["approval_status"] == "not_required"
    assert payload["final_report"] is not None
    assert payload["final_report"]["incident_type"] == "database"
    assert payload["final_report"]["retrieval_status"] == "used"
    assert payload["final_report"]["remediation_plan"]
    assert payload["tool_results"]
    assert payload["tool_results"][0]["cached"] is False
    assert payload["tool_results"][0]["name"] == "read_log_file"
    assert "payload" in payload["tool_results"][0]


def test_workflow_investigate_pauses_and_get_returns_pending_state(tmp_path) -> None:
    service = build_workflow_service(tmp_path)
    app.dependency_overrides[get_workflow_service] = lambda: service
    client = TestClient(app)

    try:
        start_response = client.post(
            "/workflow/investigate",
            json={
                "prompt": "Investigate this incident using the failing run and the previous healthy run.",
                "candidate_log_paths": [
                    "data/logs/database-current.log",
                    "data/logs/database-previous.log",
                ],
                "incident_type_hint": "database",
            },
        )
        thread_id = start_response.json()["thread_id"]
        state_response = client.get(f"/workflow/{thread_id}")
    finally:
        app.dependency_overrides.clear()
        service.close()

    assert start_response.status_code == 200
    start_payload = start_response.json()
    assert start_payload["status"] == "waiting_for_approval"
    assert start_payload["current_stage"] == "awaiting_approval"
    assert start_payload["current_step"] == "approval_node"
    assert start_payload["available_actions"] == ["approve", "reject", "resume"]
    assert start_payload["approval_required"] is True
    assert start_payload["approval_status"] == "pending"
    assert start_payload["approval_request"]["type"] == "approval_required"
    assert start_payload["approval_request"]["proposed_remediation_plan"]
    assert all(not record["cached"] for record in start_payload["tool_results"])
    assert state_response.status_code == 200
    assert state_response.json()["thread_id"] == thread_id
    assert state_response.json()["status"] == "waiting_for_approval"


def test_workflow_approve_endpoint_resumes_and_completes(tmp_path) -> None:
    service = build_workflow_service(tmp_path)
    app.dependency_overrides[get_workflow_service] = lambda: service
    client = TestClient(app)

    try:
        start_response = client.post(
            "/workflow/investigate",
            json={
                "prompt": "Investigate this incident using the failing run and the previous healthy run.",
                "candidate_log_paths": [
                    "data/logs/database-current.log",
                    "data/logs/database-previous.log",
                ],
                "incident_type_hint": "database",
            },
        )
        thread_id = start_response.json()["thread_id"]
        approve_response = client.post(
            f"/workflow/{thread_id}/approve",
            json={"review_notes": "Approved for the on-call team to execute."},
        )
    finally:
        app.dependency_overrides.clear()
        service.close()

    assert approve_response.status_code == 200
    payload = approve_response.json()
    assert payload["status"] == "completed"
    assert payload["current_stage"] == "completed"
    assert payload["available_actions"] == []
    assert payload["approval_status"] == "approved"
    assert payload["approval_notes"] == "Approved for the on-call team to execute."
    assert payload["final_report"] is not None
    assert payload["final_report"]["approval_status"] == "approved"
    assert "Approval was granted" in payload["final_report"]["engineer_summary"]
    assert ".." not in payload["engineer_summary"]
    assert ".." not in payload["final_report"]["engineer_summary"]


def test_workflow_reject_endpoint_can_replace_remediation_plan(tmp_path) -> None:
    service = build_workflow_service(tmp_path)
    app.dependency_overrides[get_workflow_service] = lambda: service
    client = TestClient(app)
    edited_plan = [
        "Freeze deploys touching the checkout service until the database saturation is verified.",
        "Page the database owner and confirm a safe rollback or failover path before restarting workers.",
    ]

    try:
        start_response = client.post(
            "/workflow/investigate",
            json={
                "prompt": "Investigate this incident using the failing run and the previous healthy run.",
                "candidate_log_paths": [
                    "data/logs/database-current.log",
                    "data/logs/database-previous.log",
                ],
                "incident_type_hint": "database",
            },
        )
        thread_id = start_response.json()["thread_id"]
        reject_response = client.post(
            f"/workflow/{thread_id}/reject",
            json={
                "reason": "Use a safer reviewed checklist before making runtime changes.",
                "edited_remediation_plan": edited_plan,
            },
        )
    finally:
        app.dependency_overrides.clear()
        service.close()

    assert reject_response.status_code == 200
    payload = reject_response.json()
    assert payload["status"] == "completed"
    assert payload["current_stage"] == "completed"
    assert payload["available_actions"] == []
    assert payload["approval_status"] == "rejected"
    assert payload["approval_notes"] == "Use a safer reviewed checklist before making runtime changes."
    assert payload["remediation_plan"] == edited_plan
    assert payload["final_report"]["approval_status"] == "rejected"
    assert payload["final_report"]["remediation_plan"] == edited_plan


def test_workflow_failure_is_persisted_as_failed_thread_state(tmp_path) -> None:
    service = build_workflow_service(tmp_path, gateway=FailingWorkflowGateway())
    app.dependency_overrides[get_workflow_service] = lambda: service
    client = TestClient(app)

    try:
        start_response = client.post(
            "/workflow/investigate",
            json={
                "thread_id": "workflow-failure-demo",
                "prompt": "Investigate this incident using the failing run and the previous healthy run.",
                "candidate_log_paths": [
                    "data/logs/database-current.log",
                    "data/logs/database-previous.log",
                ],
                "incident_type_hint": "database",
            },
        )
        state_response = client.get("/workflow/workflow-failure-demo")
    finally:
        app.dependency_overrides.clear()
        service.close()

    assert start_response.status_code == 200
    payload = start_response.json()
    assert payload["status"] == "failed"
    assert payload["current_stage"] == "failed"
    assert payload["available_actions"] == []
    assert payload["current_step"] == "hypothesis_node"
    assert payload["severity"] == "high"
    assert payload["top_error_lines"]
    assert payload["retrieved_evidence"]
    assert payload["source_citations"]
    assert payload["final_report"] is None
    assert payload["errors"] == ["workflow model synthesis failed"]
    assert state_response.status_code == 200
    assert state_response.json()["status"] == "failed"


def test_workflow_cannot_resume_completed_thread(tmp_path) -> None:
    service = build_workflow_service(tmp_path)
    app.dependency_overrides[get_workflow_service] = lambda: service
    client = TestClient(app)

    try:
        start_response = client.post(
            "/workflow/investigate",
            json={
                "thread_id": "workflow-complete-demo",
                "prompt": "Investigate this incident using the failing run and the previous healthy run.",
                "candidate_log_paths": [
                    "data/logs/database-current.log",
                    "data/logs/database-previous.log",
                ],
                "incident_type_hint": "database",
                "require_approval_for_remediation": False,
            },
        )
        resume_response = client.post(
            "/workflow/workflow-complete-demo/resume",
            json={"decision": "approved"},
        )
    finally:
        app.dependency_overrides.clear()
        service.close()

    assert start_response.status_code == 200
    assert start_response.json()["status"] == "completed"
    assert resume_response.status_code == 409
    assert resume_response.headers["content-type"].startswith("application/problem+json")
    payload = resume_response.json()
    assert payload["status"] == 409
    assert payload["code"] == "workflow_thread_conflict"
    assert "already complete" in payload["detail"]
    assert payload["thread_id"] == "workflow-complete-demo"


def test_workflow_tool_results_deduplicate_cached_replays(tmp_path) -> None:
    service = build_workflow_service(tmp_path, gateway=RepeatingCompareWorkflowGateway())
    app.dependency_overrides[get_workflow_service] = lambda: service
    client = TestClient(app)

    try:
        response = client.post(
            "/workflow/investigate",
            json={
                "thread_id": "workflow-dedup-demo",
                "prompt": "Investigate this incident using the failing run and the previous healthy run.",
                "candidate_log_paths": [
                    "data/logs/database-current.log",
                    "data/logs/database-previous.log",
                ],
                "incident_type_hint": "database",
                "require_approval_for_remediation": False,
            },
        )
    finally:
        app.dependency_overrides.clear()
        service.close()

    assert response.status_code == 200
    payload = response.json()
    compare_results = [record for record in payload["tool_results"] if record["name"] == "compare_two_logs"]
    assert len(compare_results) == 1
    assert compare_results[0]["cached"] is False


def test_workflow_missing_thread_returns_problem_details(tmp_path) -> None:
    service = build_workflow_service(tmp_path)
    app.dependency_overrides[get_workflow_service] = lambda: service
    client = TestClient(app)

    try:
        response = client.get("/workflow/workflow-missing")
    finally:
        app.dependency_overrides.clear()
        service.close()

    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/problem+json")
    payload = response.json()
    assert payload["title"] == "Workflow thread not found"
    assert payload["status"] == 404
    assert payload["code"] == "workflow_thread_not_found"
    assert payload["thread_id"] == "workflow-missing"
    assert payload["detail"] == "Workflow thread 'workflow-missing' was not found."


def test_workflow_start_duplicate_thread_returns_problem_details(tmp_path) -> None:
    service = build_workflow_service(tmp_path)
    app.dependency_overrides[get_workflow_service] = lambda: service
    client = TestClient(app)

    try:
        first = client.post(
            "/workflow/investigate",
            json={
                "thread_id": "workflow-duplicate-demo",
                "prompt": "Investigate this incident using the failing run and the previous healthy run.",
                "candidate_log_paths": [
                    "data/logs/database-current.log",
                    "data/logs/database-previous.log",
                ],
                "incident_type_hint": "database",
            },
        )
        second = client.post(
            "/workflow/investigate",
            json={
                "thread_id": "workflow-duplicate-demo",
                "prompt": "Investigate this incident using the failing run and the previous healthy run.",
                "candidate_log_paths": [
                    "data/logs/database-current.log",
                    "data/logs/database-previous.log",
                ],
                "incident_type_hint": "database",
            },
        )
    finally:
        app.dependency_overrides.clear()
        service.close()

    assert first.status_code == 200
    assert second.status_code == 409
    payload = second.json()
    assert payload["code"] == "workflow_thread_conflict"
    assert payload["thread_id"] == "workflow-duplicate-demo"
    assert "already exists" in payload["detail"]


def test_workflow_audit_trail_records_approval_events(tmp_path) -> None:
    audit_trail = WorkflowAuditTrail(Settings(audit_db_path=tmp_path / "audit" / "audit.sqlite"))
    service = build_workflow_service(tmp_path, audit_trail=audit_trail)
    app.dependency_overrides[get_workflow_service] = lambda: service
    client = TestClient(app)

    try:
        start = client.post(
            "/workflow/investigate",
            json={
                "thread_id": "workflow-audit-demo",
                "prompt": "Investigate this incident using the failing run and the previous healthy run.",
                "candidate_log_paths": [
                    "data/logs/database-current.log",
                    "data/logs/database-previous.log",
                ],
                "incident_type_hint": "database",
            },
        )
        approve = client.post(
            "/workflow/workflow-audit-demo/approve",
            json={"review_notes": "Approved by incident manager."},
        )
        audit = client.get("/workflow/workflow-audit-demo/audit")
    finally:
        app.dependency_overrides.clear()
        service.close()

    assert start.status_code == 200
    assert approve.status_code == 200
    assert audit.status_code == 200
    payload = audit.json()
    assert payload["total_events"] == 1
    event = payload["events"][0]
    assert event["decision"] == "approved"
    assert event["action"] == "approve"
    assert event["review_notes"] == "Approved by incident manager."


def test_workflow_audit_trail_records_reject_event(tmp_path) -> None:
    audit_trail = WorkflowAuditTrail(Settings(audit_db_path=tmp_path / "audit" / "audit.sqlite"))
    service = build_workflow_service(tmp_path, audit_trail=audit_trail)
    app.dependency_overrides[get_workflow_service] = lambda: service
    client = TestClient(app)

    try:
        start = client.post(
            "/workflow/investigate",
            json={
                "thread_id": "workflow-anonymous-audit-demo",
                "prompt": "Investigate this incident using the failing run and the previous healthy run.",
                "candidate_log_paths": [
                    "data/logs/database-current.log",
                    "data/logs/database-previous.log",
                ],
                "incident_type_hint": "database",
            },
        )
        reject = client.post(
            "/workflow/workflow-anonymous-audit-demo/reject",
            json={"reason": "Rejected during anonymous audit coverage."},
        )
        audit = client.get("/workflow/workflow-anonymous-audit-demo/audit")
    finally:
        app.dependency_overrides.clear()
        service.close()

    assert start.status_code == 200
    assert reject.status_code == 200
    assert audit.status_code == 200
    payload = audit.json()
    assert payload["total_events"] == 1
    event = payload["events"][0]
    assert event["decision"] == "rejected"
    assert event["action"] == "reject"
    assert event["review_notes"] == "Rejected during anonymous audit coverage."


def test_workflow_swagger_docs_document_problem_responses_and_examples(tmp_path) -> None:
    service = build_workflow_service(tmp_path)
    app.dependency_overrides[get_workflow_service] = lambda: service
    client = TestClient(app)

    try:
        docs_response = client.get("/docs")
        openapi = client.get("/openapi.json").json()
    finally:
        app.dependency_overrides.clear()
        service.close()

    assert docs_response.status_code == 200
    assert "Swagger UI" in docs_response.text
    assert "ProblemDetailResponse" in openapi["components"]["schemas"]

    start_post = openapi["paths"]["/workflow/investigate"]["post"]
    inspect_get = openapi["paths"]["/workflow/{thread_id}"]["get"]
    audit_get = openapi["paths"]["/workflow/{thread_id}/audit"]["get"]
    resume_post = openapi["paths"]["/workflow/{thread_id}/resume"]["post"]
    approve_post = openapi["paths"]["/workflow/{thread_id}/approve"]["post"]
    reject_post = openapi["paths"]["/workflow/{thread_id}/reject"]["post"]

    assert "409" in start_post["responses"]
    assert "503" in start_post["responses"]
    assert start_post["requestBody"]["content"]["application/json"]["schema"]["$ref"].endswith("/WorkflowInvestigateRequest")

    inspect_404_content = inspect_get["responses"]["404"]["content"]
    assert "application/problem+json" in inspect_404_content
    inspect_404_schema = next(iter(inspect_404_content.values()))["schema"]["$ref"]
    assert inspect_404_schema.endswith("/ProblemDetailResponse")
    assert audit_get["responses"]["200"]["content"]["application/json"]["schema"]["$ref"].endswith("/WorkflowAuditResponse")

    assert "409" in resume_post["responses"]
    resume_409_content = resume_post["responses"]["409"]["content"]
    assert "application/problem+json" in resume_409_content
    resume_409_schema = next(iter(resume_409_content.values()))["schema"]["$ref"]
    assert resume_409_schema.endswith("/ProblemDetailResponse")
    assert resume_post["requestBody"]["content"]["application/json"]["schema"]["$ref"].endswith("/WorkflowResumeRequest")
    assert approve_post["requestBody"]["content"]["application/json"]["schema"]["$ref"].endswith("/WorkflowApproveRequest")
    assert reject_post["requestBody"]["content"]["application/json"]["schema"]["$ref"].endswith("/WorkflowRejectRequest")


def test_workflow_response_contract_is_consistent_across_states(tmp_path) -> None:
    service = build_workflow_service(tmp_path)
    failing_service = build_workflow_service(tmp_path / "failing", gateway=FailingWorkflowGateway())
    app.dependency_overrides[get_workflow_service] = lambda: service
    client = TestClient(app)

    expected_thread_keys = {
        "thread_id",
        "request_id",
        "status",
        "current_stage",
        "current_step",
        "available_actions",
        "checkpoint_id",
        "checkpoint_created_at",
        "input_summary",
        "incident_type",
        "severity",
        "suspected_root_cause",
        "remediation_plan",
        "top_error_lines",
        "engineer_summary",
        "manager_summary",
        "retrieved_evidence",
        "source_citations",
        "confidence",
        "approval_required",
        "approval_status",
        "approval_reason",
        "approval_notes",
        "approval_request",
        "audit_trail",
        "retrieval_status",
        "tool_results",
        "retrieved_chunks",
        "final_report",
        "errors",
    }
    expected_problem_keys = {"type", "title", "status", "detail", "instance", "code", "thread_id"}

    try:
        pending = client.post(
            "/workflow/investigate",
            json={
                "thread_id": "workflow-contract-audit",
                "prompt": "Investigate this incident using the failing run and the previous healthy run.",
                "candidate_log_paths": [
                    "data/logs/database-current.log",
                    "data/logs/database-previous.log",
                ],
                "incident_type_hint": "database",
            },
        ).json()
        approved = client.post(
            "/workflow/workflow-contract-audit/approve",
            json={"review_notes": "Approved for execution."},
        ).json()
        no_approval = client.post(
            "/workflow/investigate",
            json={
                "thread_id": "workflow-contract-complete",
                "prompt": "Investigate this incident using the failing run and the previous healthy run.",
                "candidate_log_paths": [
                    "data/logs/database-current.log",
                    "data/logs/database-previous.log",
                ],
                "incident_type_hint": "database",
                "require_approval_for_remediation": False,
            },
        ).json()
        conflict = client.post(
            "/workflow/workflow-contract-complete/resume",
            json={"decision": "approved"},
        ).json()
        missing = client.get("/workflow/workflow-contract-missing").json()

        app.dependency_overrides[get_workflow_service] = lambda: failing_service
        failed_client = TestClient(app)
        failed = failed_client.post(
            "/workflow/investigate",
            json={
                "thread_id": "workflow-contract-failed",
                "prompt": "Investigate this incident using the failing run and the previous healthy run.",
                "candidate_log_paths": [
                    "data/logs/database-current.log",
                    "data/logs/database-previous.log",
                ],
                "incident_type_hint": "database",
            },
        ).json()
    finally:
        app.dependency_overrides.clear()
        service.close()
        failing_service.close()

    for payload in (pending, approved, no_approval, failed):
        assert set(payload.keys()) == expected_thread_keys
        assert payload["checkpoint_id"]
        assert payload["checkpoint_created_at"]
        assert payload["thread_id"].startswith("workflow-")
        assert payload["request_id"]
        assert isinstance(payload["tool_results"], list)
        assert isinstance(payload["retrieved_chunks"], list)
        assert isinstance(payload["errors"], list)

    assert pending["status"] == "waiting_for_approval"
    assert pending["current_stage"] == "awaiting_approval"
    assert pending["approval_required"] is True
    assert pending["approval_status"] == "pending"
    assert pending["audit_trail"] == []
    assert pending["approval_request"] is not None
    assert pending["approval_request"]["proposed_remediation_plan"] == pending["remediation_plan"]
    assert pending["approval_request"]["source_citations"] == pending["source_citations"]
    assert pending["final_report"] is None

    assert approved["status"] == "completed"
    assert approved["current_stage"] == "completed"
    assert approved["approval_request"] is None
    assert approved["approval_status"] == "approved"
    assert approved["audit_trail"] == []
    assert approved["final_report"] is not None
    assert approved["final_report"]["incident_type"] == approved["incident_type"]
    assert approved["final_report"]["severity"] == approved["severity"]
    assert approved["final_report"]["top_error_lines"] == approved["top_error_lines"]
    assert approved["final_report"]["remediation_plan"] == approved["remediation_plan"]
    assert approved["final_report"]["manager_summary"] == approved["manager_summary"]
    assert approved["final_report"]["retrieved_evidence"] == approved["retrieved_evidence"]
    assert approved["final_report"]["source_citations"] == approved["source_citations"]
    assert approved["final_report"]["approval_status"] == approved["approval_status"]
    assert approved["final_report"]["approval_notes"] == approved["approval_notes"]

    assert no_approval["status"] == "completed"
    assert no_approval["approval_required"] is False
    assert no_approval["approval_status"] == "not_required"
    assert no_approval["approval_reason"] is None
    assert no_approval["approval_notes"] is None
    assert no_approval["approval_request"] is None
    assert no_approval["final_report"]["approval_status"] == "not_required"

    assert failed["status"] == "failed"
    assert failed["current_stage"] == "failed"
    assert failed["approval_request"] is None
    assert failed["final_report"] is None
    assert failed["errors"] == ["workflow model synthesis failed"]
    assert failed["top_error_lines"]
    assert failed["source_citations"]
    assert failed["retrieved_evidence"]

    for payload in (conflict, missing):
        assert set(payload.keys()) == expected_problem_keys
        assert payload["type"].startswith("urn:sentinelops:problem:")
        assert payload["status"] in {404, 409}
        assert payload["code"].startswith("workflow_thread_")
