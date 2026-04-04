from __future__ import annotations

from app.rag.chroma_store import ChromaKnowledgeStore
from app.rag.models import KnowledgeStore
from app.rag.simple_store import SimpleKnowledgeStore
from app.settings import Settings


def build_knowledge_store(settings: Settings) -> KnowledgeStore:
    if settings.knowledge_store_backend == "chroma":
        return ChromaKnowledgeStore(settings)
    return SimpleKnowledgeStore(settings)
