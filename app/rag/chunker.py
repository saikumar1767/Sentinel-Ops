from __future__ import annotations

import hashlib
import re

from app.log_utils import truncate_text
from app.rag.models import KnowledgeChunk, KnowledgeDocument
from app.settings import Settings

HEADER_PATTERN = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")


class MarkdownChunker:
    def __init__(self, settings: Settings):
        self.settings = settings

    def chunk_document(self, document: KnowledgeDocument) -> list[KnowledgeChunk]:
        sections = self._split_sections(document.content)
        if not sections:
            sections = [(None, document.content.strip())]

        chunks: list[KnowledgeChunk] = []
        chunk_index = 0
        for section_path, section_text in sections:
            if not section_text.strip():
                continue
            for part_index, body in enumerate(self._split_section_body(section_text), start=1):
                chunk_index += 1
                section_label = section_path or None
                citation = document.source_path
                if section_label:
                    citation = f"{citation}#{section_label.replace(' > ', ' / ')}"

                embedding_text = "\n".join(
                    value
                    for value in [
                        document.title.strip(),
                        section_label or "",
                        body.strip(),
                    ]
                    if value
                )
                chunk_id = self._chunk_id(document.source_path, section_label, part_index)
                chunks.append(
                    KnowledgeChunk(
                        chunk_id=chunk_id,
                        document_id=document.document_id,
                        source_path=document.source_path,
                        document_type=document.document_type,
                        title=document.title,
                        content=truncate_text(body.strip(), self.settings.chunk_target_chars + 120),
                        embedding_text=embedding_text,
                        citation=citation,
                        section_path=section_label,
                        incident_type=document.incident_type,
                        service=document.service,
                        chunk_index=chunk_index,
                    )
                )

        return chunks

    def _split_sections(self, content: str) -> list[tuple[str | None, str]]:
        lines = content.splitlines()
        sections: list[tuple[str | None, str]] = []
        header_stack: list[str] = []
        current_header: str | None = None
        buffer: list[str] = []

        def flush() -> None:
            text = "\n".join(buffer).strip()
            if text:
                sections.append((current_header, text))

        for line in lines:
            match = HEADER_PATTERN.match(line)
            if not match:
                buffer.append(line)
                continue

            flush()
            level = len(match.group(1))
            header_text = match.group(2).strip()
            header_stack[:] = header_stack[: level - 1]
            header_stack.append(header_text)
            current_header = " > ".join(header_stack)
            buffer = []

        flush()
        return sections

    def _split_section_body(self, section_text: str) -> list[str]:
        target = self.settings.chunk_target_chars
        paragraphs = [paragraph.strip() for paragraph in section_text.split("\n\n") if paragraph.strip()]
        if not paragraphs:
            return []

        chunks: list[str] = []
        current = ""
        for paragraph in paragraphs:
            candidate = paragraph if not current else f"{current}\n\n{paragraph}"
            if len(candidate) <= target:
                current = candidate
                continue

            if current:
                chunks.append(current)
                current = ""

            if len(paragraph) <= target:
                current = paragraph
            else:
                chunks.extend(self._split_long_text(paragraph))

        if current:
            chunks.append(current)

        return chunks

    def _split_long_text(self, text: str) -> list[str]:
        target = self.settings.chunk_target_chars
        overlap = self.settings.chunk_overlap_chars
        pieces: list[str] = []
        start = 0
        while start < len(text):
            end = min(len(text), start + target)
            pieces.append(text[start:end].strip())
            if end == len(text):
                break
            start = max(end - overlap, start + 1)
        return [piece for piece in pieces if piece]

    @staticmethod
    def _chunk_id(source_path: str, section_path: str | None, part_index: int) -> str:
        digest = hashlib.sha1(
            f"{source_path}::{section_path or 'root'}::{part_index}".encode("utf-8")
        ).hexdigest()
        return f"chunk-{digest[:16]}"
