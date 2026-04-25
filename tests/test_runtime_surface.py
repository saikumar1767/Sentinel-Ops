import json

from fastapi.testclient import TestClient
from ollama import RequestError

from app.dependencies import (
    get_analyze_service,
    get_authentication_service,
    get_knowledge_base_service,
    get_ollama_gateway,
    get_runtime_metrics,
    get_settings,
    get_workflow_service,
    get_workflow_audit_trail,
    get_workflow_thread_store,
)
from app.main import app
from app.ollama_client import OllamaGateway
from app.persistence import build_metadata_engine
from app.rag.service import KnowledgeBaseService
from app.runtime_metrics import RuntimeMetrics
from app.schemas import AnalyzeRequest, AnalyzeResponse, RetrievalHit, WorkflowAuditResponse
from app.settings import Settings
from app.startup import validate_settings


class StubAnalyzeService:
    def analyze(self, request: AnalyzeRequest) -> AnalyzeResponse:
        return AnalyzeResponse(
            incident_type="database",
            severity="high",
            summary="Database incident with connection pool exhaustion.",
            suspected_root_cause="Connection pool exhaustion on primary-postgres.",
            recommended_action="Confirm postgres health and reduce caller concurrency.",
            retrieved_evidence=[],
            retrieval_status="not_used",
            source_citations=[],
            top_error_lines=["2026-04-06 09:10:22 ERROR database connection timeout after 30 seconds"],
            confidence=0.91,
        )


class FakeMessage:
    def __init__(self, content: str) -> None:
        self.content = content
        self.tool_calls = []

    def model_dump(self, exclude_none: bool = True) -> dict[str, object]:
        return {
            "role": "assistant",
            "content": self.content,
        }


class FakeChatResponse:
    def __init__(
        self,
        *,
        content: str,
        prompt_eval_count: int,
        eval_count: int,
        total_duration: int,
    ) -> None:
        self.message = FakeMessage(content)
        self.prompt_eval_count = prompt_eval_count
        self.eval_count = eval_count
        self.total_duration = total_duration

    def model_dump(self, exclude_none: bool = True) -> dict[str, object]:
        return {
            "message": self.message.model_dump(exclude_none=exclude_none),
            "prompt_eval_count": self.prompt_eval_count,
            "eval_count": self.eval_count,
            "total_duration": self.total_duration,
        }


class RetryThenCacheClient:
    def __init__(self) -> None:
        self.chat_calls = 0

    def chat(self, *, model, messages, tools=None, stream=False, format=None, options=None):
        self.chat_calls += 1
        if self.chat_calls == 1:
            raise RequestError("temporary network failure")
        return FakeChatResponse(
            content=json.dumps({"status": "ok"}),
            prompt_eval_count=120,
            eval_count=45,
            total_duration=250_000_000,
        )

    def embed(self, *, model, input, truncate=True):
        raise AssertionError("embed should not be called in this test")


class AlwaysOfflineClient:
    def chat(self, *, model, messages, tools=None, stream=False, format=None, options=None):
        raise ConnectionError(
            "Failed to connect to Ollama. Please check that Ollama is downloaded, running and accessible."
        )

    def embed(self, *, model, input, truncate=True):
        raise ConnectionError(
            "Failed to connect to Ollama. Please check that Ollama is downloaded, running and accessible."
        )


class CountingEmbeddingProvider:
    def __init__(self) -> None:
        self.calls = 0

    def embed_texts(self, texts):
        self.calls += 1
        return [[0.1, 0.9] for _ in texts]


class CountingStore:
    collection_name = "test-cache"

    def __init__(self) -> None:
        self.query_calls = 0

    def rebuild(self, *, chunks, embeddings, reset):
        raise AssertionError("rebuild should not be called in this test")

    def count(self) -> int:
        return 1

    def query(self, *, query_embedding, top_k, document_types=None, incident_type_hint=None):
        self.query_calls += 1
        return [
            RetrievalHit(
                chunk_id="cache-hit-1",
                document_type="runbook",
                source_path="data/knowledge/runbooks/database-timeout-runbook.md",
                citation="data/knowledge/runbooks/database-timeout-runbook.md#Symptoms",
                snippet="Database timeout incidents usually include connection pool exhaustion.",
                title="Database timeout runbook",
                incident_type="database",
                similarity_score=0.9,
            )
        ]


class StubWorkflowService:
    def audit_report(self, thread_id: str) -> WorkflowAuditResponse:
        return WorkflowAuditResponse(thread_id=thread_id, total_events=0, events=[])


def reset_singletons() -> None:
    get_settings.cache_clear()
    get_authentication_service.cache_clear()
    get_ollama_gateway.cache_clear()
    get_knowledge_base_service.cache_clear()
    get_runtime_metrics.cache_clear()
    get_workflow_audit_trail.cache_clear()
    get_workflow_thread_store.cache_clear()
    app.openapi_schema = None


def test_operational_routes_are_public_and_health_stays_available() -> None:
    reset_singletons()
    app.dependency_overrides[get_analyze_service] = lambda: StubAnalyzeService()
    client = TestClient(app)

    try:
        health = client.get("/health")
        analyze = client.post(
            "/analyze",
            json={"log_text": "2026-04-06 09:10:22 ERROR database connection timeout after 30 seconds"},
        )
    finally:
        app.dependency_overrides.clear()
        reset_singletons()

    assert health.status_code == 200
    assert analyze.status_code == 200
    assert analyze.json()["incident_type"] == "database"
    assert analyze.headers["X-Request-ID"]
    assert analyze.headers["X-Process-Time-Ms"]
    assert analyze.headers["X-Content-Type-Options"] == "nosniff"
    assert analyze.headers["X-Frame-Options"] == "DENY"
    assert analyze.headers["Referrer-Policy"] == "no-referrer"


def test_openapi_does_not_advertise_security_schemes() -> None:
    reset_singletons()
    client = TestClient(app)

    try:
        openapi = client.get("/openapi.json").json()
    finally:
        reset_singletons()

    assert "securitySchemes" not in openapi.get("components", {})
    assert "security" not in openapi["paths"]["/analyze"]["post"]
    assert "security" not in openapi["paths"]["/health"]["get"]
    analyze_responses = openapi["paths"]["/analyze"]["post"]["responses"]
    assert analyze_responses["422"]["content"]["application/problem+json"]["schema"]["$ref"].endswith(
        "/ProblemDetailResponse"
    )
    assert analyze_responses["502"]["content"]["application/problem+json"]["schema"]["$ref"].endswith(
        "/ProblemDetailResponse"
    )
    assert analyze_responses["503"]["content"]["application/problem+json"]["schema"]["$ref"].endswith(
        "/ProblemDetailResponse"
    )
    knowledge_ingest_responses = openapi["paths"]["/knowledge/ingest"]["post"]["responses"]
    assert knowledge_ingest_responses["400"]["content"]["application/problem+json"]["schema"]["$ref"].endswith(
        "/ProblemDetailResponse"
    )
    ready_responses = openapi["paths"]["/ready"]["get"]["responses"]
    assert ready_responses["503"]["content"]["application/json"]["schema"]["$ref"].endswith(
        "/ReadinessResponse"
    )


def test_auth_enabled_routes_require_identity_and_admin_for_metrics(monkeypatch) -> None:
    reset_singletons()
    monkeypatch.setenv("SENTINELOPS_AUTH_MODE", "api_key")
    monkeypatch.setenv("SENTINELOPS_AUTH_API_KEY", "header-secret")
    monkeypatch.setenv(
        "SENTINELOPS_AUTH_BEARER_TOKENS",
        json.dumps(
            {
                "analyst-token": {
                    "subject": "analyst-1",
                    "email": "analyst@example.com",
                    "name": "Analyst One",
                    "roles": ["analyst"],
                },
                "admin-token": {
                    "subject": "admin-1",
                    "email": "admin@example.com",
                    "name": "Admin One",
                    "roles": ["admin"],
                },
            }
        ),
    )
    reset_singletons()
    app.dependency_overrides[get_analyze_service] = lambda: StubAnalyzeService()
    client = TestClient(app)

    try:
        unauthorized = client.post(
            "/analyze",
            json={"log_text": "2026-04-06 09:10:22 ERROR database connection timeout after 30 seconds"},
        )
        health = client.get("/health")
        authorized = client.post(
            "/analyze",
            headers={"Authorization": "Bearer analyst-token"},
            json={"log_text": "2026-04-06 09:10:22 ERROR database connection timeout after 30 seconds"},
        )
        header_authorized = client.post(
            "/analyze",
            headers={"X-API-Key": "header-secret"},
            json={"log_text": "2026-04-06 09:10:22 ERROR database connection timeout after 30 seconds"},
        )
        me = client.get("/me", headers={"Authorization": "Bearer analyst-token"})
        forbidden_metrics = client.get("/metrics", headers={"Authorization": "Bearer analyst-token"})
        admin_metrics = client.get("/metrics", headers={"Authorization": "Bearer admin-token"})
    finally:
        app.dependency_overrides.clear()
        reset_singletons()

    assert unauthorized.status_code == 401
    assert health.status_code == 200
    assert authorized.status_code == 200
    assert header_authorized.status_code == 200
    assert me.status_code == 200
    assert me.json()["subject"] == "analyst-1"
    assert me.json()["roles"] == ["analyst"]
    assert forbidden_metrics.status_code == 403
    assert admin_metrics.status_code == 200


def test_openapi_advertises_security_schemes_when_auth_is_enabled(monkeypatch) -> None:
    reset_singletons()
    monkeypatch.setenv("SENTINELOPS_AUTH_MODE", "api_key")
    monkeypatch.setenv(
        "SENTINELOPS_AUTH_BEARER_TOKENS",
        json.dumps(
            {
                "analyst-token": {
                    "subject": "analyst-1",
                    "roles": ["analyst"],
                }
            }
        ),
    )
    reset_singletons()
    client = TestClient(app)

    try:
        openapi = client.get("/openapi.json").json()
    finally:
        reset_singletons()

    security_schemes = openapi["components"]["securitySchemes"]
    assert "SentinelOpsApiKey" in security_schemes
    assert "SentinelOpsBearer" in security_schemes
    assert openapi["paths"]["/analyze"]["post"]["security"]
    assert "security" not in openapi["paths"]["/health"]["get"]
    assert openapi["paths"]["/me"]["get"]["security"]


def test_request_validation_errors_use_problem_details() -> None:
    reset_singletons()
    client = TestClient(app)

    try:
        response = client.post("/analyze", json={})
    finally:
        reset_singletons()

    assert response.status_code == 422
    assert response.headers["content-type"].startswith("application/problem+json")
    payload = response.json()
    assert payload["title"] == "Request validation failed"
    assert payload["code"] == "request_validation_failed"


def test_request_body_limit_returns_problem_details(monkeypatch) -> None:
    reset_singletons()
    monkeypatch.setenv("SENTINELOPS_MAX_REQUEST_BODY_BYTES", "1024")
    reset_singletons()
    client = TestClient(app)

    try:
        response = client.post(
            "/analyze",
            content=json.dumps({"log_text": "x" * 2048}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
    finally:
        reset_singletons()

    assert response.status_code == 413
    assert response.headers["content-type"].startswith("application/problem+json")
    payload = response.json()
    assert payload["title"] == "Request body too large"
    assert payload["code"] == "request_body_too_large"
    assert response.headers["X-Request-ID"]


def test_metrics_endpoint_reports_request_usage() -> None:
    reset_singletons()
    runtime_metrics = get_runtime_metrics()
    runtime_metrics.reset()
    app.dependency_overrides[get_analyze_service] = lambda: StubAnalyzeService()
    client = TestClient(app)

    try:
        client.get("/health")
        client.post(
            "/analyze",
            json={"log_text": "2026-04-06 09:10:22 ERROR database connection timeout after 30 seconds"},
        )
        response = client.get("/metrics")
    finally:
        app.dependency_overrides.clear()
        reset_singletons()

    assert response.status_code == 200
    payload = response.json()
    assert payload["requests"]["total_requests"] >= 2
    routes = {(item["method"], item["path"]): item for item in payload["routes"]}
    assert routes[("GET", "/health")]["request_count"] >= 1
    assert routes[("POST", "/analyze")]["request_count"] >= 1


def test_metrics_normalize_workflow_audit_paths() -> None:
    reset_singletons()
    runtime_metrics = get_runtime_metrics()
    runtime_metrics.reset()
    app.dependency_overrides[get_workflow_service] = lambda: StubWorkflowService()
    client = TestClient(app)

    try:
        audit_response = client.get("/workflow/workflow-audit-case/audit")
        metrics_response = client.get("/metrics")
    finally:
        app.dependency_overrides.clear()
        reset_singletons()

    assert audit_response.status_code == 200
    payload = metrics_response.json()
    routes = {(item["method"], item["path"]): item for item in payload["routes"]}
    assert ("GET", "/workflow/{thread_id}/audit") in routes
    assert ("GET", "/workflow/workflow-audit-case/audit") not in routes


def test_ollama_gateway_retries_then_serves_cached_response_with_metrics() -> None:
    settings = Settings(
        ollama_max_retries=1,
        ollama_retry_backoff_seconds=0.0,
        ollama_cache_enabled=True,
        ollama_cache_ttl_seconds=60,
    )
    metrics = RuntimeMetrics()
    client = RetryThenCacheClient()
    gateway = OllamaGateway(settings, metrics=metrics, client=client)
    messages = [{"role": "user", "content": "check the model"}]

    first = gateway.chat(
        model=settings.analyze_model,
        messages=messages,
        format={"type": "object"},
    )
    second = gateway.chat(
        model=settings.analyze_model,
        messages=messages,
        format={"type": "object"},
    )

    snapshot = metrics.snapshot(settings)
    assert client.chat_calls == 2
    assert first.cached is False
    assert second.cached is True
    assert len(snapshot.model_usage) == 1

    model_usage = snapshot.model_usage[0]
    assert model_usage.operation == "chat"
    assert model_usage.call_count == 2
    assert model_usage.cache_hit_count == 1
    assert model_usage.retry_count == 1
    assert model_usage.failure_count == 0
    assert model_usage.prompt_tokens == 120
    assert model_usage.completion_tokens == 45
    assert model_usage.total_tokens == 165


def test_validate_settings_requires_otlp_endpoint_when_enabled() -> None:
    settings = Settings(
        telemetry_enabled=True,
        telemetry_exporter="otlp",
        telemetry_otlp_endpoint=None,
    )

    try:
        validate_settings(settings)
        assert False, "validate_settings should raise for missing OTLP endpoint"
    except RuntimeError as exc:
        assert "telemetry_otlp_endpoint" in str(exc)


def test_validate_settings_requires_auth_credentials_for_api_key_mode() -> None:
    settings = Settings(
        auth_mode="api_key",
        auth_api_key=None,
        auth_bearer_tokens={},
    )

    try:
        validate_settings(settings)
        assert False, "validate_settings should raise when auth_mode=api_key has no credentials"
    except RuntimeError as exc:
        assert "auth_api_key" in str(exc)


def test_validate_settings_requires_oidc_issuer_for_oidc_mode() -> None:
    settings = Settings(
        auth_mode="oidc",
        auth_oidc_issuer_url=None,
    )

    try:
        validate_settings(settings)
        assert False, "validate_settings should raise when auth_mode=oidc has no issuer"
    except RuntimeError as exc:
        assert "auth_oidc_issuer_url" in str(exc)


def test_effective_workflow_checkpoint_database_url_defaults_to_sqlite_path() -> None:
    settings = Settings(workflow_checkpoint_path=Settings().workflow_checkpoint_path)
    assert settings.effective_workflow_checkpoint_database_url.startswith("sqlite:///")


def test_effective_workflow_checkpoint_database_url_prefers_metadata_database_url() -> None:
    settings = Settings(
        metadata_database_url="postgresql+pg8000://sentinelops:secret@db.internal:5432/sentinelops",
    )
    assert settings.effective_workflow_checkpoint_database_url == settings.metadata_database_url


def test_validate_settings_rejects_non_reviewed_models_under_default_license_policy() -> None:
    settings = Settings(
        analyze_model="llama3.2",
        investigate_model="mistral",
        embedding_model="nomic-embed-text",
        model_license_policy="permissive_only",
    )

    try:
        validate_settings(settings)
        assert False, "validate_settings should reject models outside the reviewed default policy"
    except RuntimeError as exc:
        assert "analyze_model" in str(exc)


def test_validate_settings_requires_stricter_contract_in_production_mode() -> None:
    settings = Settings(
        deployment_mode="production",
        auth_mode="disabled",
        telemetry_exporter="none",
    )

    try:
        validate_settings(settings)
        assert False, "validate_settings should reject incomplete production settings"
    except RuntimeError as exc:
        assert "auth_mode" in str(exc)


def test_validate_settings_accepts_hardened_production_profile() -> None:
    settings = Settings(
        deployment_mode="production",
        public_base_url="https://sentinelops.example.internal",
        auth_mode="oidc",
        auth_oidc_issuer_url="https://id.example.internal/realms/sentinelops",
        auth_oidc_audience="sentinelops-api",
        telemetry_exporter="otlp",
        telemetry_otlp_endpoint="https://otel.example.internal/v1/traces",
        metadata_database_url="postgresql+pg8000://sentinelops:secret@db.internal:5432/sentinelops",
        workflow_checkpoint_database_url="postgresql://sentinelops:secret@db.internal:5432/sentinelops?sslmode=require",
    )

    validate_settings(settings)


def test_sqlite_metadata_engine_enables_production_pragmas(tmp_path) -> None:
    database_path = tmp_path / "metadata.sqlite"
    engine = build_metadata_engine(f"sqlite:///{database_path.as_posix()}")

    with engine.connect() as connection:
        busy_timeout = connection.exec_driver_sql("PRAGMA busy_timeout").scalar()
        foreign_keys = connection.exec_driver_sql("PRAGMA foreign_keys").scalar()
        journal_mode = connection.exec_driver_sql("PRAGMA journal_mode").scalar()

    assert busy_timeout == 30_000
    assert foreign_keys == 1
    assert str(journal_mode).lower() == "wal"


def test_ollama_gateway_wraps_connection_errors_as_request_errors() -> None:
    settings = Settings(
        ollama_max_retries=0,
        ollama_cache_enabled=False,
    )
    gateway = OllamaGateway(settings, client=AlwaysOfflineClient())

    try:
        gateway.chat(
            model=settings.analyze_model,
            messages=[{"role": "user", "content": "hello"}],
            format={"type": "object"},
        )
        assert False, "gateway.chat should raise RequestError when Ollama is offline"
    except RequestError as exc:
        assert "Failed to connect to Ollama" in str(exc)


def test_knowledge_service_caches_repeated_search_queries() -> None:
    settings = Settings(
        retrieval_cache_enabled=True,
        retrieval_cache_ttl_seconds=60,
        knowledge_auto_ingest=False,
        knowledge_store_backend="simple",
    )
    embedding_provider = CountingEmbeddingProvider()
    store = CountingStore()
    service = KnowledgeBaseService(
        settings=settings,
        embedding_provider=embedding_provider,
        loader=object(),
        chunker=object(),
        store=store,
    )

    first = service.search(
        query="database timeout and pool exhaustion",
        top_k=3,
        incident_type_hint="database",
    )
    second = service.search(
        query="database timeout and pool exhaustion",
        top_k=3,
        incident_type_hint="database",
    )

    assert len(first) == 1
    assert len(second) == 1
    assert embedding_provider.calls == 1
    assert store.query_calls == 1


def test_metrics_snapshot_includes_cache_usage() -> None:
    settings = Settings(
        retrieval_cache_enabled=True,
        retrieval_cache_ttl_seconds=60,
        retrieval_cache_max_entries=4,
        knowledge_auto_ingest=False,
        knowledge_store_backend="simple",
        ollama_cache_enabled=True,
        ollama_cache_ttl_seconds=60,
        ollama_cache_max_entries=4,
    )
    metrics = RuntimeMetrics()
    gateway = OllamaGateway(settings, metrics=metrics, client=RetryThenCacheClient())
    service = KnowledgeBaseService(
        settings=settings,
        embedding_provider=CountingEmbeddingProvider(),
        loader=object(),
        chunker=object(),
        store=CountingStore(),
    )

    gateway.chat(
        model=settings.analyze_model,
        messages=[{"role": "user", "content": "check the model"}],
        format={"type": "object"},
    )
    gateway.chat(
        model=settings.analyze_model,
        messages=[{"role": "user", "content": "check the model"}],
        format={"type": "object"},
    )
    service.search(query="database timeout", top_k=2)
    service.search(query="database timeout", top_k=2)

    snapshot = metrics.snapshot(settings)
    caches = {item.cache_name: item for item in snapshot.caches}
    assert "ollama_chat" in caches
    assert caches["ollama_chat"].hit_count >= 1
    assert caches["ollama_chat"].set_count >= 1
