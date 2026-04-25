from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from re import sub

from app.schemas import (
    InvestigateRequest,
    InvestigateResponse,
    ListRecentIncidentsArgs,
    LoadIncidentTemplateArgs,
    SavedIncidentSummary,
)
from app.settings import Settings


class IncidentTools:
    def __init__(self, settings: Settings):
        self.settings = settings

    def load_incident_template(self, args: LoadIncidentTemplateArgs) -> dict[str, object]:
        template_path = self.settings.incident_templates_dir / f"{args.incident_type}.md"
        if not template_path.is_file():
            raise FileNotFoundError(f"Incident template not found: {template_path.name}")

        checklist = [
            line.lstrip("- ").strip()
            for line in template_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

        return {
            "ok": True,
            "incident_type": args.incident_type,
            "checklist": checklist[:6],
            "truncated": len(checklist) > 6,
        }

    def list_recent_incidents(self, args: ListRecentIncidentsArgs) -> dict[str, object]:
        incident_dir = self.settings.incident_history_dir
        incident_dir.mkdir(parents=True, exist_ok=True)

        incidents: list[SavedIncidentSummary] = []
        for path in sorted(incident_dir.glob("*.json"), reverse=True):
            payload = json.loads(path.read_text(encoding="utf-8-sig"))
            incidents.append(SavedIncidentSummary.model_validate(payload))

        incidents.sort(key=lambda item: item.created_at, reverse=True)
        selected = incidents[: args.limit]

        return {
            "ok": True,
            "incidents": [
                {
                    "created_at": incident.created_at.isoformat(),
                    "incident_type": incident.incident_type,
                    "severity": incident.severity,
                    "manager_summary": incident.manager_summary,
                }
                for incident in selected
            ],
            "truncated": len(incidents) > args.limit,
        }

    def save_incident(
        self,
        request: InvestigateRequest,
        response: InvestigateResponse,
    ) -> Path:
        incident_dir = self.settings.incident_history_dir
        incident_dir.mkdir(parents=True, exist_ok=True)

        created_at = datetime.now(timezone.utc)
        slug = sub(r"[^a-z0-9]+", "-", response.incident_type.lower()).strip("-") or "incident"
        filename = f"{created_at.strftime('%Y%m%dT%H%M%S%fZ')}-{slug}.json"

        summary = SavedIncidentSummary(
            created_at=created_at,
            request=request.prompt,
            candidate_log_paths=request.candidate_log_paths,
            incident_type=response.incident_type,
            severity=response.severity,
            manager_summary=response.manager_summary,
            suspected_root_cause=response.suspected_root_cause,
            top_error_lines=response.top_error_lines,
            next_steps=response.next_steps,
            source_citations=response.source_citations,
            retrieval_status=response.retrieval_status,
            root_cause_diagnostics=response.root_cause_diagnostics,
            confidence=response.confidence,
        )

        target_path = incident_dir / filename
        target_path.write_text(summary.model_dump_json(indent=2), encoding="utf-8")
        self._prune_incidents(incident_dir)
        return target_path

    def _prune_incidents(self, incident_dir: Path) -> None:
        incidents = sorted(incident_dir.glob("*.json"), reverse=True)
        for stale_path in incidents[self.settings.persisted_incident_limit :]:
            stale_path.unlink(missing_ok=True)
