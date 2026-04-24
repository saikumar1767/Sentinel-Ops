import json

import pytest
import requests
from fastapi.testclient import TestClient

from app.dependencies import get_analyze_service, get_runtime_health_service
from app.evaluation import REQUIRED_RESPONSE_KEYS, load_eval_cases, score_analysis_response
from app.main import app
from app.ollama_client import ChatTurn
from app.schemas import (
    AnalyzeRequest,
    HealthAppInfo,
    HealthDependency,
    LivenessResponse,
    ReadinessResponse,
    RetrievalHit,
)
from app.services.analyze_service import AnalyzeService
from app.services.runtime_health_service import RuntimeHealthService
from app.settings import Settings

client = TestClient(app)
CASES = load_eval_cases()


def infer_incident_type(text: str) -> str:
    lowered = text.lower()
    if any(token in lowered for token in ("missing env", "missing config", "payment_api_key", "redis_url")):
        return "configuration"
    if any(token in lowered for token in ("failed login", "credential", "account lock")):
        return "authentication"
    if any(token in lowered for token in ("outofmemory", "heap space", "swap activity", "memory available")):
        return "memory"
    if any(token in lowered for token in ("ransomware", "certificate", "tls handshake")):
        return "security"
    if any(token in lowered for token in ("queue backlog", "consumer lag")):
        return "queue"
    if any(token in lowered for token in ("disk usage", "no space left")):
        return "disk"
    if any(token in lowered for token in ("readiness probe", "rollout paused", "failed deployment")):
        return "deployment"
    if any(token in lowered for token in ("failed to resolve", "dns lookup", "packet loss", "connection reset by peer")):
        return "network"
    if any(token in lowered for token in ("rate limit", "http 429")):
        return "api"
    if any(token in lowered for token in ("database", "deadlock", "pool exhausted", "lock wait timeout")):
        return "database"
    if any(token in lowered for token in ("cpu usage", "latency p95", "latency increased")):
        return "performance"
    return "service"


def infer_severity(text: str, incident_type: str) -> str:
    lowered = text.lower()
    if "ransomware" in lowered:
        return "critical"
    if incident_type in {"performance"}:
        return "medium"
    if incident_type == "memory" and "swap activity" in lowered and "outofmemory" not in lowered:
        return "medium"
    return "high"


def retrieval_hit_for(incident_type: str) -> RetrievalHit:
    snippets = {
        "api": "Partner billing integration can return HTTP 429 when the rate limit budget is exhausted.",
        "authentication": "Repeated failed login attempts plus account lock growth usually indicate credential abuse or stale secrets.",
        "configuration": "Missing environment variables should be classified as configuration even when the service is failing during deployment.",
        "database": "Database timeout incidents often include connection pool exhaustion or long-running transactions on postgres.",
        "deployment": "Rollouts should pause when readiness probes fail for new pods.",
        "disk": "No space left on device means the host is storage constrained and backup writes are likely to fail.",
        "memory": "Sustained swap activity with low available memory indicates memory pressure before an explicit OOM crash.",
        "network": "DNS lookup failures and connection reset events point to a network or resolver problem.",
        "performance": "High CPU plus rising latency usually indicates service saturation rather than a hard outage.",
        "queue": "Queue backlog and consumer lag should be handled as a throughput incident with SLA risk.",
        "security": "Expired certificates and TLS handshake failures are security incidents that block trusted connections.",
        "service": "HTTP 502 plus an open circuit breaker usually indicates an unhealthy upstream service.",
    }
    citation = f"data/knowledge/{incident_type}.md#Overview"
    return RetrievalHit(
        chunk_id=f"stub-{incident_type}",
        document_type="runbook",
        source_path=f"data/knowledge/{incident_type}.md",
        citation=citation,
        snippet=snippets[incident_type],
        title=f"{incident_type.title()} reference",
        incident_type=incident_type,
        similarity_score=0.95,
    )


class StubRetriever:
    def search(self, *, query: str, top_k: int, document_types=None, incident_type_hint=None):
        seed = incident_type_hint or infer_incident_type(query)
        hit = retrieval_hit_for(seed)
        return [hit]


class HeuristicAnalyzeGateway:
    def chat(self, *, model, messages, tools=None, format=None):
        prompt = messages[-1]["content"]
        log_text = prompt.split("Use this log text:", 1)[1].split(
            "Retrieved supporting evidence:",
            1,
        )[0].strip()
        incident_type = infer_incident_type(log_text)
        severity = infer_severity(log_text, incident_type)
        lines = [line.strip() for line in log_text.splitlines() if line.strip()]
        suspected_root_cause = " ".join(lines[:2]) or "Insufficient log evidence."
        payload = {
            "incident_type": incident_type,
            "severity": severity,
            "summary": f"{incident_type.title()} incident detected from supplied log evidence.",
            "suspected_root_cause": suspected_root_cause,
            "recommended_action": "Use the cited runbook and validate the affected dependency before retrying.",
            "retrieved_evidence": [],
            "source_citations": [],
            "confidence": 0.84,
        }
        body = json.dumps(payload)
        return ChatTurn(
            content=body,
            message={"role": "assistant", "content": body},
            tool_calls=[],
        )


def build_analyze_service() -> AnalyzeService:
    return AnalyzeService(
        settings=Settings(),
        gateway=HeuristicAnalyzeGateway(),
        retriever=StubRetriever(),
    )


class FailingRetriever:
    def search(self, *, query: str, top_k: int, document_types=None, incident_type_hint=None):
        raise RuntimeError("retrieval backend unavailable")


class MultiHitDatabaseRetriever:
    def search(self, *, query: str, top_k: int, document_types=None, incident_type_hint=None):
        return [
            RetrievalHit(
                chunk_id="db-runbook-checks",
                document_type="runbook",
                source_path="data/knowledge/runbooks/database-timeout-runbook.md",
                citation="data/knowledge/runbooks/database-timeout-runbook.md#Checks",
                snippet="Confirm primary postgres reachability and DNS resolution.",
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
                    "Checkout traffic degrades when logs show database connection timeout errors, "
                    "connection pool exhaustion, or workers stalled waiting for a free postgres connection."
                ),
                title="Database timeout runbook",
                section_path="Symptoms",
                incident_type="database",
                similarity_score=0.96,
            ),
            RetrievalHit(
                chunk_id="payments-readme-notes",
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


class StubRuntimeHealthService:
    def __init__(
        self,
        *,
        ollama_status="ok",
        knowledge_status="ok",
        chroma_status="ok",
        analyze_capability="ok",
        investigate_capability="ok",
        knowledge_ingest_capability="ok",
        knowledge_search_capability="ok",
    ):
        self.liveness = LivenessResponse(
            check_type="liveness",
            alive=True,
            status="ok",
            summary="stub liveness summary",
            app=HealthAppInfo(name="SentinelOps", version="0.4.0"),
        )
        self.readiness = ReadinessResponse(
            check_type="readiness",
            scope="traffic",
            ready=analyze_capability in {"ok", "degraded"} and investigate_capability in {"ok", "degraded"},
            traffic_ready=analyze_capability in {"ok", "degraded"} and investigate_capability in {"ok", "degraded"},
            strict_ready=(
                analyze_capability == "ok"
                and investigate_capability == "ok"
                and knowledge_ingest_capability == "ok"
                and knowledge_search_capability == "ok"
            ),
            status=(
                "ok"
                if ollama_status == "ok"
                and knowledge_status == "ok"
                and analyze_capability == "ok"
                and investigate_capability == "ok"
                and knowledge_ingest_capability == "ok"
                and knowledge_search_capability == "ok"
                else "degraded"
            ),
            summary="stub readiness summary",
            app=HealthAppInfo(name="SentinelOps", version="0.4.0"),
            dependencies={
                "ollama": HealthDependency(status=ollama_status, detail="stub"),
                "knowledge_store": HealthDependency(status=knowledge_status, detail="stub"),
                "chroma": HealthDependency(status=chroma_status, detail="stub"),
            },
            capabilities={
                "analyze_endpoint": HealthDependency(status=analyze_capability, detail="stub"),
                "investigate_endpoint": HealthDependency(status=investigate_capability, detail="stub"),
                "knowledge_ingest_endpoint": HealthDependency(status=knowledge_ingest_capability, detail="stub"),
                "knowledge_search_endpoint": HealthDependency(status=knowledge_search_capability, detail="stub"),
            },
        )

    def health_report(self) -> LivenessResponse:
        return self.liveness

    def readiness_report(self, *, scope: str = "traffic") -> ReadinessResponse:
        return self.readiness.model_copy(update={"scope": scope, "ready": self.readiness.strict_ready if scope == "strict" else self.readiness.traffic_ready})

    def is_ready(self, report: ReadinessResponse | None = None, *, strict: bool = False) -> bool:
        report = report or self.readiness_report()
        return report.strict_ready if strict else report.traffic_ready


def test_health() -> None:
    app.dependency_overrides[get_runtime_health_service] = lambda: StubRuntimeHealthService()
    try:
        response = client.get("/health")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["check_type"] == "liveness"
    assert payload["alive"] is True
    assert payload["status"] == "ok"
    assert payload["summary"] == "stub liveness summary"
    assert "dependencies" not in payload
    assert "capabilities" not in payload


def test_ready_returns_200_when_core_traffic_is_available_but_retrieval_is_degraded() -> None:
    app.dependency_overrides[get_runtime_health_service] = (
        lambda: StubRuntimeHealthService(
            knowledge_status="unavailable",
            chroma_status="unavailable",
            analyze_capability="degraded",
            investigate_capability="degraded",
            knowledge_ingest_capability="unavailable",
            knowledge_search_capability="unavailable",
        )
    )
    try:
        response = client.get("/ready")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["check_type"] == "readiness"
    assert response.json()["ready"] is True
    assert response.json()["traffic_ready"] is True
    assert response.json()["strict_ready"] is False
    assert response.json()["dependencies"]["knowledge_store"]["status"] == "unavailable"


def test_ready_strict_returns_503_when_optional_knowledge_capabilities_are_unavailable() -> None:
    app.dependency_overrides[get_runtime_health_service] = (
        lambda: StubRuntimeHealthService(
            knowledge_status="unavailable",
            chroma_status="unavailable",
            analyze_capability="degraded",
            investigate_capability="degraded",
            knowledge_ingest_capability="unavailable",
            knowledge_search_capability="unavailable",
        )
    )
    try:
        response = client.get("/ready/strict")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503
    assert response.json()["scope"] == "strict"
    assert response.json()["ready"] is False


def test_runtime_health_marks_retrieval_capabilities_degraded_when_embedding_model_is_missing(monkeypatch) -> None:
    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {
                "models": [
                    {"name": "mistral", "model": "mistral"},
                ]
            }

    def fake_get(url: str, timeout: int):
        return FakeResponse()

    monkeypatch.setattr("app.services.runtime_health_service.requests.get", fake_get)
    service = RuntimeHealthService(Settings(knowledge_store_backend="simple"))

    report = service.readiness_report()

    assert report.dependencies["ollama"].status == "degraded"
    assert report.dependencies["knowledge_store"].status == "unavailable"
    assert report.capabilities["analyze_endpoint"].status == "degraded"
    assert report.capabilities["investigate_endpoint"].status == "degraded"
    assert report.capabilities["knowledge_search_endpoint"].status == "unavailable"
    assert service.is_ready(report)
    assert not service.is_ready(report, strict=True)


def test_runtime_health_reports_unreachable_ollama_without_claiming_models_are_missing(monkeypatch) -> None:
    def fake_get(url: str, timeout: int):
        raise requests.ConnectionError("socket timeout")

    monkeypatch.setattr("app.services.runtime_health_service.requests.get", fake_get)
    service = RuntimeHealthService(Settings(knowledge_store_backend="simple"))

    report = service.readiness_report()

    assert report.dependencies["ollama"].status == "unavailable"
    assert report.capabilities["analyze_endpoint"].status == "unavailable"


def test_runtime_health_accepts_persistent_chroma_without_http_server(monkeypatch, tmp_path) -> None:
    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {
                "models": [
                    {"name": "mistral:latest"},
                    {"name": "nomic-embed-text:latest"},
                ]
            }

    def fake_get(url: str, timeout: int):
        if "/api/tags" not in url:
            raise AssertionError(f"unexpected HTTP readiness probe: {url}")
        return FakeResponse()

    monkeypatch.setattr("app.services.runtime_health_service.requests.get", fake_get)
    service = RuntimeHealthService(
        Settings(
            knowledge_store_backend="chroma",
            chroma_client_mode="persistent",
            chroma_path=tmp_path / "chroma-db",
            analyze_model="mistral",
            investigate_model="mistral",
            embedding_model="nomic-embed-text",
        )
    )

    report = service.readiness_report(scope="strict")

    assert report.dependencies["chroma"].status == "ok"
    assert report.dependencies["chroma"].metadata["client_mode"] == "persistent"
    assert report.strict_ready is True
    assert report.capabilities["analyze_endpoint"].status == "ok"
    assert report.capabilities["investigate_endpoint"].status == "ok"


def test_openapi_includes_rag_examples_for_analyze_and_investigate() -> None:
    response = client.get("/openapi.json")

    assert response.status_code == 200
    payload = response.json()
    analyze_schema = payload["components"]["schemas"]["AnalyzeResponse"]
    investigate_schema = payload["components"]["schemas"]["InvestigateResponse"]
    analyze_request_schema = payload["components"]["schemas"]["AnalyzeRequest"]
    investigate_request_schema = payload["components"]["schemas"]["InvestigateRequest"]

    assert "retrieves supporting knowledge-base evidence" in payload["paths"]["/analyze"]["post"]["description"]
    assert "reads candidate logs" in payload["paths"]["/investigate"]["post"]["description"]
    assert "/ready/strict" in payload["paths"]
    assert analyze_request_schema["examples"]
    assert investigate_request_schema["examples"]
    assert analyze_schema["example"]["retrieval_status"] == "used"
    assert investigate_schema["example"]["retrieval_status"] == "used"


class NarrowSummaryAnalyzeGateway:
    def chat(self, *, model, messages, tools=None, format=None):
        payload = {
            "incident_type": "database",
            "severity": "high",
            "summary": "Database connection timeout after 30 seconds",
            "suspected_root_cause": "connection pool exhausted on primary-postgres due to prolonged database connection timeouts",
            "recommended_action": "Reduce application concurrency until the database is stable",
            "retrieved_evidence": [
                "- data/knowledge/runbooks/database-timeout-runbook.md#Checks: Confirm primary postgres reachability and DNS resolution."
            ],
            "source_citations": [
                "data/knowledge/runbooks/database-timeout-runbook.md#Checks",
                "data/knowledge/readmes/payments-service-readme.md#Operational Notes",
                "data/knowledge/invalid.md#MadeUp",
            ],
            "confidence": 0.8,
        }
        body = json.dumps(payload)
        return ChatTurn(
            content=body,
            message={"role": "assistant", "content": body},
            tool_calls=[],
        )


class SpeculativeAnalyzeGateway:
    def chat(self, *, model, messages, tools=None, format=None):
        payload = {
            "incident_type": "database",
            "severity": "high",
            "summary": (
                "Database connection timeout and pool exhaustion after repeated retries, "
                "indicating a potential issue with primary-postgres reachability or DNS resolution."
            ),
            "suspected_root_cause": (
                "connection pool exhausted on primary-postgres due to prolonged database connection timeouts. "
                "Evidence from log: database connection timeout after 30 seconds; retrying connection attempt 1/3; "
                "connection pool exhausted on primary-postgres"
            ),
            "recommended_action": (
                "Reduce application concurrency until the database is stable, terminate or recycle stuck workers "
                "only after database health is confirmed, and escalate to the database owner if lock waits or "
                "pool exhaustion persist."
            ),
            "retrieved_evidence": [],
            "source_citations": [
                "data/knowledge/runbooks/database-timeout-runbook.md#Checks",
                "data/knowledge/runbooks/database-timeout-runbook.md#Symptoms",
                "data/knowledge/readmes/payments-service-readme.md#Operational Notes",
            ],
            "confidence": 0.8,
        }
        body = json.dumps(payload)
        return ChatTurn(
            content=body,
            message={"role": "assistant", "content": body},
            tool_calls=[],
        )


class SingleCitationAnalyzeGateway:
    def chat(self, *, model, messages, tools=None, format=None):
        payload = {
            "incident_type": "database",
            "severity": "high",
            "summary": "Database connection timeout after 30 seconds",
            "suspected_root_cause": "connection pool exhausted on primary-postgres due to prolonged database connection timeouts",
            "recommended_action": "Reduce application concurrency until the database is stable",
            "retrieved_evidence": [],
            "source_citations": [
                "data/knowledge/readmes/payments-service-readme.md#Operational Notes",
            ],
            "confidence": 0.8,
        }
        body = json.dumps(payload)
        return ChatTurn(
            content=body,
            message={"role": "assistant", "content": body},
            tool_calls=[],
        )


def test_analyze_grounds_summary_root_cause_and_retrieved_evidence_from_retrieval_hits() -> None:
    service = AnalyzeService(
        settings=Settings(),
        gateway=SpeculativeAnalyzeGateway(),
        retriever=MultiHitDatabaseRetriever(),
    )

    response = service.analyze(
        AnalyzeRequest(
            log_text=(
                "2026-03-29 09:10:22 ERROR database connection timeout after 30 seconds\n"
                "2026-03-29 09:10:23 WARN retrying connection attempt 1/3\n"
                "2026-03-29 09:10:24 ERROR connection pool exhausted on primary-postgres"
            )
        )
    )

    assert response.summary == (
        "Database incident with database connection timeout after 30 seconds and "
        "connection pool exhausted on primary-postgres."
    )
    assert response.suspected_root_cause == (
        "Connection pool exhaustion on primary-postgres is causing repeated database timeouts."
    )
    assert response.retrieved_evidence == [
        (
            "Checkout traffic degrades when logs show database connection timeout errors, "
            "connection pool exhaustion, or workers stalled waiting for a free postgres connection."
        ),
        (
            "When pool exhaustion occurs, checkout requests stall before downstream billing work begins. "
            "The first signs are database timeout lines, retries, and warnings about waiting for a free connection."
        ),
    ]
    assert response.source_citations == [
        "data/knowledge/runbooks/database-timeout-runbook.md#Symptoms",
        "data/knowledge/readmes/payments-service-readme.md#Operational Notes",
    ]
    assert "dns resolution" not in response.summary.lower()
    assert response.confidence >= 0.9


def test_analyze_fills_missing_preferred_citations_and_evidence_snippets() -> None:
    service = AnalyzeService(
        settings=Settings(),
        gateway=SingleCitationAnalyzeGateway(),
        retriever=MultiHitDatabaseRetriever(),
    )

    response = service.analyze(
        AnalyzeRequest(
            log_text=(
                "2026-03-29 09:10:22 ERROR database connection timeout after 30 seconds\n"
                "2026-03-29 09:10:23 WARN retrying connection attempt 1/3\n"
                "2026-03-29 09:10:24 ERROR connection pool exhausted on primary-postgres"
            )
        )
    )

    assert response.source_citations == [
        "data/knowledge/readmes/payments-service-readme.md#Operational Notes",
        "data/knowledge/runbooks/database-timeout-runbook.md#Symptoms",
    ]
    assert response.retrieved_evidence == [
        (
            "When pool exhaustion occurs, checkout requests stall before downstream billing work begins. "
            "The first signs are database timeout lines, retries, and warnings about waiting for a free connection."
        ),
        (
            "Checkout traffic degrades when logs show database connection timeout errors, "
            "connection pool exhaustion, or workers stalled waiting for a free postgres connection."
        ),
    ]


@pytest.mark.parametrize("case", CASES, ids=[case.id for case in CASES])
def test_analyze_eval_cases(case) -> None:
    app.dependency_overrides[get_analyze_service] = build_analyze_service
    try:
        response = client.post("/analyze", json={"log_text": case.input_log})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200

    payload = response.json()
    for key in REQUIRED_RESPONSE_KEYS:
        assert key in payload

    failures = score_analysis_response(case, payload)
    assert not failures, f"{case.id} failed: {', '.join(failures)}"
    assert payload["source_citations"]
    assert payload["retrieved_evidence"]
    assert payload["retrieval_status"] == "used"


def test_analyze_degrades_when_retrieval_is_unavailable() -> None:
    service = AnalyzeService(
        settings=Settings(),
        gateway=HeuristicAnalyzeGateway(),
        retriever=FailingRetriever(),
    )
    app.dependency_overrides[get_analyze_service] = lambda: service
    try:
        response = client.post(
            "/analyze",
            json={
                "log_text": "2026-03-30 07:10:22 ERROR database connection timeout after 30 seconds"
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["retrieval_status"] == "unavailable"
    assert payload["retrieved_evidence"] == []
    assert payload["source_citations"] == []
    assert 0.5 <= payload["confidence"] < 0.75
