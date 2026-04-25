from __future__ import annotations

import json
import math
import os
import tempfile
from collections import Counter
from pathlib import Path
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
        self._write_index_payload(payload)

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

    def upsert(
        self,
        *,
        chunks: list[KnowledgeChunk],
        embeddings: list[list[float]],
    ) -> int:
        if len(chunks) != len(embeddings):
            raise ValueError("Chunk and embedding counts must match.")
        if not chunks:
            return 0

        payload = self._load_payload()
        records = list(payload.get("records", []))
        document_ids = {chunk.document_id for chunk in chunks}
        retained_records = [
            record
            for record in records
            if not (
                isinstance(record, dict)
                and isinstance(record.get("metadata"), dict)
                and record["metadata"].get("document_id") in document_ids
            )
        ]
        retained_records.extend(
            {
                "chunk_id": chunk.chunk_id,
                "document": chunk.content,
                "embedding": embedding,
                "metadata": chunk.to_metadata(),
            }
            for chunk, embedding in zip(chunks, embeddings, strict=True)
        )
        self._write_index_payload(
            {
                "collection_name": self.collection_name,
                "records": retained_records,
            }
        )
        return len(chunks)

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
        return list(self._load_payload().get("records", []))

    def _load_payload(self) -> dict[str, Any]:
        if not self.index_path.is_file():
            return {
                "collection_name": self.collection_name,
                "records": [],
            }
        try:
            payload = json.loads(self.index_path.read_text(encoding="utf-8-sig"))
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                f"Knowledge index at {self.index_path} is not valid JSON. Rebuild the index before searching."
            ) from exc

        if not isinstance(payload, dict):
            raise RuntimeError(f"Knowledge index at {self.index_path} must contain a JSON object.")

        records = payload.get("records", [])
        if not isinstance(records, list):
            raise RuntimeError(f"Knowledge index at {self.index_path} must contain a records list.")

        validated_records: list[dict[str, Any]] = []
        for index, record in enumerate(records):
            if not isinstance(record, dict):
                raise RuntimeError(f"Knowledge index record {index} must be a JSON object.")
            if not isinstance(record.get("metadata"), dict):
                raise RuntimeError(f"Knowledge index record {index} is missing metadata.")
            if not isinstance(record.get("embedding"), list):
                raise RuntimeError(f"Knowledge index record {index} is missing an embedding vector.")
            if not str(record.get("chunk_id", "")).strip():
                raise RuntimeError(f"Knowledge index record {index} is missing a chunk_id.")
            validated_records.append(record)

        return {
            "collection_name": str(payload.get("collection_name") or self.collection_name),
            "records": validated_records,
        }

    def _write_index_payload(self, payload: dict[str, Any]) -> None:
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                "w",
                encoding="utf-8",
                dir=self.index_path.parent,
                prefix=f".{self.index_path.name}.",
                suffix=".tmp",
                delete=False,
            ) as handle:
                temp_path = Path(handle.name)
                json.dump(payload, handle, indent=2)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            temp_path.replace(self.index_path)
        finally:
            if temp_path is not None and temp_path.exists():
                temp_path.unlink()

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
