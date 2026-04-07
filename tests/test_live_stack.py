from __future__ import annotations

import os
from pathlib import Path
from uuid import uuid4

import pytest

from app.ollama_client import OllamaGateway
from app.rag.chunker import MarkdownChunker
from app.rag.loader import KnowledgeDocumentLoader
from app.rag.service import KnowledgeBaseService, OllamaEmbeddingProvider
from app.rag.store_factory import build_knowledge_store
from app.settings import PROJECT_ROOT, Settings

RUN_LIVE_TESTS = os.getenv("SENTINELOPS_RUN_LIVE_TESTS") == "1"

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not RUN_LIVE_TESTS,
        reason="Set SENTINELOPS_RUN_LIVE_TESTS=1 to run live Ollama and Chroma integration checks.",
    ),
]


def test_live_ollama_and_chroma_roundtrip() -> None:
    knowledge_dir = _create_live_knowledge_dir()
    collection_name = f"sentinelops_live_{uuid4().hex[:10]}"
    settings = Settings(
        knowledge_base_dir=knowledge_dir,
        incident_history_dir=PROJECT_ROOT / "data" / "recent_incidents",
        incident_templates_dir=PROJECT_ROOT / "data" / "incident_templates",
        knowledge_store_backend="chroma",
        chroma_client_mode="http",
        chroma_host=os.getenv("SENTINELOPS_LIVE_CHROMA_HOST", "127.0.0.1"),
        chroma_port=int(os.getenv("SENTINELOPS_LIVE_CHROMA_PORT", "8012")),
        chroma_ssl=os.getenv("SENTINELOPS_LIVE_CHROMA_SSL", "false").lower() == "true",
        knowledge_collection_name=collection_name,
        knowledge_auto_ingest=False,
        analyze_model=os.getenv("SENTINELOPS_LIVE_CHAT_MODEL", "llama3.2"),
        investigate_model=os.getenv("SENTINELOPS_LIVE_CHAT_MODEL", "llama3.2"),
        embedding_model=os.getenv("SENTINELOPS_LIVE_EMBED_MODEL", "embeddinggemma"),
    )

    gateway = OllamaGateway(settings)
    embedding_provider = OllamaEmbeddingProvider(settings=settings, gateway=gateway)
    service = KnowledgeBaseService(
        settings=settings,
        embedding_provider=embedding_provider,
        loader=KnowledgeDocumentLoader(settings),
        chunker=MarkdownChunker(settings),
        store=build_knowledge_store(settings),
    )

    ingest = service.rebuild_index(reset=True)
    hits = service.search(
        query="database timeout and connection pool exhaustion",
        top_k=2,
        incident_type_hint="database",
    )

    assert ingest.chunk_count >= 1
    assert hits, "Expected live retrieval hits from Chroma."
    assert any("live-integration-database-runbook.md" in hit.source_path for hit in hits)


def _create_live_knowledge_dir() -> Path:
    live_dir = PROJECT_ROOT / "data" / "runtime" / "live_integration" / uuid4().hex
    runbook_dir = live_dir / "runbooks"
    runbook_dir.mkdir(parents=True, exist_ok=True)
    (runbook_dir / "live-integration-database-runbook.md").write_text(
        """---
title: Live integration database runbook
incident_type: database
---

# Symptoms

Database timeout incidents often include connection pool exhaustion and stalled workers waiting on postgres.

# Checks

Confirm the database is reachable and compare the failing run with the previous healthy baseline.
""",
        encoding="utf-8",
    )
    return live_dir
