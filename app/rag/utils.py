from __future__ import annotations

import re

from app.log_utils import dedupe_preserve_order
from app.schemas import DocumentType, RetrievalHit

DEFAULT_RETRIEVAL_DOCUMENT_TYPES: list[DocumentType] = [
    "runbook",
    "readme",
    "incident_template",
    "github_issue",
    "troubleshooting_note",
]

ANALYZE_RETRIEVAL_DOCUMENT_TYPES: list[DocumentType] = [
    "runbook",
    "readme",
    "github_issue",
    "troubleshooting_note",
]

INVESTIGATION_RETRIEVAL_DOCUMENT_TYPES: list[DocumentType] = [
    "runbook",
    "readme",
    "github_issue",
    "troubleshooting_note",
]


def format_retrieval_hits_for_prompt(hits: list[RetrievalHit]) -> str:
    if not hits:
        return "No retrieved knowledge evidence was found."

    lines = []
    for hit in hits:
        lines.append(f"- {hit.citation}: {hit.snippet}")
    return "\n".join(lines)


def retrieval_snippets(hits: list[RetrievalHit], limit: int = 4) -> list[str]:
    return dedupe_preserve_order(hit.snippet for hit in hits)[:limit]


def retrieval_citations(hits: list[RetrievalHit], limit: int = 6) -> list[str]:
    return dedupe_preserve_order(hit.citation for hit in hits)[:limit]


def clean_retrieval_snippet_text(text: str) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    normalized_lines: list[str] = []
    for line in lines:
        normalized = line.lstrip("- ").strip()
        normalized = re.sub(r"\s+", " ", normalized).rstrip(" ;")
        if normalized:
            normalized_lines.append(normalized)

    if not normalized_lines:
        return ""
    if len(normalized_lines) == 1:
        return normalized_lines[0]
    return " ".join(
        sentence if sentence.endswith(".") else f"{sentence}."
        for sentence in normalized_lines
    ).strip()


def retrieval_source_priority(hit: RetrievalHit) -> int:
    source_path = hit.source_path.replace("\\", "/").lower()
    if source_path.startswith(".sentinelops/data/"):
        return 1
    return 0


def curate_knowledge_search_hits(
    hits: list[RetrievalHit],
    *,
    query: str,
    limit: int,
) -> list[RetrievalHit]:
    if not hits or limit <= 0:
        return []

    ranked = sorted(
        hits,
        key=lambda hit: (
            retrieval_source_priority(hit),
            _knowledge_search_priority(hit, query),
            -(hit.similarity_score or 0.0),
            hit.citation,
        ),
    )

    curated: list[RetrievalHit] = []
    seen_citations: set[str] = set()
    seen_sources: set[str] = set()

    for hit in ranked:
        if hit.citation in seen_citations or hit.source_path in seen_sources:
            continue
        curated.append(hit)
        seen_citations.add(hit.citation)
        seen_sources.add(hit.source_path)
        if len(curated) == limit:
            return _finalize_curated_hits(curated)

    for hit in ranked:
        if hit.citation in seen_citations:
            continue
        curated.append(hit)
        seen_citations.add(hit.citation)
        if len(curated) == limit:
            break

    return _finalize_curated_hits(curated)


def _knowledge_search_priority(hit: RetrievalHit, query: str) -> int:
    intent = _knowledge_search_intent(query)
    section = (hit.section_path or "").lower()
    document_type = hit.document_type

    if intent == "action":
        if "mitigation" in section or "resolution" in section:
            return 0
        if "check" in section:
            return 1
        if document_type == "troubleshooting_note":
            return 2
        if "symptom" in section or "summary" in section or "operational notes" in section:
            return 3
        return 4

    if document_type == "runbook" and "symptom" in section:
        return 0
    if document_type == "github_issue" and "summary" in section:
        return 1
    if document_type == "readme" and any(
        token in section for token in ("operational notes", "investigation guidance", "troubleshooting")
    ):
        return 2
    if document_type == "troubleshooting_note":
        return 3
    if "summary" in section or "overview" in section:
        return 4
    if "check" in section:
        return 5
    if "mitigation" in section or "resolution" in section:
        return 6
    return 7


def _knowledge_search_intent(query: str) -> str:
    words = set(re.findall(r"[a-z0-9]+", query.lower()))
    if words.intersection({"fix", "mitigate", "resolve", "remediate", "recover", "restore", "repair"}):
        return "action"
    return "explain"


def _finalize_curated_hits(hits: list[RetrievalHit]) -> list[RetrievalHit]:
    finalized: list[RetrievalHit] = []
    for rank, hit in enumerate(hits, start=1):
        similarity_score = hit.similarity_score
        finalized.append(
            hit.model_copy(
                update={
                    "snippet": clean_retrieval_snippet_text(hit.snippet),
                    "relevance": _relevance_label_for_similarity(similarity_score),
                    "display_rank": rank,
                }
            )
        )
    return finalized


def _relevance_label_for_similarity(similarity_score: float | None) -> str | None:
    if similarity_score is None:
        return None
    if similarity_score >= 0.55:
        return "high"
    if similarity_score >= 0.45:
        return "medium"
    return "low"
