from __future__ import annotations

import json
from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.dependencies import get_console_service
from app.main import app
from app.schemas import (
    ConsoleOverviewResponse,
    ConsoleTimelineEntry,
    ConsoleTimelineResponse,
    EvalScenarioSummary,
    EvalSummaryResponse,
    EvalTotals,
    IncidentExpectation,
    IncidentLibraryResponse,
    IncidentProfileResponse,
    RagEvalSummary,
    WorkflowEvalSummary,
)
from app.services.console_service import ConsoleService
from app.settings import PROJECT_ROOT, Settings
from scripts.run_operations_report import build_report


class StubEvaluationSummaryService:
    def build_summary(self) -> EvalSummaryResponse:
        return EvalSummaryResponse(
            mode="deterministic_local",
            summary="Stub evaluation summary.",
            generated_at=datetime.now(UTC),
            totals=EvalTotals(total_cases=54, passed_cases=54, failed_cases=0, overall_pass_rate=1.0),
            analyze=EvalScenarioSummary(
                total_cases=20,
                passed_cases=20,
                failed_cases=0,
                pass_rate=1.0,
                average_confidence=0.9,
                retrieval_used_rate=1.0,
                average_confidence_by_incident_type={},
                common_failure_reasons={},
            ),
            investigate=EvalScenarioSummary(
                total_cases=12,
                passed_cases=12,
                failed_cases=0,
                pass_rate=1.0,
                average_confidence=0.9,
                retrieval_used_rate=1.0,
                average_confidence_by_incident_type={},
                common_failure_reasons={},
            ),
            rag=RagEvalSummary(
                total_cases=12,
                passed_cases=12,
                failed_cases=0,
                pass_rate=1.0,
                retrieval_hit_rate=1.0,
                average_hits_returned=4.0,
                corpus_document_count=20,
                corpus_chunk_count=40,
                common_failure_reasons={},
            ),
            workflow=WorkflowEvalSummary(
                total_cases=10,
                passed_cases=10,
                failed_cases=0,
                pass_rate=1.0,
                waiting_for_approval_rate=0.4,
                completed_rate=0.6,
                approval_required_rate=0.8,
                approved_completion_count=4,
                rejected_completion_count=2,
                average_confidence=0.88,
                average_confidence_by_incident_type={},
                common_failure_reasons={},
            ),
        )


class StubConsoleService:
    def overview(self) -> ConsoleOverviewResponse:
        return ConsoleOverviewResponse(
            generated_at=datetime.now(UTC),
            launch_command="sentinelops",
            console_url="http://127.0.0.1:8000/console",
            workspace_name="checkout-service",
            workspace_root="/workspace/checkout-service",
            incident_count=2,
            timeline_entry_count=2,
            library_categories=["workflow", "resilience"],
            eval_total_cases=54,
            overall_pass_rate=1.0,
            analyze_pass_rate=1.0,
            investigate_pass_rate=1.0,
            rag_pass_rate=1.0,
            workflow_pass_rate=1.0,
        )

    def list_incidents(self) -> IncidentLibraryResponse:
        return IncidentLibraryResponse(
            incident_count=1,
            incidents=[
                IncidentProfileResponse(
                    incident_id="database-workflow",
                    recommended_order=1,
                    title="Database Workflow",
                    headline="Exercises the workflow entrypoint.",
                    category="workflow",
                    endpoint="/workflow/investigate",
                    description="Stub incident profile for API coverage.",
                    estimated_run_seconds=60,
                    artifact_paths=["data/logs/database-current.log"],
                    request_body={"thread_id": "workflow-thread"},
                    expected_outcome=IncidentExpectation(
                        incident_type="database",
                        severity="high",
                        workflow_status="waiting_for_approval",
                        approval_status="pending",
                    ),
                    operator_steps=["Run workflow"],
                )
            ],
        )

    def get_incident(self, incident_id: str) -> IncidentProfileResponse:
        if incident_id != "database-workflow":
            raise KeyError(f"Incident profile '{incident_id}' was not found.")
        return self.list_incidents().incidents[0]

    def timeline(self) -> ConsoleTimelineResponse:
        return ConsoleTimelineResponse(
            total_entries=1,
            entries=[
                ConsoleTimelineEntry(
                    entry_id="runtime:database",
                    source="runtime",
                    created_at=datetime.now(UTC),
                    incident_type="database",
                    severity="high",
                    manager_summary="Database incident timeline entry.",
                    suspected_root_cause="Connection pool exhaustion.",
                    retrieval_status="used",
                    confidence=0.91,
                    source_citations=["runtime-citation"],
                    candidate_log_paths=["data/logs/database-current.log"],
                )
            ],
        )


def test_console_routes_and_api_contracts() -> None:
    app.dependency_overrides[get_console_service] = lambda: StubConsoleService()
    client = TestClient(app)

    try:
        root_response = client.get("/", follow_redirects=False)
        console_response = client.get("/console")
        overview_response = client.get("/console/overview")
        incidents_response = client.get("/console/incidents")
        incident_response = client.get("/console/incidents/database-workflow")
        missing_response = client.get("/console/incidents/missing-incident")
        timeline_response = client.get("/console/timeline")
        openapi_response = client.get("/openapi.json")
    finally:
        app.dependency_overrides.clear()

    assert root_response.status_code == 307
    assert root_response.headers["location"] == "/console"

    assert console_response.status_code == 200
    assert "SentinelOps Operations Console" in console_response.text

    assert overview_response.status_code == 200
    assert overview_response.json()["incident_count"] == 2

    assert incidents_response.status_code == 200
    payload = incidents_response.json()
    assert payload["incident_count"] == 1
    assert payload["incidents"][0]["incident_id"] == "database-workflow"

    assert incident_response.status_code == 200
    assert incident_response.json()["endpoint"] == "/workflow/investigate"

    assert missing_response.status_code == 404
    assert missing_response.headers["content-type"].startswith("application/problem+json")
    assert missing_response.json()["code"] == "incident_profile_not_found"

    assert timeline_response.status_code == 200
    assert timeline_response.json()["total_entries"] == 1

    assert openapi_response.status_code == 200
    openapi_payload = openapi_response.json()
    assert any(tag["name"] == "console" for tag in openapi_payload.get("tags", []))


def test_console_service_loads_repo_incidents_and_builds_timeline() -> None:
    settings = Settings()
    service = ConsoleService(settings=settings, evaluation_service=StubEvaluationSummaryService())

    incident_library = service.list_incidents()
    timeline = service.timeline()
    overview = service.overview()

    assert incident_library.incident_count >= 5
    assert incident_library.incidents[0].incident_id == "database-workflow"
    assert any(incident.category == "resilience" for incident in incident_library.incidents)

    assert timeline.total_entries >= 1
    assert all(entry.entry_id for entry in timeline.entries)
    assert all(entry.source in {"runtime", "reference"} for entry in timeline.entries)
    assert "reference" in {entry.source for entry in timeline.entries}

    assert overview.incident_count == incident_library.incident_count
    assert overview.eval_total_cases == 54
    assert "approval" in overview.library_categories
    assert overview.launch_command == "sentinelops"


def test_console_service_timeline_merges_runtime_and_reference_entries(tmp_path) -> None:
    runtime_dir = tmp_path / "recent_incidents"
    runtime_dir.mkdir(parents=True, exist_ok=True)

    reference_payload = json.loads(
        (PROJECT_ROOT / "data" / "reference_incidents" / "20260328T141500Z-database.json").read_text(
            encoding="utf-8"
        )
    )
    reference_payload["created_at"] = "2026-04-07T12:00:00Z"
    (runtime_dir / "20260407T120000Z-database.json").write_text(
        json.dumps(reference_payload),
        encoding="utf-8",
    )

    settings = Settings(incident_history_dir=runtime_dir)
    service = ConsoleService(settings=settings, evaluation_service=StubEvaluationSummaryService())

    timeline = service.timeline()

    assert timeline.total_entries >= 2
    assert {entry.source for entry in timeline.entries} >= {"runtime", "reference"}


def test_operations_report_can_render_json(tmp_path) -> None:
    report_path = tmp_path / "operations-report.json"
    report_path.write_text(json.dumps(build_report()), encoding="utf-8")
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    assert payload["overview"]["incident_count"] >= 5
    assert payload["artifacts"]["architecture_doc"] == "docs/architecture.md"
