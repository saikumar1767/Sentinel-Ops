from __future__ import annotations

from types import SimpleNamespace

from app.rag.chroma_store import ChromaKnowledgeStore
from app.rag.models import KnowledgeChunk
from app.settings import Settings


class FakeCollection:
    def __init__(self) -> None:
        self.upsert_sizes: list[int] = []

    def upsert(self, *, ids, documents, metadatas, embeddings) -> None:
        self.upsert_sizes.append(len(ids))
        assert len(ids) == len(documents) == len(metadatas) == len(embeddings)


class FakeClient:
    def __init__(self, collection: FakeCollection) -> None:
        self.collection = collection

    def delete_collection(self, *, name: str) -> None:
        return None

    def get_or_create_collection(self, *, name: str, embedding_function):
        return self.collection


def test_chroma_store_batches_large_rebuild_upserts(monkeypatch) -> None:
    settings = Settings(
        knowledge_store_backend="chroma",
        embedding_batch_size=16,
    )
    store = ChromaKnowledgeStore(settings)
    collection = FakeCollection()
    monkeypatch.setattr(store, "_get_client", lambda: FakeClient(collection))
    chunks = [
        KnowledgeChunk(
            chunk_id=f"chunk-{index}",
            document_id="doc-1",
            source_path="runbooks/database.md",
            document_type="runbook",
            title="Database",
            content=f"chunk {index}",
            embedding_text=f"chunk {index}",
            citation="runbooks/database.md#Database",
            incident_type="database",
            chunk_index=index,
        )
        for index in range(35)
    ]
    embeddings = [[float(index), 0.0, 1.0] for index in range(35)]

    result = store.rebuild(chunks=chunks, embeddings=embeddings, reset=True)

    assert result.chunk_count == 35
    assert collection.upsert_sizes == [16, 16, 3]


def test_chroma_store_uses_string_path_for_persistent_client(monkeypatch, tmp_path) -> None:
    captured: dict[str, str] = {}

    class FakePersistentClient:
        def __init__(self, *, path: str, settings) -> None:
            captured["path"] = path
            captured["telemetry"] = settings.anonymized_telemetry

    class FakeChromaSettings:
        def __init__(self, *, anonymized_telemetry: bool) -> None:
            self.anonymized_telemetry = anonymized_telemetry

    monkeypatch.setattr(
        "app.rag.chroma_store._load_chromadb",
        lambda: (SimpleNamespace(PersistentClient=FakePersistentClient), FakeChromaSettings),
    )
    settings = Settings(
        knowledge_store_backend="chroma",
        chroma_client_mode="persistent",
        chroma_path=tmp_path / "chroma-db",
    )

    client = ChromaKnowledgeStore(settings)._build_client()

    assert isinstance(client, FakePersistentClient)
    assert captured["path"] == str(tmp_path / "chroma-db")
    assert captured["telemetry"] is False
    assert (tmp_path / "chroma-db").is_dir()


def test_chroma_store_reset_recreates_persistent_path(tmp_path) -> None:
    chroma_path = tmp_path / "chroma-db"
    stale_file = chroma_path / "old-schema.sqlite"
    stale_file.parent.mkdir(parents=True)
    stale_file.write_text("stale", encoding="utf-8")
    settings = Settings(
        knowledge_store_backend="chroma",
        chroma_client_mode="persistent",
        chroma_path=chroma_path,
    )
    store = ChromaKnowledgeStore(settings)

    store._reset_collection()

    assert chroma_path.is_dir()
    assert not stale_file.exists()
