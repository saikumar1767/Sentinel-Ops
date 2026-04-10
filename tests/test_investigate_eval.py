import json
import shutil

import pytest
from fastapi.testclient import TestClient
from ollama import RequestError

from app.dependencies import get_investigation_service
from app.evaluation import load_investigation_eval_cases, score_investigation_response
from app.main import app
from app.ollama_client import ChatTurn, ToolCallSpec
from app.schemas import InvestigateRequest, RetrievalHit
from app.services.investigation_service import InvestigationService
from app.settings import PROJECT_ROOT, Settings
from app.tools.file_tools import FileTools
from app.tools.incident_tools import IncidentTools
from app.tools.tool_registry import ToolRegistry

CASES = load_investigation_eval_cases()


def infer_incident_type(text: str) -> str:
    lowered = text.lower()
    if any(token in lowered for token in ("failed login", "credential", "lock threshold")):
        return "authentication"
    if any(token in lowered for token in ("missing env", "missing config", "payment_api_key", "redis_url")):
        return "configuration"
    if any(token in lowered for token in ("database", "pool exhausted", "deadlock", "lock wait timeout")):
        return "database"
    if any(token in lowered for token in ("disk usage", "no space left")):
        return "disk"
    if any(token in lowered for token in ("dns", "resolve", "packet loss", "connection reset")):
        return "network"
    if any(token in lowered for token in ("queue backlog", "consumer lag")):
        return "queue"
    if any(token in lowered for token in ("ransomware", "certificate", "tls handshake")):
        return "security"
    if any(token in lowered for token in ("cpu usage", "latency")):
        return "performance"
    return "service"


def retrieval_hit_for(incident_type: str) -> RetrievalHit:
    snippets = {
        "authentication": "Repeated failed login attempts and rising lock thresholds usually point to credential abuse or stale secrets.",
        "configuration": "Missing environment variables should be fixed before retrying a rollout or service bootstrap.",
        "database": "Database timeout incidents usually include connection pool exhaustion or long-running postgres transactions.",
        "deployment": "Rollouts should pause when readiness probes fail, but missing configuration should be corrected before resuming.",
        "disk": "No space left on device means the host is disk constrained and write-heavy jobs will fail first.",
        "network": "DNS lookup failures and packet loss between subnets indicate a network or resolver issue.",
        "performance": "High CPU and elevated latency indicate service saturation that should be reported as degradation.",
        "queue": "Queue backlog together with consumer lag means throughput is insufficient and the SLA is at risk.",
        "security": "Ransomware signatures or certificate failures should be escalated as security incidents immediately.",
        "service": "Crash loops, segmentation faults, and repeated 502 responses usually point to an unhealthy upstream or binary fault.",
    }
    source_map = {
        "authentication": "data/knowledge/troubleshooting_notes/auth-lockout-note.md#Note",
        "configuration": "data/knowledge/troubleshooting_notes/readiness-missing-config-note.md#Note",
        "database": "data/knowledge/runbooks/database-timeout-runbook.md#Symptoms",
        "deployment": "data/knowledge/runbooks/deployment-readiness-runbook.md#Symptoms",
        "disk": "data/knowledge/troubleshooting_notes/disk-pressure-note.md#Note",
        "network": "data/knowledge/runbooks/network-dns-runbook.md#Symptoms",
        "performance": "data/knowledge/readmes/platform-observability-readme.md#Investigation Guidance",
        "queue": "data/knowledge/runbooks/queue-backlog-runbook.md#Symptoms",
        "security": "data/knowledge/runbooks/security-certificate-runbook.md#Symptoms",
        "service": "data/knowledge/github_issues/worker-segfault-issue.md#Summary",
    }
    return RetrievalHit(
        chunk_id=f"stub-{incident_type}",
        document_type="runbook",
        source_path=source_map[incident_type].split("#", 1)[0],
        citation=source_map[incident_type],
        snippet=snippets[incident_type],
        title=f"{incident_type.title()} knowledge",
        incident_type=incident_type,
        similarity_score=0.93,
    )


class StubRetriever:
    def search(self, *, query: str, top_k: int, document_types=None, incident_type_hint=None):
        incident_type = incident_type_hint or infer_incident_type(query)
        return [retrieval_hit_for(incident_type)]


class MultiHitDatabaseRetriever:
    def search(self, *, query: str, top_k: int, document_types=None, incident_type_hint=None):
        return [
            RetrievalHit(
                chunk_id="incident-template-database",
                document_type="incident_template",
                source_path="data/incident_templates/database.md",
                citation="data/incident_templates/database.md",
                snippet=(
                    "- Confirm database reachability, connection pool health, and active saturation symptoms.\n"
                    "- Check for recent schema changes, failovers, or long-running queries.\n"
                    "- Compare timeouts, deadlocks, and pool exhaustion against prior healthy runs."
                ),
                title="Database incident template",
                incident_type="database",
                similarity_score=0.99,
            ),
            RetrievalHit(
                chunk_id="db-runbook-checks",
                document_type="runbook",
                source_path="data/knowledge/runbooks/database-timeout-runbook.md",
                citation="data/knowledge/runbooks/database-timeout-runbook.md#Checks",
                snippet=(
                    "- Confirm primary postgres reachability and DNS resolution.\n"
                    "- Check connection pool saturation, long transactions, and lock wait time.\n"
                    "- Compare the failing run with the previous healthy log for new timeout lines."
                ),
                title="Database timeout runbook",
                section_path="Checks",
                incident_type="database",
                similarity_score=0.97,
            ),
            RetrievalHit(
                chunk_id="db-runbook-symptoms",
                document_type="runbook",
                source_path="data/knowledge/runbooks/database-timeout-runbook.md",
                citation="data/knowledge/runbooks/database-timeout-runbook.md#Symptoms",
                snippet=(
                    "Database timeout incidents usually include connection pool exhaustion or long-running "
                    "postgres transactions."
                ),
                title="Database timeout runbook",
                section_path="Symptoms",
                incident_type="database",
                similarity_score=0.96,
            ),
            RetrievalHit(
                chunk_id="payments-readme-operational-notes",
                document_type="readme",
                source_path="data/knowledge/readmes/payments-service-readme.md",
                citation="data/knowledge/readmes/payments-service-readme.md#Operational Notes",
                snippet=(
                    "When pool exhaustion occurs, checkout requests stall before downstream billing work begins. "
                    "The first signs are database timeout lines, retries, and warnings about waiting for a free connection."
                ),
                title="Payments service README",
                section_path="Operational Notes",
                incident_type="database",
                similarity_score=0.91,
            ),
        ]


class FailingRetriever:
    def search(self, *, query: str, top_k: int, document_types=None, incident_type_hint=None):
        raise RuntimeError("retrieval backend unavailable")


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
    history_dir = tmp_path / "reference_incidents"
    shutil.copytree(PROJECT_ROOT / "data" / "reference_incidents", history_dir)

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
        retriever=StubRetriever(),
    )
    return service, gateway, history_dir


def build_service_with_gateway(gateway, tmp_path, retriever=None):
    history_dir = tmp_path / "reference_incidents"
    shutil.copytree(PROJECT_ROOT / "data" / "reference_incidents", history_dir)

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
        retriever=retriever or StubRetriever(),
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
    assert payload["source_citations"]
    assert payload["retrieved_evidence"] is not None
    assert payload["retrieval_status"] == "used"


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
            "retrieved_evidence": [],
            "source_citations": [],
            "confidence": 0.6,
        }
        body = json.dumps(payload)
        return ChatTurn(
            content=body,
            message={"role": "assistant", "content": body},
            tool_calls=[],
        )


class NoisyInvestigateGateway:
    def chat(self, *, model, messages, tools=None, format=None):
        if tools is not None:
            return ChatTurn(
                content="enough evidence",
                message={"role": "assistant", "content": "enough evidence"},
                tool_calls=[],
            )

        payload = {
            "incident_type": "database",
            "severity": "critical",
            "top_error_lines": [
                "1: 2026-03-31 09:10:22 ERROR database connection timeout after 30 seconds;",
                "2: 2026-03-31 09:10:23 WARN retrying connection attempt 1 of 3;",
                "3: 2026-03-31 09:10:24 ERROR connection pool exhausted on primary-postgres",
            ],
            "suspected_root_cause": "connection pool exhaustion on primary-postgres after a flash sale",
            "next_steps": [],
            "manager_summary": "Database is experiencing active saturation symptoms.",
            "retrieved_evidence": [
                "- data/knowledge/runbooks/database-timeout-runbook.md#Symptoms: Database timeout incidents usually include connection pool exhaustion or long-running postgres transactions."
            ],
            "source_citations": [
                "data/knowledge/runbooks/database-timeout-runbook.md#Symptoms",
                "data/knowledge/readmes/payments-service-readme.md#Operational Notes",
                "data/knowledge/invalid.md#MadeUp",
            ],
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
    assert "read_log_file:data/logs/database-current.log" in response.source_citations
    assert (
        "compare_two_logs:data/logs/database-previous.log->data/logs/database-current.log"
        in response.source_citations
    )
    assert any("database-timeout-runbook" in citation for citation in response.source_citations)
    assert response.retrieved_evidence
    assert response.retrieval_status == "used"
    assert response.next_steps
    assert response.next_steps[0].startswith("Confirm database reachability")
    assert response.confidence >= 0.85


def test_investigate_grounds_manager_summary_retrieved_evidence_and_citations(tmp_path) -> None:
    service = build_service_with_gateway(
        NoisyInvestigateGateway(),
        tmp_path,
        retriever=MultiHitDatabaseRetriever(),
    )

    response = service.investigate(
        InvestigateRequest(
            prompt="Investigate this incident using the failing run and the previous healthy run.",
            candidate_log_paths=[
                "data/logs/database-current.log",
                "data/logs/database-previous.log",
            ],
            incident_type_hint="database",
        )
    )

    assert response.manager_summary == (
        "The current database run is failing with database connection timeout after 30 seconds and "
        "connection pool exhausted on primary-postgres, while the previous run was healthy."
    )
    assert response.severity == "high"
    assert response.top_error_lines == [
        "1: 2026-03-31 09:10:22 ERROR database connection timeout after 30 seconds",
        "2: 2026-03-31 09:10:23 WARN retrying connection attempt 1 of 3",
        "3: 2026-03-31 09:10:24 ERROR connection pool exhausted on primary-postgres",
        "4: 2026-03-31 09:10:26 ERROR checkout request stalled waiting for free database connection",
    ]
    assert response.suspected_root_cause == (
        "Connection pool exhaustion on primary-postgres is causing repeated database timeouts and stalled checkout requests. "
        "Compared with the previous run, this appears to be a current regression."
    )
    assert "flash sale" not in response.suspected_root_cause.lower()
    assert response.retrieved_evidence == [
        "Database timeout incidents usually include connection pool exhaustion or long-running postgres transactions.",
        (
            "When pool exhaustion occurs, checkout requests stall before downstream billing work begins. "
            "The first signs are database timeout lines, retries, and warnings about waiting for a free connection."
        ),
    ]
    assert response.next_steps[-1] == (
        "Mitigate by reducing pressure, restarting stuck workers only if safe, and validating recovery."
    )
    assert response.source_citations == [
        "read_log_file:data/logs/database-current.log",
        "read_log_file:data/logs/database-previous.log",
        "compare_two_logs:data/logs/database-previous.log->data/logs/database-current.log",
        "load_incident_template:database",
        "data/knowledge/runbooks/database-timeout-runbook.md#Symptoms",
        "data/knowledge/readmes/payments-service-readme.md#Operational Notes",
    ]
    assert response.confidence >= 0.85


def test_investigate_degrades_when_retrieval_is_unavailable(tmp_path) -> None:
    service = build_service_with_gateway(
        NoToolGenericFinalGateway(),
        tmp_path,
        retriever=FailingRetriever(),
    )

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

    assert response.retrieval_status == "unavailable"
    assert response.source_citations
    assert "read_log_file:data/logs/database-current.log" in response.source_citations
    assert response.retrieved_evidence == []
    assert 0.7 <= response.confidence < 0.85


class RaisingInvestigationService:
    def investigate(self, request):
        raise RequestError("upgrade in progress...")


def test_investigate_returns_503_with_clear_ollama_upgrade_message() -> None:
    app.dependency_overrides[get_investigation_service] = lambda: RaisingInvestigationService()
    client = TestClient(app)

    try:
        response = client.post("/investigate", json={"prompt": "Investigate this incident."})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503
    assert "upgrade is still in progress" in response.json()["detail"]
