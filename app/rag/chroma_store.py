from __future__ import annotations

import shutil
from collections import Counter
from pathlib import Path
from types import ModuleType
from typing import Any

from app.rag.chroma_runtime import ChromaRuntimeManager
from app.rag.models import KnowledgeChunk
from app.schemas import DocumentType, IncidentType, KnowledgeIngestResponse, RetrievalHit
from app.settings import Settings

chromadb: ModuleType | None = None
ChromaClientSettings: type | None = None


class ChromaKnowledgeStore:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.runtime = ChromaRuntimeManager(settings)
        self._client = None

    @property
    def collection_name(self) -> str:
        return self.settings.knowledge_collection_name

    def _build_client(self):
        chroma_module, chroma_settings_class = _load_chromadb()
        client_settings = chroma_settings_class(anonymized_telemetry=False)
        if self.settings.chroma_client_mode == "persistent":
            self.settings.chroma_path.mkdir(parents=True, exist_ok=True)
            return chroma_module.PersistentClient(
                path=str(self.settings.chroma_path),
                settings=client_settings,
            )

        self.runtime.ensure_ready()
        return chroma_module.HttpClient(
            host=self.settings.chroma_host,
            port=self.settings.chroma_port,
            ssl=self.settings.chroma_ssl,
            settings=client_settings,
        )

    def _get_client(self):
        if self._client is None:
            self._client = self._build_client()
        return self._client

    def rebuild(
        self,
        *,
        chunks: list[KnowledgeChunk],
        embeddings: list[list[float]],
        reset: bool,
    ) -> KnowledgeIngestResponse:
        if reset:
            self._reset_collection()

        collection = self._get_client().get_or_create_collection(
            name=self.collection_name,
            embedding_function=None,
        )
        batch_size = max(1, min(self.settings.embedding_batch_size, 32))
        for start in range(0, len(chunks), batch_size):
            batch_chunks = chunks[start : start + batch_size]
            batch_embeddings = embeddings[start : start + batch_size]
            collection.upsert(
                ids=[chunk.chunk_id for chunk in batch_chunks],
                documents=[chunk.content for chunk in batch_chunks],
                metadatas=[chunk.to_metadata() for chunk in batch_chunks],
                embeddings=batch_embeddings,
            )

        source_counts = Counter()
        seen_documents: dict[str, str] = {}
        for chunk in chunks:
            seen_documents.setdefault(chunk.document_id, chunk.document_type)
        for document_type in seen_documents.values():
            source_counts[document_type] += 1

        chunk_counts = Counter(chunk.document_type for chunk in chunks)
        document_count = len({chunk.document_id for chunk in chunks})
        return KnowledgeIngestResponse(
            collection_name=self.collection_name,
            document_count=document_count,
            chunk_count=len(chunks),
            source_counts=dict(source_counts),
            chunk_counts=dict(chunk_counts),
            status="indexed",
        )

    def count(self) -> int:
        collection = self._get_client().get_or_create_collection(
            name=self.collection_name,
            embedding_function=None,
        )
        return collection.count()

    def query(
        self,
        *,
        query_embedding: list[float],
        top_k: int,
        document_types: list[DocumentType] | None = None,
        incident_type_hint: IncidentType | None = None,
    ) -> list[RetrievalHit]:
        collection = self._get_client().get_or_create_collection(
            name=self.collection_name,
            embedding_function=None,
        )
        where = self._build_where(document_types=document_types, incident_type_hint=incident_type_hint)
        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            where=where,
            include=["documents", "metadatas", "distances"],
        )

        documents = results.get("documents") or [[]]
        metadatas = results.get("metadatas") or [[]]
        distances = results.get("distances") or [[]]
        ids = results.get("ids") or [[]]

        hits: list[RetrievalHit] = []
        for chunk_id, document, metadata, distance in zip(
            ids[0],
            documents[0],
            metadatas[0],
            distances[0],
        ):
            if metadata is None:
                continue
            score = round(1.0 / (1.0 + float(distance)), 4)
            hits.append(
                RetrievalHit(
                    chunk_id=str(chunk_id),
                    document_type=metadata["document_type"],
                    source_path=metadata["source_path"],
                    citation=metadata["citation"],
                    snippet=str(document).strip(),
                    title=metadata["title"],
                    section_path=metadata.get("section_path"),
                    incident_type=metadata.get("incident_type"),
                    similarity_score=score,
                )
            )

        return hits

    def _reset_collection(self) -> None:
        if self.settings.chroma_client_mode == "persistent" and self._client is None:
            self._reset_persistent_path(self.settings.chroma_path)
            return
        try:
            self._get_client().delete_collection(name=self.collection_name)
        except Exception:
            if self.settings.chroma_client_mode == "persistent":
                self._client = None
                self._reset_persistent_path(self.settings.chroma_path)
                return

    @staticmethod
    def _build_where(
        *,
        document_types: list[DocumentType] | None,
        incident_type_hint: IncidentType | None,
    ) -> dict[str, Any] | None:
        clauses: list[dict[str, Any]] = []
        if document_types:
            if len(document_types) == 1:
                clauses.append({"document_type": document_types[0]})
            else:
                clauses.append({"document_type": {"$in": document_types}})
        if incident_type_hint is not None:
            clauses.append({"incident_type": incident_type_hint})

        if not clauses:
            return None
        if len(clauses) == 1:
            return clauses[0]
        return {"$and": clauses}

    @staticmethod
    def _reset_persistent_path(path: Path) -> None:
        resolved = path.resolve()
        if resolved == resolved.parent:
            raise RuntimeError(f"Refusing to reset unsafe Chroma path: {resolved}")
        if resolved.exists():
            shutil.rmtree(resolved)
        resolved.mkdir(parents=True, exist_ok=True)


def _load_chromadb() -> tuple[ModuleType, type]:
    global chromadb, ChromaClientSettings
    if chromadb is None or ChromaClientSettings is None:
        import chromadb as chromadb_module
        from chromadb.config import Settings as chroma_settings_class

        chromadb = chromadb_module
        ChromaClientSettings = chroma_settings_class
    return chromadb, ChromaClientSettings
