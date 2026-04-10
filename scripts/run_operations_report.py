from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.services.console_service import ConsoleService
from app.services.evaluation_service import EvaluationSummaryService
from app.settings import Settings


def build_report() -> dict[str, object]:
    settings = Settings()
    evaluation_service = EvaluationSummaryService(settings)
    console_service = ConsoleService(settings=settings, evaluation_service=evaluation_service)

    overview = console_service.overview()
    incidents = console_service.list_incidents()
    timeline = console_service.timeline()

    return {
        "overview": overview.model_dump(mode="json"),
        "incidents": incidents.model_dump(mode="json"),
        "timeline": timeline.model_dump(mode="json"),
        "artifacts": {
            "console": "http://127.0.0.1:8000/console",
            "launch_command": overview.launch_command,
            "architecture_doc": "docs/architecture.md",
            "operator_walkthrough": "docs/operator-walkthrough.md",
            "video_walkthrough": "docs/video-walkthrough.md",
            "resume_bullets": "docs/resume-bullets.md",
            "interview_story": "docs/interview-story.md",
        },
    }


def render_markdown(report: dict[str, object]) -> str:
    overview = report["overview"]
    incidents = report["incidents"]["incidents"]
    timeline = report["timeline"]["entries"]

    lines = [
        "# SentinelOps Operations Report",
        "",
        f"- Launch command: `{overview['launch_command']}`",
        f"- Console URL: `{overview['console_url']}`",
        f"- Incident library size: `{overview['incident_count']}`",
        f"- Eval total cases: `{overview['eval_total_cases']}`",
        f"- Overall pass rate: `{overview['overall_pass_rate']}`",
        f"- Timeline entries surfaced: `{overview['timeline_entry_count']}`",
        "",
        "## Incident library",
    ]

    for incident in incidents:
        lines.extend(
            [
                f"- `{incident['recommended_order']}. {incident['title']}`",
                f"  Endpoint: `{incident['endpoint']}`",
                f"  Category: `{incident['category']}`",
                f"  Expected: `{incident['expected_outcome'].get('incident_type')}` / `{incident['expected_outcome'].get('severity')}`",
            ]
        )

    lines.extend(["", "## Timeline preview"])
    for entry in timeline[:5]:
        lines.append(
            f"- `{entry['created_at']}` · `{entry['incident_type']}` · `{entry['severity']}` · {entry['manager_summary']}"
        )

    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Render the SentinelOps operations report.")
    parser.add_argument("--json", action="store_true", help="Print the operations report as JSON instead of Markdown.")
    args = parser.parse_args()

    report = build_report()
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(render_markdown(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
