import re

import pytest
from fastapi.testclient import TestClient

from app.dependencies import get_knowledge_base_service
from app.evaluation import load_rag_eval_cases, score_rag_search_results
from app.main import app
from app.rag.chunker import MarkdownChunker
from app.rag.loader import KnowledgeDocumentLoader
from app.rag.models import KnowledgeChunk
from app.rag.service import KnowledgeBaseService
from app.rag.simple_store import SimpleKnowledgeStore
from app.settings import PROJECT_ROOT, Settings

RAG_CASES = load_rag_eval_cases()
VOCABULARY = [
    "429",
    "account lock",
    "authentication",
    "backlog",
    "certificate",
    "connection pool",
    "connection timeout",
    "consumer lag",
    "cpu",
    "credential",
    "database",
    "deadlock",
    "deployment",
    "disk",
    "dns",
    "expired",
    "failed login",
    "latency",
    "memory",
    "missing environment",
    "network",
    "no space left",
    "packet loss",
    "postgres",
    "queue",
    "rate limit",
    "readiness",
    "resolve",
    "restart",
    "segmentation fault",
    "service",
    "sla",
    "swap",
    "throttle",
    "timeout",
    "tls",
]


class KeywordEmbeddingProvider:
    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [self._embed(text) for text in texts]

    def _embed(self, text: str) -> list[float]:
        normalized = self._normalize(text)
        vector: list[float] = []
        for keyword in VOCABULARY:
            vector.append(float(normalized.count(keyword)))
        vector.append(float(len(normalized.split())))
        return vector

    @staticmethod
    def _normalize(text: str) -> str:
        collapsed = re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()
        return f" {collapsed} "


@pytest.fixture(scope="session")
def indexed_knowledge_service(tmp_path_factory):
    chroma_path = tmp_path_factory.mktemp("chroma-rag")
    settings = Settings(
        knowledge_base_dir=PROJECT_ROOT / "data" / "knowledge",
        incident_templates_dir=PROJECT_ROOT / "data" / "incident_templates",
        incident_history_dir=PROJECT_ROOT / "data" / "reference_incidents",
        knowledge_index_path=chroma_path / "knowledge-index.json",
        knowledge_auto_ingest=False,
        knowledge_store_backend="simple",
    )
    service = KnowledgeBaseService(
        settings=settings,
        embedding_provider=KeywordEmbeddingProvider(),
        loader=KnowledgeDocumentLoader(settings),
        chunker=MarkdownChunker(settings),
        store=SimpleKnowledgeStore(settings),
    )
    ingest_result = service.rebuild_index(reset=True)
    return service, ingest_result


def test_knowledge_ingest_indexes_local_docs(indexed_knowledge_service) -> None:
    service, ingest_result = indexed_knowledge_service

    assert ingest_result.collection_name == service.collection_name
    assert ingest_result.document_count >= 30
    assert ingest_result.chunk_count >= ingest_result.document_count
    assert ingest_result.source_counts["incident_template"] >= 10
    assert ingest_result.source_counts["runbook"] >= 5
    assert ingest_result.chunk_counts["incident_template"] >= ingest_result.source_counts["incident_template"]
    assert ingest_result.chunk_counts["runbook"] >= ingest_result.source_counts["runbook"]


def test_simple_knowledge_store_rebuild_uses_valid_atomic_index(tmp_path) -> None:
    settings = Settings(
        knowledge_index_path=tmp_path / "knowledge-index.json",
        knowledge_store_backend="simple",
    )
    store = SimpleKnowledgeStore(settings)
    chunk = KnowledgeChunk(
        chunk_id="chunk-database-1",
        document_id="doc-database",
        source_path="runbooks/database.md",
        document_type="runbook",
        title="Database",
        content="Database timeout incidents include connection pool exhaustion.",
        embedding_text="Database timeout incidents include connection pool exhaustion.",
        citation="runbooks/database.md#Database",
        incident_type="database",
        chunk_index=0,
    )

    result = store.rebuild(chunks=[chunk], embeddings=[[0.1, 0.9]], reset=True)

    assert result.chunk_count == 1
    assert store.count() == 1
    assert not [path for path in tmp_path.iterdir() if path.suffix == ".tmp"]


def test_simple_knowledge_store_reports_corrupt_index(tmp_path) -> None:
    index_path = tmp_path / "knowledge-index.json"
    index_path.write_text("{not-json", encoding="utf-8")
    store = SimpleKnowledgeStore(
        Settings(
            knowledge_index_path=index_path,
            knowledge_store_backend="simple",
        )
    )

    with pytest.raises(RuntimeError, match="not valid JSON"):
        store.count()


@pytest.mark.parametrize("case", RAG_CASES, ids=[case.id for case in RAG_CASES])
def test_knowledge_search_eval_cases(indexed_knowledge_service, case) -> None:
    service, _ = indexed_knowledge_service
    hits = service.search(
        query=case.query,
        top_k=case.top_k,
        document_types=case.document_types or None,
        incident_type_hint=case.incident_type_hint,
    )

    failures = score_rag_search_results(case, hits)
    assert not failures, f"{case.id} failed: {', '.join(failures)}"
    assert 1 <= len(hits) <= case.top_k


def test_knowledge_search_respects_document_type_filter(indexed_knowledge_service) -> None:
    service, _ = indexed_knowledge_service
    hits = service.search(
        query="Database connection timeout and pool exhaustion on primary-postgres.",
        top_k=3,
        document_types=["github_issue"],
        incident_type_hint="database",
    )

    assert hits
    assert all(hit.document_type == "github_issue" for hit in hits)
    assert any("db-pool-exhaustion-issue" in hit.citation for hit in hits)


def test_knowledge_api_endpoints(indexed_knowledge_service) -> None:
    service, _ = indexed_knowledge_service
    app.dependency_overrides[get_knowledge_base_service] = lambda: service
    client = TestClient(app)

    try:
        ingest_response = client.post(
            "/knowledge/ingest",
            json={"reset": True, "confirm_reset": True},
        )
        search_response = client.post(
            "/knowledge/search",
            json={
                "query": "Why did startup fail with DNS lookup timed out errors?",
                "top_k": 3,
                "incident_type_hint": "network",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert ingest_response.status_code == 200
    ingest_payload = ingest_response.json()
    assert ingest_payload["document_count"] >= 30
    assert ingest_payload["chunk_count"] >= ingest_payload["document_count"]

    assert search_response.status_code == 200
    search_payload = search_response.json()
    assert search_payload["total_results"] >= 1
    assert search_payload["ranking_strategy"] == "diversified_semantic_search"
    assert any(
        "network-dns-runbook" in item["citation"] or "dns-failover-regression-issue" in item["citation"]
        for item in search_payload["results"]
    )


def test_knowledge_search_endpoint_curates_diverse_database_sources(indexed_knowledge_service) -> None:
    service, _ = indexed_knowledge_service
    app.dependency_overrides[get_knowledge_base_service] = lambda: service
    client = TestClient(app)

    try:
        response = client.post(
            "/knowledge/search",
            json={
                "query": "Why did startup fail with database timeout and connection pool exhaustion?",
                "top_k": 3,
                "document_types": ["runbook", "github_issue"],
                "incident_type_hint": "database",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    citations = [item["citation"] for item in payload["results"]]

    assert payload["total_results"] == 3
    assert payload["ranking_strategy"] == "diversified_semantic_search"
    assert any("database-timeout-runbook.md#Symptoms" in citation for citation in citations)
    assert any("db-pool-exhaustion-issue.md#Summary" in citation for citation in citations)
    assert len({item["source_path"] for item in payload["results"]}) >= 2
    assert [item["display_rank"] for item in payload["results"]] == [1, 2, 3]
    assert all("\n" not in item["snippet"] for item in payload["results"])
    assert all("similarity_score" in item for item in payload["results"])
    assert all(item["relevance"] in {"high", "medium", "low"} for item in payload["results"])


def test_knowledge_ingest_requires_confirm_reset(indexed_knowledge_service) -> None:
    service, _ = indexed_knowledge_service
    app.dependency_overrides[get_knowledge_base_service] = lambda: service
    client = TestClient(app)

    try:
        response = client.post("/knowledge/ingest", json={"reset": True, "confirm_reset": False})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 400
    assert "confirm_reset=true" in response.json()["detail"]


class UnavailableKnowledgeService:
    collection_name = "sentinelops_knowledge"

    def rebuild_index(self, *, reset: bool = True):
        raise RuntimeError("retrieval backend unavailable")

    def search(self, *, query: str, top_k: int, document_types=None, incident_type_hint=None):
        raise RuntimeError("retrieval backend unavailable")


def test_knowledge_endpoints_return_503_when_backend_is_unavailable() -> None:
    app.dependency_overrides[get_knowledge_base_service] = lambda: UnavailableKnowledgeService()
    client = TestClient(app)

    try:
        ingest_response = client.post(
            "/knowledge/ingest",
            json={"reset": True, "confirm_reset": True},
        )
        search_response = client.post(
            "/knowledge/search",
            json={"query": "database timeout", "top_k": 3},
        )
    finally:
        app.dependency_overrides.clear()

    assert ingest_response.status_code == 503
    assert search_response.status_code == 503


class MissingEmbeddingModelKnowledgeService:
    collection_name = "sentinelops_knowledge"

    def rebuild_index(self, *, reset: bool = True):
        raise RuntimeError(
            "Ollama embedding model 'nomic-embed-text' is not installed. Pull it first with: ollama pull nomic-embed-text"
        )

    def search(self, *, query: str, top_k: int, document_types=None, incident_type_hint=None):
        raise RuntimeError(
            "Ollama embedding model 'nomic-embed-text' is not installed. Pull it first with: ollama pull nomic-embed-text"
        )


def test_knowledge_endpoints_surface_missing_embedding_model_as_503() -> None:
    app.dependency_overrides[get_knowledge_base_service] = lambda: MissingEmbeddingModelKnowledgeService()
    client = TestClient(app)

    try:
        ingest_response = client.post(
            "/knowledge/ingest",
            json={"reset": False, "confirm_reset": False},
        )
        search_response = client.post(
            "/knowledge/search",
            json={"query": "database timeout", "top_k": 3},
        )
    finally:
        app.dependency_overrides.clear()

    assert ingest_response.status_code == 503
    assert "knowledge ingest" in ingest_response.json()["detail"].lower()
    assert search_response.status_code == 503
    assert "knowledge search" in search_response.json()["detail"].lower()
