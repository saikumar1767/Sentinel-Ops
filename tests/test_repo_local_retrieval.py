from __future__ import annotations

from app.schemas import InvestigateRequest, RetrievalHit
from app.rag.service import KnowledgeBaseService
from app.services.analyze_service import AnalyzeService
from app.services.investigation_service import InvestigationContext, InvestigationService
from app.settings import Settings


def retrieval_hit(
    *,
    source_path: str,
    citation: str,
    section_path: str,
    similarity_score: float,
) -> RetrievalHit:
    return RetrievalHit(
        chunk_id=f"chunk-{citation}",
        document_type="runbook",
        source_path=source_path,
        citation=citation,
        snippet="Drain checkout workers before recycling database connections.",
        title="Database recovery",
        section_path=section_path,
        incident_type="database",
        similarity_score=similarity_score,
    )


class StubRetriever:
    def __init__(self, hits: list[RetrievalHit]):
        self.hits = hits

    def search(self, **_: object) -> list[RetrievalHit]:
        return list(self.hits)


class StubEmbeddingProvider:
    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [[float(len(texts[0]))]]


class RecordingStore:
    def __init__(self, hits: list[RetrievalHit], *, count: int = 24):
        self.hits = hits
        self._count = count
        self.query_top_k: int | None = None

    @property
    def collection_name(self) -> str:
        return "test"

    def rebuild(self, **_: object) -> object:
        raise NotImplementedError

    def count(self) -> int:
        return self._count

    def query(self, **kwargs: object) -> list[RetrievalHit]:
        self.query_top_k = int(kwargs["top_k"])
        return list(self.hits)


def test_analyze_retrieval_prefers_workspace_runbook_over_bundled_knowledge() -> None:
    bundled_hit = retrieval_hit(
        source_path=".sentinelops/data/knowledge/runbooks/database-timeout-runbook.md",
        citation=".sentinelops/data/knowledge/runbooks/database-timeout-runbook.md#Symptoms",
        section_path="Symptoms",
        similarity_score=0.99,
    )
    workspace_hit = retrieval_hit(
        source_path="runbooks/database.md",
        citation="runbooks/database.md#Recovery",
        section_path="Recovery",
        similarity_score=0.45,
    )
    service = AnalyzeService(
        settings=Settings(retrieval_top_k=2),
        gateway=object(),  # not used by this retrieval-path test
        retriever=StubRetriever([bundled_hit, workspace_hit]),
    )

    hits, status = service._retrieve_supporting_evidence(
        query="database connection timeout and pool exhaustion",
        incident_type_hint="database",
    )

    assert status == "used"
    assert [hit.citation for hit in hits][:2] == [
        "runbooks/database.md#Recovery",
        ".sentinelops/data/knowledge/runbooks/database-timeout-runbook.md#Symptoms",
    ]


def test_investigation_retrieval_prefers_workspace_runbook_over_bundled_knowledge() -> None:
    bundled_hit = retrieval_hit(
        source_path=".sentinelops/data/knowledge/runbooks/database-timeout-runbook.md",
        citation=".sentinelops/data/knowledge/runbooks/database-timeout-runbook.md#Symptoms",
        section_path="Symptoms",
        similarity_score=0.99,
    )
    workspace_hit = retrieval_hit(
        source_path="runbooks/database.md",
        citation="runbooks/database.md#Recovery",
        section_path="Recovery",
        similarity_score=0.45,
    )
    service = InvestigationService(
        settings=Settings(retrieval_top_k=2),
        gateway=object(),  # not used by this retrieval-path test
        tool_registry=object(),  # not used by this retrieval-path test
        retriever=StubRetriever([bundled_hit, workspace_hit]),
    )
    request = InvestigateRequest(
        prompt="Investigate database timeouts and connection pool exhaustion.",
        incident_type_hint="database",
    )
    context = InvestigationContext(
        candidate_log_paths=[],
        cached_results={},
        baseline_records=[],
        planner_records=[],
        support_records=[],
        retrieval_hits=[],
        retrieval_status="not_used",
    )

    hits, status = service._retrieve_knowledge(request, context)

    assert status == "used"
    assert [hit.citation for hit in hits][:2] == [
        "runbooks/database.md#Recovery",
        ".sentinelops/data/knowledge/runbooks/database-timeout-runbook.md#Symptoms",
    ]


def test_knowledge_search_overfetches_before_reranking() -> None:
    store = RecordingStore(
        [
            retrieval_hit(
                source_path="runbooks/database.md",
                citation="runbooks/database.md#Recovery",
                section_path="Recovery",
                similarity_score=0.45,
            )
        ],
        count=24,
    )
    service = KnowledgeBaseService(
        settings=Settings(knowledge_auto_ingest=False),
        embedding_provider=StubEmbeddingProvider(),
        loader=object(),
        chunker=object(),
        store=store,
    )

    service.search(
        query="database timeout",
        top_k=4,
        incident_type_hint="database",
        overfetch_multiplier=4,
    )

    assert store.query_top_k == 16
