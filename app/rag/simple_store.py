from __future__ import annotations

import json
import math
from collections import Counter
from typing import Any

from app.rag.models import KnowledgeChunk
from app.schemas import DocumentType, IncidentType, KnowledgeIngestResponse, RetrievalHit
from app.settings import Settings


class SimpleKnowledgeStore:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.index_path = settings.knowledge_index_path

    @property
    def collection_name(self) -> str:
        return self.settings.knowledge_collection_name

    def rebuild(
        self,
        *,
        chunks: list[KnowledgeChunk],
        embeddings: list[list[float]],
        reset: bool,
    ) -> KnowledgeIngestResponse:
        if len(chunks) != len(embeddings):
            raise ValueError("Chunk and embedding counts must match.")

        if reset and self.index_path.exists():
            self.index_path.unlink()

        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        records = [
            {
                "chunk_id": chunk.chunk_id,
                "document": chunk.content,
                "embedding": embedding,
                "metadata": chunk.to_metadata(),
            }
            for chunk, embedding in zip(chunks, embeddings, strict=True)
        ]
        payload = {
            "collection_name": self.collection_name,
            "records": records,
        }
        self.index_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

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
        return len(self._load_records())

    def query(
        self,
        *,
        query_embedding: list[float],
        top_k: int,
        document_types: list[DocumentType] | None = None,
        incident_type_hint: IncidentType | None = None,
    ) -> list[RetrievalHit]:
        ranked: list[tuple[float, dict[str, Any]]] = []
        for record in self._load_records():
            metadata = record["metadata"]
            if document_types and metadata.get("document_type") not in document_types:
                continue
            if incident_type_hint is not None and metadata.get("incident_type") != incident_type_hint:
                continue

            score = self._cosine_similarity(query_embedding, record["embedding"])
            ranked.append((score, record))

        ranked.sort(key=lambda item: item[0], reverse=True)
        hits: list[RetrievalHit] = []
        for score, record in ranked[:top_k]:
            metadata = record["metadata"]
            hits.append(
                RetrievalHit(
                    chunk_id=str(record["chunk_id"]),
                    document_type=metadata["document_type"],
                    source_path=metadata["source_path"],
                    citation=metadata["citation"],
                    snippet=str(record["document"]).strip(),
                    title=metadata["title"],
                    section_path=metadata.get("section_path"),
                    incident_type=metadata.get("incident_type"),
                    similarity_score=round(score, 4),
                )
            )
        return hits

    def _load_records(self) -> list[dict[str, Any]]:
        if not self.index_path.is_file():
            return []
        payload = json.loads(self.index_path.read_text(encoding="utf-8-sig"))
        return list(payload.get("records", []))

    @staticmethod
    def _cosine_similarity(left: list[float], right: list[float]) -> float:
        if not left or not right or len(left) != len(right):
            return 0.0
        dot = sum(a * b for a, b in zip(left, right, strict=True))
        left_norm = math.sqrt(sum(a * a for a in left))
        right_norm = math.sqrt(sum(b * b for b in right))
        if left_norm == 0 or right_norm == 0:
            return 0.0
        return dot / (left_norm * right_norm)
