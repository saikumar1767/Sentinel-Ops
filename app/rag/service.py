from __future__ import annotations

from itertools import islice

from ollama import ResponseError

from app.log_utils import truncate_text
from app.ollama_client import EmbeddingGateway
from app.rag.chunker import MarkdownChunker
from app.rag.loader import KnowledgeDocumentLoader
from app.rag.models import EmbeddingProvider, KnowledgeStore, RetrievalService
from app.schemas import (
    DocumentType,
    IncidentType,
    KnowledgeIngestResponse,
    RetrievalHit,
)
from app.settings import Settings


class OllamaEmbeddingProvider(EmbeddingProvider):
    def __init__(self, settings: Settings, gateway: EmbeddingGateway):
        self.settings = settings
        self.gateway = gateway

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        embeddings: list[list[float]] = []
        batch_size = self.settings.embedding_batch_size
        for start in range(0, len(texts), batch_size):
            batch = list(islice(texts, start, start + batch_size))
            try:
                embeddings.extend(
                    self.gateway.embed(
                        model=self.settings.embedding_model,
                        texts=batch,
                    )
                )
            except ResponseError as exc:
                raise RuntimeError(
                    self._format_embedding_error(
                        model=self.settings.embedding_model,
                        error=exc,
                    )
                ) from exc
        return embeddings

    @staticmethod
    def _format_embedding_error(*, model: str, error: ResponseError) -> str:
        if error.status_code == 404:
            return (
                f"Ollama embedding model '{model}' is not installed. "
                f"Pull it first with: ollama pull {model}"
            )
        return f"Failed to generate embeddings with Ollama model '{model}': {error}"


class KnowledgeBaseService(RetrievalService):
    def __init__(
        self,
        settings: Settings,
        embedding_provider: EmbeddingProvider,
        loader: KnowledgeDocumentLoader,
        chunker: MarkdownChunker,
        store: KnowledgeStore,
    ):
        self.settings = settings
        self.embedding_provider = embedding_provider
        self.loader = loader
        self.chunker = chunker
        self.store = store

    @property
    def collection_name(self) -> str:
        return self.store.collection_name

    def ensure_index(self) -> None:
        if self.store.count() == 0 and self.settings.knowledge_auto_ingest:
            self.rebuild_index(reset=True)

    def rebuild_index(self, *, reset: bool = True) -> KnowledgeIngestResponse:
        documents = self.loader.load_documents()
        chunks = []
        for document in documents:
            chunks.extend(self.chunker.chunk_document(document))

        embeddings = self.embedding_provider.embed_texts(
            [chunk.embedding_text for chunk in chunks]
        )
        return self.store.rebuild(chunks=chunks, embeddings=embeddings, reset=reset)

    def search(
        self,
        *,
        query: str,
        top_k: int,
        document_types: list[DocumentType] | None = None,
        incident_type_hint: IncidentType | None = None,
    ) -> list[RetrievalHit]:
        self.ensure_index()
        if self.store.count() == 0:
            return []
        embedding = self.embedding_provider.embed_texts([query])[0]
        hits = self.store.query(
            query_embedding=embedding,
            top_k=top_k,
            document_types=document_types,
            incident_type_hint=incident_type_hint,
        )
        return [
            RetrievalHit(
                **{
                    **hit.model_dump(),
                    "snippet": truncate_text(hit.snippet, self.settings.retrieval_snippet_chars),
                }
            )
            for hit in hits
        ]
