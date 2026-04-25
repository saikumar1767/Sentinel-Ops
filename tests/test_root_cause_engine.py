from __future__ import annotations

from datetime import datetime, timezone

from app.rag.chunker import MarkdownChunker
from app.rag.loader import KnowledgeDocumentLoader
from app.rag.service import KnowledgeBaseService
from app.rag.simple_store import SimpleKnowledgeStore
from app.schemas import InvestigateRequest, SavedIncidentSummary
from app.services.root_cause_engine import RootCauseEngine
from app.settings import Settings
from app.tools.tool_registry import ToolExecutionRecord


def test_root_cause_engine_builds_causal_database_hypothesis() -> None:
    records = [
        ToolExecutionRecord(
            name="read_log_file",
            arguments={"path": "data/logs/database-current.log"},
            ok=True,
            payload={
                "ok": True,
                "path": "data/logs/database-current.log",
                "selected_lines": [
                    "1: 2026-03-31 09:10:22 ERROR database connection timeout after 30 seconds",
                    "3: 2026-03-31 09:10:24 ERROR connection pool exhausted on primary-postgres",
                    "4: 2026-03-31 09:10:26 ERROR checkout request stalled waiting for free database connection",
                ],
            },
        ),
        ToolExecutionRecord(
            name="compare_two_logs",
            arguments={
                "path_a": "data/logs/database-previous.log",
                "path_b": "data/logs/database-current.log",
            },
            ok=True,
            payload={
                "ok": True,
                "path_a": "data/logs/database-previous.log",
                "path_b": "data/logs/database-current.log",
                "new_error_lines": [
                    "1: 2026-03-31 09:10:22 ERROR database connection timeout after 30 seconds"
                ],
            },
        ),
    ]

    report = RootCauseEngine().analyze(
        request=InvestigateRequest(
            prompt="Investigate the failing database run.",
            incident_type_hint="database",
        ),
        records=records,
        retrieval_hits=[],
    )

    assert report.incident_type == "database"
    assert report.severity == "high"
    assert report.regression_detected is True
    assert report.root_cause == (
        "Connection pool exhaustion on primary-postgres is causing repeated database timeouts "
        "and stalled checkout requests"
    )
    assert "connection_pool_exhaustion" in report.primary_hypothesis.supporting_signals
    assert report.timeline
    assert report.to_diagnostics().evidence_strength >= 0.75
    assert report.to_diagnostics().signals
    assert "Dominant hypothesis" in report.prompt_summary()


class KeywordEmbeddingProvider:
    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [[float("database" in text.lower()), float("timeout" in text.lower())] for text in texts]


def test_knowledge_service_indexes_completed_incident_memory(tmp_path) -> None:
    settings = Settings(
        knowledge_index_path=tmp_path / "knowledge-index.json",
        knowledge_base_dir=tmp_path / "knowledge",
        incident_templates_dir=tmp_path / "templates",
        incident_history_dir=tmp_path / "history",
        knowledge_auto_ingest=False,
        knowledge_store_backend="simple",
    )
    incident_path = settings.incident_history_dir / "20260425T000000000000Z-database.json"
    incident_path.parent.mkdir(parents=True, exist_ok=True)
    incident = SavedIncidentSummary(
        created_at=datetime.now(timezone.utc),
        request="Investigate database timeout.",
        candidate_log_paths=["logs/database-current.log"],
        incident_type="database",
        severity="high",
        manager_summary="Database requests timed out during startup.",
        suspected_root_cause="Connection pool exhaustion caused database timeouts.",
        source_citations=["read_log_file:logs/database-current.log"],
        retrieval_status="used",
        confidence=0.91,
    )
    incident_path.write_text(incident.model_dump_json(indent=2), encoding="utf-8")
    service = KnowledgeBaseService(
        settings=settings,
        embedding_provider=KeywordEmbeddingProvider(),
        loader=KnowledgeDocumentLoader(settings),
        chunker=MarkdownChunker(settings),
        store=SimpleKnowledgeStore(settings),
    )

    indexed_count = service.index_incident_summary(incident_path)
    hits = service.search(
        query="database timeout prior incident",
        top_k=1,
        incident_type_hint="database",
    )

    assert indexed_count >= 1
    assert hits
    assert hits[0].document_type == "prior_incident"
    assert "database" in hits[0].citation.lower()
