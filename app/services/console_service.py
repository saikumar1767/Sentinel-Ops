from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from app.schemas import (
    ConsoleOverviewResponse,
    ConsoleTimelineEntry,
    ConsoleTimelineResponse,
    IncidentLibraryResponse,
    IncidentProfileResponse,
    SavedIncidentSummary,
)
from app.services.evaluation_service import EvaluationSummaryService
from app.settings import Settings


class ConsoleService:
    def __init__(
        self,
        *,
        settings: Settings,
        evaluation_service: EvaluationSummaryService,
    ) -> None:
        self.settings = settings
        self.evaluation_service = evaluation_service

    def list_incidents(self) -> IncidentLibraryResponse:
        incidents = sorted(
            (self._load_incident(path) for path in self._incident_paths()),
            key=lambda incident: (incident.recommended_order, incident.incident_id),
        )
        return IncidentLibraryResponse(
            incident_count=len(incidents),
            incidents=incidents,
        )

    def get_incident(self, incident_id: str) -> IncidentProfileResponse:
        for path in self._incident_paths():
            incident = self._load_incident(path)
            if incident.incident_id == incident_id:
                return incident
        raise KeyError(f"Incident profile '{incident_id}' was not found.")

    def timeline(self) -> ConsoleTimelineResponse:
        runtime_entries = self._load_timeline_entries(self.settings.incident_history_dir, source="runtime")
        reference_entries = self._load_timeline_entries(self.settings.reference_incidents_dir, source="reference")
        selected = self._select_timeline_entries(
            runtime_entries=runtime_entries,
            reference_entries=reference_entries,
            limit=self.settings.console_timeline_limit,
        )
        return ConsoleTimelineResponse(
            total_entries=len(selected),
            entries=selected,
        )

    def overview(self) -> ConsoleOverviewResponse:
        incident_library = self.list_incidents()
        timeline = self.timeline()
        eval_summary = self.evaluation_service.build_summary()
        return ConsoleOverviewResponse(
            generated_at=datetime.now(UTC),
            launch_command="sentinelops",
            console_url="http://127.0.0.1:8000/console",
            workspace_name=self.settings.effective_workspace_name,
            workspace_root=str(self.settings.workspace_root),
            incident_count=incident_library.incident_count,
            timeline_entry_count=timeline.total_entries,
            library_categories=self._library_categories(incident_library.incidents),
            eval_total_cases=eval_summary.totals.total_cases,
            overall_pass_rate=eval_summary.totals.overall_pass_rate,
            analyze_pass_rate=eval_summary.analyze.pass_rate,
            investigate_pass_rate=eval_summary.investigate.pass_rate,
            rag_pass_rate=eval_summary.rag.pass_rate,
            workflow_pass_rate=eval_summary.workflow.pass_rate,
        )

    def _incident_paths(self) -> list[Path]:
        directory = self.settings.incident_library_dir
        directory.mkdir(parents=True, exist_ok=True)
        return sorted(directory.glob("*.json"))

    @staticmethod
    def _load_incident(path: Path) -> IncidentProfileResponse:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
        return IncidentProfileResponse.model_validate(payload)

    @staticmethod
    def _load_timeline_entries(directory: Path, *, source: str) -> list[ConsoleTimelineEntry]:
        directory.mkdir(parents=True, exist_ok=True)
        entries: list[ConsoleTimelineEntry] = []
        for path in sorted(directory.glob("*.json"), reverse=True):
            payload = json.loads(path.read_text(encoding="utf-8-sig"))
            summary = SavedIncidentSummary.model_validate(payload)
            entries.append(
                ConsoleTimelineEntry(
                    entry_id=f"{source}:{path.stem}",
                    source=source,  # type: ignore[arg-type]
                    created_at=summary.created_at,
                    incident_type=summary.incident_type,
                    severity=summary.severity,
                    manager_summary=summary.manager_summary,
                    suspected_root_cause=summary.suspected_root_cause,
                    retrieval_status=summary.retrieval_status,
                    confidence=summary.confidence,
                    source_citations=summary.source_citations,
                    candidate_log_paths=summary.candidate_log_paths,
                )
            )
        return entries

    @staticmethod
    def _select_timeline_entries(
        *,
        runtime_entries: list[ConsoleTimelineEntry],
        reference_entries: list[ConsoleTimelineEntry],
        limit: int,
    ) -> list[ConsoleTimelineEntry]:
        runtime_sorted = sorted(runtime_entries, key=lambda entry: (entry.created_at, entry.entry_id), reverse=True)
        reference_sorted = sorted(reference_entries, key=lambda entry: (entry.created_at, entry.entry_id), reverse=True)

        selected: list[ConsoleTimelineEntry] = []
        seen_keys: set[tuple[str, str, str]] = set()

        def add(entry: ConsoleTimelineEntry) -> None:
            if len(selected) >= limit:
                return

            key = (
                entry.incident_type,
                entry.manager_summary.strip().lower(),
                entry.source,
            )
            if key in seen_keys:
                return

            seen_keys.add(key)
            selected.append(entry)

        for entry in runtime_sorted[:2]:
            add(entry)

        for entry in reference_sorted:
            add(entry)

        for entry in runtime_sorted[2:]:
            add(entry)

        return selected[:limit]

    @staticmethod
    def _library_categories(incidents: list[IncidentProfileResponse]) -> list[str]:
        seen: set[str] = set()
        ordered: list[str] = []
        for incident in incidents:
            if incident.category in seen:
                continue
            seen.add(incident.category)
            ordered.append(incident.category)
        return ordered
