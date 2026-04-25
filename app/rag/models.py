from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from app.schemas import DocumentType, IncidentType, KnowledgeIngestResponse, RetrievalHit


@dataclass
class KnowledgeDocument:
    document_id: str
    source_path: str
    document_type: DocumentType
    title: str
    content: str
    incident_type: IncidentType | None = None
    tags: list[str] = field(default_factory=list)
    service: str | None = None


@dataclass
class KnowledgeChunk:
    chunk_id: str
    document_id: str
    source_path: str
    document_type: DocumentType
    title: str
    content: str
    embedding_text: str
    citation: str
    section_path: str | None = None
    incident_type: IncidentType | None = None
    service: str | None = None
    chunk_index: int = 0

    def to_metadata(self) -> dict[str, str | int | float | bool]:
        metadata: dict[str, str | int | float | bool] = {
            "document_id": self.document_id,
            "source_path": self.source_path,
            "document_type": self.document_type,
            "title": self.title,
            "citation": self.citation,
            "chunk_index": self.chunk_index,
        }
        if self.section_path:
            metadata["section_path"] = self.section_path
        if self.incident_type:
            metadata["incident_type"] = self.incident_type
        if self.service:
            metadata["service"] = self.service
        return metadata


class EmbeddingProvider(Protocol):
    def embed_texts(self, texts: list[str]) -> list[list[float]]: ...


class KnowledgeStore(Protocol):
    @property
    def collection_name(self) -> str: ...

    def rebuild(
        self,
        *,
        chunks: list[KnowledgeChunk],
        embeddings: list[list[float]],
        reset: bool,
    ) -> KnowledgeIngestResponse: ...

    def upsert(
        self,
        *,
        chunks: list[KnowledgeChunk],
        embeddings: list[list[float]],
    ) -> int: ...

    def count(self) -> int: ...

    def query(
        self,
        *,
        query_embedding: list[float],
        top_k: int,
        document_types: list[DocumentType] | None = None,
        incident_type_hint: IncidentType | None = None,
    ) -> list[RetrievalHit]: ...


class RetrievalService(Protocol):
    def ensure_index(self) -> None: ...

    def rebuild_index(self, *, reset: bool = True) -> object: ...

    def index_incident_summary(self, incident_path: Path) -> int: ...

    def search(
        self,
        *,
        query: str,
        top_k: int,
        document_types: list[DocumentType] | None = None,
        incident_type_hint: IncidentType | None = None,
        overfetch_multiplier: int = 1,
    ) -> list[RetrievalHit]: ...
