from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from app.rag.models import KnowledgeDocument
from app.schemas import DocumentType, IncidentType
from app.settings import Settings

KNOWN_DOCUMENT_TYPES = {
    "runbooks": "runbook",
    "readmes": "readme",
    "github_issues": "github_issue",
    "troubleshooting_notes": "troubleshooting_note",
}
WORKSPACE_DOC_DIR_HINTS = {"docs", "runbooks", "ops", "deploy", "k8s", "helm", ".github"}
WORKSPACE_SPECIAL_FILENAMES = {
    "docker-compose.yml",
    "docker-compose.yaml",
    "compose.yml",
    "compose.yaml",
    ".env.example",
}
WORKSPACE_TEXT_SUFFIXES = {".md", ".mdx", ".txt", ".rst", ".yaml", ".yml", ".toml", ".json"}


class KnowledgeDocumentLoader:
    def __init__(self, settings: Settings):
        self.settings = settings

    def load_documents(self) -> list[KnowledgeDocument]:
        documents: list[KnowledgeDocument] = []
        seen_source_paths: set[str] = set()

        for document in (
            *self._load_workspace_documents(),
            *self._load_knowledge_directory(),
            *self._load_incident_templates(),
            *self._load_prior_incidents(),
        ):
            if document.source_path in seen_source_paths:
                continue
            seen_source_paths.add(document.source_path)
            documents.append(document)

        return sorted(documents, key=lambda document: document.source_path.lower())

    def _load_workspace_documents(self) -> list[KnowledgeDocument]:
        workspace_root = self.settings.workspace_root
        if not workspace_root.exists():
            return []

        documents: list[KnowledgeDocument] = []
        for path in self._iter_workspace_documents(workspace_root):
            relative_path = self.settings.workspace_relative_path(path)
            frontmatter, body = self._extract_frontmatter(path.read_text(encoding="utf-8", errors="replace"))
            title = str(frontmatter.get("title") or path.stem.replace("-", " ").replace("_", " ").title())
            incident_type = self._coerce_incident_type(frontmatter.get("incident_type"))
            tags = self._parse_tags(frontmatter.get("tags"))
            service = self._optional_string(frontmatter.get("service"))
            documents.append(
                KnowledgeDocument(
                    document_id=self._document_id(relative_path),
                    source_path=relative_path,
                    document_type=self._document_type_for_path(path),
                    title=title,
                    content=body,
                    incident_type=incident_type,
                    tags=tags,
                    service=service,
                )
            )
        return documents

    def _load_knowledge_directory(self) -> list[KnowledgeDocument]:
        knowledge_dir = self.settings.knowledge_base_dir
        if not knowledge_dir.exists():
            return []

        documents: list[KnowledgeDocument] = []
        for path in sorted(knowledge_dir.rglob("*.md")):
            relative_path = self.settings.workspace_relative_path(path)
            doc_type = self._document_type_for_path(path)
            content = path.read_text(encoding="utf-8")
            frontmatter, body = self._extract_frontmatter(content)
            title = str(frontmatter.get("title") or path.stem.replace("-", " ").title())
            incident_type = self._coerce_incident_type(frontmatter.get("incident_type"))
            tags = self._parse_tags(frontmatter.get("tags"))
            service = self._optional_string(frontmatter.get("service"))
            documents.append(
                KnowledgeDocument(
                    document_id=self._document_id(relative_path),
                    source_path=relative_path,
                    document_type=doc_type,
                    title=title,
                    content=body,
                    incident_type=incident_type,
                    tags=tags,
                    service=service,
                )
            )

        return documents

    def _load_incident_templates(self) -> list[KnowledgeDocument]:
        documents: list[KnowledgeDocument] = []
        for path in sorted(self.settings.incident_templates_dir.glob("*.md")):
            relative_path = self.settings.workspace_relative_path(path)
            incident_type = self._coerce_incident_type(path.stem)
            title = f"{path.stem.replace('-', ' ').title()} incident template"
            documents.append(
                KnowledgeDocument(
                    document_id=self._document_id(relative_path),
                    source_path=relative_path,
                    document_type="incident_template",
                    title=title,
                    content=path.read_text(encoding="utf-8"),
                    incident_type=incident_type,
                )
            )
        return documents

    def _load_prior_incidents(self) -> list[KnowledgeDocument]:
        documents: list[KnowledgeDocument] = []
        for path in sorted(self.settings.incident_history_dir.glob("*.json")):
            relative_path = self.settings.workspace_relative_path(path)
            payload = json.loads(path.read_text(encoding="utf-8-sig"))
            incident_type = self._coerce_incident_type(payload.get("incident_type"))
            title = f"{str(payload.get('incident_type', 'incident')).replace('-', ' ').title()} prior incident"
            content = self._render_prior_incident_markdown(payload)
            documents.append(
                KnowledgeDocument(
                    document_id=self._document_id(relative_path),
                    source_path=relative_path,
                    document_type="prior_incident",
                    title=title,
                    content=content,
                    incident_type=incident_type,
                    tags=self._parse_tags(payload.get("source_citations")),
                )
            )
        return documents

    def _render_prior_incident_markdown(self, payload: dict[str, object]) -> str:
        citations = payload.get("source_citations") or []
        citation_lines = "\n".join(f"- {item}" for item in citations if isinstance(item, str)) or "- None"
        candidate_paths = payload.get("candidate_log_paths") or []
        candidate_lines = "\n".join(
            f"- {item}" for item in candidate_paths if isinstance(item, str)
        ) or "- None"

        return f"""
# Prior Incident Summary

## Request
{payload.get("request", "Unknown request")}

## Severity
{payload.get("severity", "unknown")}

## Retrieval Status
{payload.get("retrieval_status", "not_used")}

## Manager Summary
{payload.get("manager_summary", "No summary available")}

## Suspected Root Cause
{payload.get("suspected_root_cause", "No root cause available")}

## Candidate Logs
{candidate_lines}

## Source Citations
{citation_lines}
""".strip()

    def _document_type_for_path(self, path: Path) -> DocumentType:
        for segment in path.parts:
            if segment in KNOWN_DOCUMENT_TYPES:
                return KNOWN_DOCUMENT_TYPES[segment]  # type: ignore[return-value]
        if path.name.lower().startswith("readme"):
            return "readme"
        if path.parent.name == "runbooks":
            return "runbook"
        return "troubleshooting_note"

    def _iter_workspace_documents(self, workspace_root: Path) -> list[Path]:
        candidates: list[Path] = []
        ignore_dirs = {entry.lower() for entry in self.settings.workspace_ignore_dirs}
        seen_paths: set[Path] = set()

        for configured_root in self.settings.effective_workspace_doc_root_paths():
            if not configured_root.exists():
                continue

            if configured_root.is_file():
                if self._is_workspace_document(workspace_root, configured_root):
                    seen_paths.add(configured_root.resolve())
                continue

            for root, dirs, files in os.walk(configured_root, topdown=True):
                root_path = Path(root)
                if root_path != workspace_root and root_path.name.lower() == ".sentinelops":
                    dirs[:] = []
                    continue

                dirs[:] = [name for name in dirs if name.lower() not in ignore_dirs]
                for file_name in files:
                    path = root_path / file_name
                    if self._is_workspace_document(workspace_root, path):
                        seen_paths.add(path.resolve())
        candidates.extend(seen_paths)
        return sorted(candidates)

    def _is_workspace_document(self, workspace_root: Path, path: Path) -> bool:
        if not path.is_file():
            return False

        relative_parts = path.relative_to(workspace_root).parts
        lowered_parts = [part.lower() for part in relative_parts]
        filename = path.name.lower()

        if filename.startswith("readme"):
            return True
        if filename in WORKSPACE_SPECIAL_FILENAMES:
            return True
        if filename.startswith("dockerfile"):
            return True
        if filename.startswith(".env.") and filename.endswith(".example"):
            return True
        if len(lowered_parts) >= 2 and lowered_parts[0] == ".github" and lowered_parts[1] == "workflows":
            return path.suffix.lower() in {".yml", ".yaml"}
        if any(part in WORKSPACE_DOC_DIR_HINTS for part in lowered_parts):
            return path.suffix.lower() in WORKSPACE_TEXT_SUFFIXES
        return False

    @staticmethod
    def _extract_frontmatter(content: str) -> tuple[dict[str, str], str]:
        stripped = content.lstrip()
        if not stripped.startswith("---"):
            return {}, content

        lines = stripped.splitlines()
        if len(lines) < 3 or lines[0].strip() != "---":
            return {}, content

        frontmatter: dict[str, str] = {}
        end_index = None
        for index, line in enumerate(lines[1:], start=1):
            if line.strip() == "---":
                end_index = index
                break
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            frontmatter[key.strip()] = value.strip()

        if end_index is None:
            return {}, content

        body = "\n".join(lines[end_index + 1 :]).strip()
        return frontmatter, body

    @staticmethod
    def _parse_tags(value: object) -> list[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return []

    @staticmethod
    def _optional_string(value: object) -> str | None:
        if value is None:
            return None
        cleaned = str(value).strip()
        return cleaned or None

    @staticmethod
    def _document_id(source_path: str) -> str:
        digest = hashlib.sha1(source_path.encode("utf-8")).hexdigest()
        return f"doc-{digest[:16]}"

    @staticmethod
    def _coerce_incident_type(value: object) -> IncidentType | None:
        if value is None:
            return None
        cleaned = str(value).strip().lower()
        allowed = {
            "api",
            "authentication",
            "configuration",
            "database",
            "deployment",
            "disk",
            "memory",
            "network",
            "performance",
            "queue",
            "security",
            "service",
        }
        return cleaned if cleaned in allowed else None
