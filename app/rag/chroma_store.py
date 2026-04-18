from __future__ import annotations

from collections import Counter
from typing import Any

import chromadb

from app.rag.chroma_runtime import ChromaRuntimeManager
from app.rag.models import KnowledgeChunk
from app.schemas import DocumentType, IncidentType, KnowledgeIngestResponse, RetrievalHit
from app.settings import Settings


class ChromaKnowledgeStore:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.runtime = ChromaRuntimeManager(settings)
        self._client = None

    @property
    def collection_name(self) -> str:
        return self.settings.knowledge_collection_name

    def _build_client(self):
        if self.settings.chroma_client_mode == "persistent":
            return chromadb.PersistentClient(path=self.settings.chroma_path)

        self.runtime.ensure_ready()
        return chromadb.HttpClient(
            host=self.settings.chroma_host,
            port=self.settings.chroma_port,
            ssl=self.settings.chroma_ssl,
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
            try:
                self._get_client().delete_collection(name=self.collection_name)
            except Exception:
                pass

        collection = self._get_client().get_or_create_collection(
            name=self.collection_name,
            embedding_function=None,
        )
        if chunks:
            collection.upsert(
                ids=[chunk.chunk_id for chunk in chunks],
                documents=[chunk.content for chunk in chunks],
                metadatas=[chunk.to_metadata() for chunk in chunks],
                embeddings=embeddings,
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
