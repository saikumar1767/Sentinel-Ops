from __future__ import annotations

import json
import logging
from pathlib import Path
from itertools import islice
from time import perf_counter

from ollama import ResponseError

from app.cache import ExpiringCache
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
from app.telemetry import set_span_attributes, start_span

logger = logging.getLogger(__name__)


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
        metrics = getattr(getattr(embedding_provider, "gateway", None), "metrics", None)
        self._search_cache = ExpiringCache(
            name="knowledge_search",
            max_entries=settings.retrieval_cache_max_entries,
            metrics=metrics,
        )

    @property
    def collection_name(self) -> str:
        return self.store.collection_name

    def ensure_index(self) -> None:
        if self.store.count() == 0 and self.settings.knowledge_auto_ingest:
            self.rebuild_index(reset=True)

    def rebuild_index(self, *, reset: bool = True) -> KnowledgeIngestResponse:
        started = perf_counter()
        with start_span("knowledge.rebuild", {"knowledge.reset": reset}) as span:
            documents = self.loader.load_documents()
            chunks = []
            for document in documents:
                chunks.extend(self.chunker.chunk_document(document))

            embeddings = self.embedding_provider.embed_texts(
                [chunk.embedding_text for chunk in chunks]
            )
            result = self.store.rebuild(chunks=chunks, embeddings=embeddings, reset=reset)
            self._search_cache.clear()
            duration_ms = (perf_counter() - started) * 1000
            set_span_attributes(
                span,
                {
                    "knowledge.document_count": len(documents),
                    "knowledge.chunk_count": len(chunks),
                    "knowledge.duration_ms": round(duration_ms, 3),
                },
            )
            logger.info(
                "knowledge_rebuild documents=%s chunks=%s reset=%s duration_ms=%.3f",
                len(documents),
                len(chunks),
                reset,
                duration_ms,
            )
            return result

    def index_incident_summary(self, incident_path: Path) -> int:
        with start_span("knowledge.index_incident_memory") as span:
            document = self.loader.load_prior_incident_file(incident_path)
            chunks = self.chunker.chunk_document(document)
            embeddings = self.embedding_provider.embed_texts(
                [chunk.embedding_text for chunk in chunks]
            )
            indexed_count = self.store.upsert(chunks=chunks, embeddings=embeddings)
            self._search_cache.clear()
            set_span_attributes(
                span,
                {
                    "knowledge.document_type": document.document_type,
                    "knowledge.chunk_count": indexed_count,
                },
            )
            logger.info(
                "knowledge_index_incident_memory path=%s chunks=%s",
                document.source_path,
                indexed_count,
            )
            return indexed_count

    def search(
        self,
        *,
        query: str,
        top_k: int,
        document_types: list[DocumentType] | None = None,
        incident_type_hint: IncidentType | None = None,
        overfetch_multiplier: int = 1,
    ) -> list[RetrievalHit]:
        started = perf_counter()
        with start_span(
            "knowledge.search",
            {
                "knowledge.query_chars": len(query),
                "knowledge.top_k": top_k,
                "knowledge.incident_type_hint": incident_type_hint,
            },
        ) as span:
            self.ensure_index()
            if self.store.count() == 0:
                set_span_attributes(span, {"knowledge.result_count": 0, "knowledge.cache_hit": False})
                return []
            cache_key = self._cache_key(
                query=query,
                top_k=top_k,
                document_types=document_types,
                incident_type_hint=incident_type_hint,
                overfetch_multiplier=overfetch_multiplier,
            )
            if self.settings.retrieval_cache_enabled:
                cached_hits = self._search_cache.get(cache_key)
                if cached_hits is not None:
                    duration_ms = (perf_counter() - started) * 1000
                    set_span_attributes(
                        span,
                        {
                            "knowledge.result_count": len(cached_hits),
                            "knowledge.cache_hit": True,
                            "knowledge.duration_ms": round(duration_ms, 3),
                        },
                    )
                    logger.info(
                        "knowledge_search cache_hit=true top_k=%s incident_type_hint=%s duration_ms=%.3f",
                        top_k,
                        incident_type_hint,
                        duration_ms,
                    )
                    return cached_hits

            embedding = self.embedding_provider.embed_texts([query])[0]
            raw_top_k = min(
                self.store.count(),
                max(top_k * max(overfetch_multiplier, 1), top_k),
            )
            hits = self.store.query(
                query_embedding=embedding,
                top_k=raw_top_k,
                document_types=document_types,
                incident_type_hint=incident_type_hint,
            )
            result = [
                RetrievalHit(
                    **{
                        **hit.model_dump(),
                        "snippet": truncate_text(hit.snippet, self.settings.retrieval_snippet_chars),
                    }
                )
                for hit in hits
            ]
            if self.settings.retrieval_cache_enabled:
                self._search_cache.set(cache_key, result, self.settings.retrieval_cache_ttl_seconds)
            duration_ms = (perf_counter() - started) * 1000
            set_span_attributes(
                span,
                {
                    "knowledge.result_count": len(result),
                    "knowledge.cache_hit": False,
                    "knowledge.duration_ms": round(duration_ms, 3),
                },
            )
            logger.info(
                "knowledge_search cache_hit=false top_k=%s incident_type_hint=%s results=%s duration_ms=%.3f",
                top_k,
                incident_type_hint,
                len(result),
                duration_ms,
            )
            return result

    @staticmethod
    def _cache_key(
        *,
        query: str,
        top_k: int,
        document_types: list[DocumentType] | None,
        incident_type_hint: IncidentType | None,
        overfetch_multiplier: int,
    ) -> str:
        payload = {
            "query": query,
            "top_k": top_k,
            "document_types": document_types or [],
            "incident_type_hint": incident_type_hint,
            "overfetch_multiplier": overfetch_multiplier,
        }
        return json.dumps(payload, sort_keys=True, separators=(",", ":"))
