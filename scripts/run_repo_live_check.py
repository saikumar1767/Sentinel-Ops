from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import requests

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_APP_PORT = 18000
DEFAULT_CHROMA_PORT = 8012
DEFAULT_CHAT_MODEL = "mistral"
DEFAULT_EMBED_MODEL = "nomic-embed-text"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create a dummy repo, attach SentinelOps, and run a strict live validation pass.",
    )
    parser.add_argument("--workspace-root", type=Path, default=None)
    parser.add_argument("--report-path", type=Path, default=None)
    parser.add_argument("--keep-workspace", action="store_true")
    parser.add_argument("--use-installed-cli", action="store_true")
    parser.add_argument("--app-port", type=int, default=DEFAULT_APP_PORT)
    parser.add_argument("--knowledge-backend", choices=("simple", "chroma"), default="chroma")
    parser.add_argument("--chroma-port", type=int, default=DEFAULT_CHROMA_PORT)
    parser.add_argument("--ollama-host", default="http://127.0.0.1:11434")
    parser.add_argument("--chat-model", default=DEFAULT_CHAT_MODEL)
    parser.add_argument("--embed-model", default=DEFAULT_EMBED_MODEL)
    parser.add_argument("--pull-models", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report: dict[str, object] = {"steps": [], "status": "failed"}
    temp_dir: tempfile.TemporaryDirectory[str] | None = None
    app_process: subprocess.Popen[str] | None = None
    chroma_process: subprocess.Popen[str] | None = None

    try:
        workspace_root = args.workspace_root
        if workspace_root is None:
            if args.keep_workspace:
                workspace_root = Path(tempfile.mkdtemp(prefix="sentinelops-live-check-"))
            else:
                temp_dir = tempfile.TemporaryDirectory(prefix="sentinelops-live-check-")
                workspace_root = Path(temp_dir.name)
        workspace_root = workspace_root.resolve()
        project_root = workspace_root / "checkout-service"
        create_dummy_repo(project_root)
        report["workspace_root"] = str(project_root)

        verify_ollama(args.ollama_host)
        report["steps"].append({"name": "ollama", "host": args.ollama_host, "status": "reachable"})

        if args.pull_models:
            run(
                sentinelops_cmd(
                    args.use_installed_cli,
                    "pull-models",
                    "--model",
                    args.chat_model,
                    "--model",
                    args.embed_model,
                    "--timeout",
                    "3600",
                ),
                cwd=REPO_ROOT,
            )
            report["steps"].append(
                {"name": "pull-models", "chat_model": args.chat_model, "embed_model": args.embed_model}
            )

        chroma_client_mode = "persistent" if args.knowledge_backend == "chroma" else "http"
        attach_cmd = sentinelops_cmd(
            args.use_installed_cli,
            "attach",
            "--project-root",
            str(project_root),
            "--agent",
            "all",
            "--knowledge-backend",
            args.knowledge_backend,
            "--ollama-host",
            args.ollama_host,
            "--chroma-client-mode",
            chroma_client_mode,
            "--chroma-host",
            "127.0.0.1",
            "--chroma-port",
            str(args.chroma_port),
        )
        if args.knowledge_backend == "chroma" and chroma_client_mode == "http":
            attach_cmd.append("--chroma-auto-start")
        run(attach_cmd, cwd=REPO_ROOT)
        assert_true((project_root / ".sentinelops" / "project.toml").exists(), "project manifest missing")
        assert_true((project_root / ".claude" / "skills" / "sentinelops-check" / "SKILL.md").exists(), "Claude skill missing")
        assert_true((project_root / "CLAUDE.md").exists(), "CLAUDE.md missing")
        report["steps"].append({"name": "attach", "agent_set": "all", "knowledge_backend": args.knowledge_backend})

        paths = run(
            sentinelops_cmd(args.use_installed_cli, "paths", "--project-root", str(project_root)),
            cwd=REPO_ROOT,
        ).stdout
        doctor_before = run(
            sentinelops_cmd(args.use_installed_cli, "doctor", "--project-root", str(project_root)),
            cwd=REPO_ROOT,
        ).stdout
        assert_true("workspace_name: checkout-service" in paths, "paths did not report the dummy workspace")
        report["steps"].append({"name": "paths", "stdout": paths.strip()})
        report["steps"].append({"name": "doctor-before", "stdout": doctor_before.strip()})

        app_log_path = workspace_root / "sentinelops-live.log"
        with app_log_path.open("w", encoding="utf-8") as log_handle:
            app_process = subprocess.Popen(
                sentinelops_start_cmd(
                    args.use_installed_cli,
                    "start",
                    "--project-root",
                    str(project_root),
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(args.app_port),
                    "--no-browser",
                ),
                cwd=str(REPO_ROOT),
                stdout=log_handle,
                stderr=subprocess.STDOUT,
                text=True,
            )

        api_base = f"http://127.0.0.1:{args.app_port}"
        wait_for(f"{api_base}/health", timeout=90)

        api_result = run_api_checks(
            api_base=api_base,
            project_root=project_root,
            knowledge_backend=args.knowledge_backend,
        )
        report["api_checks"] = api_result
        report["app_log_path"] = str(app_log_path)
        report["status"] = "passed"
    except Exception as exc:
        report["status"] = "failed"
        report["error"] = f"{exc.__class__.__name__}: {exc}"
    finally:
        if app_process is not None:
            stop_process(app_process)
        if chroma_process is not None:
            stop_process(chroma_process)
        if temp_dir is not None and not args.keep_workspace:
            temp_dir.cleanup()

    serialized = json.dumps(report, indent=2)
    if args.report_path is not None:
        args.report_path.parent.mkdir(parents=True, exist_ok=True)
        args.report_path.write_text(serialized, encoding="utf-8")
    print(serialized)
    return 0 if report["status"] == "passed" else 1


def sentinelops_cmd(use_installed_cli: bool, *args: str) -> list[str]:
    if use_installed_cli:
        return ["sentinelops", *args]
    return ["uv", "run", "sentinelops", *args]


def sentinelops_start_cmd(use_installed_cli: bool, *args: str) -> list[str]:
    if use_installed_cli:
        return ["sentinelops", *args]
    return [sys.executable, "-c", "from app.cli import main; raise SystemExit(main())", *args]


def run(cmd: list[str], *, cwd: Path, timeout: int = 900) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        cmd,
        cwd=str(cwd),
        text=True,
        capture_output=True,
        timeout=timeout,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"Command failed: {' '.join(cmd)}\nexit={completed.returncode}\nstdout=\n{completed.stdout}\nstderr=\n{completed.stderr}"
        )
    return completed


def verify_ollama(ollama_host: str) -> None:
    response = requests.get(f"{ollama_host.rstrip('/')}/api/tags", timeout=10)
    response.raise_for_status()


def wait_for(url: str, *, timeout: float) -> None:
    deadline = time.time() + timeout
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            response = requests.get(url, timeout=3)
            response.raise_for_status()
            return
        except Exception as exc:  # pragma: no cover - best effort polling
            last_error = exc
            time.sleep(1)
    raise RuntimeError(f"Timed out waiting for {url}: {last_error}")


def api_json(method: str, url: str, payload: dict[str, object] | None = None) -> tuple[int, dict[str, object]]:
    response = requests.request(method, url, json=payload, timeout=120)
    response.raise_for_status()
    return response.status_code, response.json()


def run_api_checks(*, api_base: str, project_root: Path, knowledge_backend: str) -> dict[str, object]:
    health = requests.get(f"{api_base}/health", timeout=20)
    ready_before = requests.get(f"{api_base}/ready", timeout=20)
    ready_strict_before = requests.get(f"{api_base}/ready/strict", timeout=20)
    docs_html = requests.get(f"{api_base}/docs", timeout=20).text

    assert_true(health.ok, "/health failed")
    assert_true(ready_before.ok, "/ready failed")
    assert_true(ready_strict_before.ok or ready_strict_before.status_code == 503, "/ready/strict failed")
    assert_true("Swagger UI" in docs_html, "/docs did not render")

    _, me = api_json("GET", f"{api_base}/me")
    _, overview = api_json("GET", f"{api_base}/console/overview")
    _, incidents = api_json("GET", f"{api_base}/console/incidents")
    _, timeline = api_json("GET", f"{api_base}/console/timeline")
    _, metrics = api_json("GET", f"{api_base}/metrics")

    assert_true(me["subject"] == "local-operator", "unexpected /me subject")
    assert_true(overview["workspace_name"] == "checkout-service", "console overview workspace mismatch")
    assert_true(incidents["incident_count"] >= 1, "incident library did not load")
    assert_true(timeline["total_entries"] >= 1, "timeline did not load")
    assert_true(metrics["requests"]["total_requests"] >= 1, "metrics totals missing")

    _, ingest = api_json(
        "POST",
        f"{api_base}/knowledge/ingest",
        {"reset": True, "confirm_reset": True},
    )
    assert_true(ingest["chunk_count"] >= 1, "knowledge ingest did not index chunks")

    _, ready_after = api_json("GET", f"{api_base}/ready")
    ready_strict_after_response = requests.get(f"{api_base}/ready/strict", timeout=20)
    ready_strict_after_payload = ready_strict_after_response.json()
    if knowledge_backend == "chroma":
        assert_true(ready_after["ready"] is True, "ready should be true after ingest")
        assert_true(ready_strict_after_response.status_code == 200, "strict readiness should be healthy after ingest")
        assert_true(ready_strict_after_payload["ready"] is True, "strict readiness payload should be true after ingest")

    _, analyze_database = api_json(
        "POST",
        f"{api_base}/analyze",
        {"log_text": (project_root / "logs" / "checkout-current.log").read_text(encoding="utf-8")},
    )
    _, analyze_authentication = api_json(
        "POST",
        f"{api_base}/analyze",
        {"log_text": (project_root / "logs" / "auth-current.log").read_text(encoding="utf-8")},
    )

    assert_incident(analyze_database, expected="database", citation_hint="runbooks/database.md")
    assert_incident(analyze_authentication, expected="authentication", citation_hint="runbooks/authentication.md")

    _, investigate_database = api_json(
        "POST",
        f"{api_base}/investigate",
        {
            "prompt": "Investigate checkout timeout symptoms using the failing run and the previous healthy run.",
            "candidate_log_paths": ["logs/checkout-current.log", "logs/checkout-previous.log"],
            "incident_type_hint": "database",
        },
    )
    _, investigate_authentication = api_json(
        "POST",
        f"{api_base}/investigate",
        {
            "prompt": "Investigate repeated login failures and token verification errors.",
            "candidate_log_paths": ["logs/auth-current.log"],
            "incident_type_hint": "authentication",
        },
    )
    _, investigate_deployment = api_json(
        "POST",
        f"{api_base}/investigate",
        {
            "prompt": "Investigate the rollout failure for checkout.",
            "candidate_log_paths": ["logs/deploy-current.log"],
            "incident_type_hint": "deployment",
        },
    )

    assert_incident(investigate_database, expected="database", citation_hint="runbooks/database.md")
    assert_incident(investigate_authentication, expected="authentication", citation_hint="runbooks/authentication.md")
    assert_incident(investigate_deployment, expected="deployment", citation_hint="ops/deployment.md")

    _, workflow_start = api_json(
        "POST",
        f"{api_base}/workflow/investigate",
        {
            "prompt": "Investigate this checkout incident using the failing run and previous healthy run.",
            "candidate_log_paths": ["logs/checkout-current.log", "logs/checkout-previous.log"],
            "incident_type_hint": "database",
        },
    )
    thread_id = str(workflow_start["thread_id"])
    assert_true(workflow_start["status"] == "waiting_for_approval", "workflow did not wait for approval")

    _, workflow_approve = api_json(
        "POST",
        f"{api_base}/workflow/{thread_id}/approve",
        {"review_notes": "Approved during live validation."},
    )
    _, workflow_audit = api_json("GET", f"{api_base}/workflow/{thread_id}/audit")
    _, workflow_threads = api_json("GET", f"{api_base}/workflow/threads?limit=10")

    assert_true(workflow_approve["status"] == "completed", "workflow did not complete after approval")
    assert_true(workflow_approve["approval_status"] == "approved", "workflow approval status mismatch")
    assert_true(workflow_audit["total_events"] >= 1, "workflow audit trail missing")
    assert_true(any(item["thread_id"] == thread_id for item in workflow_threads["threads"]), "workflow thread list missing new thread")

    return {
        "me": me,
        "overview": overview,
        "incident_count": incidents["incident_count"],
        "timeline_entries": timeline["total_entries"],
        "ready_before": ready_before.json(),
        "ready_strict_before": ready_strict_before.json(),
        "knowledge_ingest": ingest,
        "ready_after": ready_after,
        "ready_strict_after": ready_strict_after_payload,
        "analyze_database": analyze_database,
        "analyze_authentication": analyze_authentication,
        "investigate_database": investigate_database,
        "investigate_authentication": investigate_authentication,
        "investigate_deployment": investigate_deployment,
        "workflow_start": workflow_start,
        "workflow_approve": workflow_approve,
        "workflow_audit": workflow_audit,
        "workflow_threads": workflow_threads,
    }


def assert_incident(payload: dict[str, object], *, expected: str, citation_hint: str) -> None:
    incident_type = str(payload.get("incident_type", "")).strip()
    assert_true(incident_type == expected, f"expected incident_type={expected}, got {incident_type}")
    citations = [str(item) for item in payload.get("source_citations", [])]
    evidence = " ".join(str(item) for item in payload.get("retrieved_evidence", []))
    assert_true(
        any(citation_hint in citation for citation in citations) or citation_hint.replace(".md", "").split("/")[-1] in evidence.lower(),
        f"expected repo-local evidence for {expected}, got citations={citations} evidence={evidence}",
    )


def create_dummy_repo(project_root: Path) -> None:
    if project_root.exists():
        shutil.rmtree(project_root)
    project_root.mkdir(parents=True, exist_ok=True)
    (project_root / ".git").mkdir()
    write_file(
        project_root / "README.md",
        "# Checkout Service\n\nSentinelOps should treat this repository as the source of truth for checkout incidents.\n",
    )
    write_file(
        project_root / "docs" / "overview.md",
        "# Checkout Overview\n\nThe checkout service talks to primary-postgres and internal-sso.\n",
    )
    write_file(
        project_root / "runbooks" / "database.md",
        "---\n"
        "title: Checkout Database Recovery\n"
        "incident_type: database\n"
        "tags: checkout, database\n"
        "---\n"
        "# Recovery\n\n"
        "Drain checkout workers before recycling database connections. Compare the failing run against the previous healthy run before restarting anything.\n",
    )
    write_file(
        project_root / "runbooks" / "authentication.md",
        "---\n"
        "title: Checkout Authentication Recovery\n"
        "incident_type: authentication\n"
        "tags: auth, token\n"
        "---\n"
        "# Recovery\n\n"
        "Reset lockouts only after confirming the token issuer and signature settings are correct.\n",
    )
    write_file(
        project_root / "ops" / "deployment.md",
        "---\n"
        "title: Checkout Deployment Guardrails\n"
        "incident_type: deployment\n"
        "tags: deploy, rollout\n"
        "---\n"
        "# Rollout Guardrails\n\n"
        "Do not continue the rollout until config validation and migration compatibility both pass.\n",
    )
    write_file(project_root / "compose.yaml", "services:\n  checkout:\n    image: checkout:latest\n")
    write_file(project_root / ".github" / "workflows" / "deploy.yml", "name: deploy\non: [push]\n")
    write_file(
        project_root / "logs" / "checkout-current.log",
        "2026-04-20T10:00:00Z INFO starting checkout service\n"
        "2026-04-20T10:00:03Z WARN retrying database connection attempt 1/3\n"
        "2026-04-20T10:00:05Z ERROR database connection timeout after 30 seconds\n"
        "2026-04-20T10:00:07Z ERROR connection pool exhausted on primary-postgres\n"
        "2026-04-20T10:00:10Z ERROR checkout requests stalled waiting for a free database connection\n",
    )
    write_file(
        project_root / "logs" / "checkout-previous.log",
        "2026-04-20T09:40:00Z INFO starting checkout service\n"
        "2026-04-20T09:40:04Z INFO checkout service ready\n"
        "2026-04-20T09:40:05Z INFO processed order 1001 successfully\n",
    )
    write_file(
        project_root / "logs" / "auth-current.log",
        "2026-04-20T09:15:00Z WARN token verification retry for issuer internal-sso\n"
        "2026-04-20T09:15:04Z ERROR Invalid JWT signature for issuer internal-sso\n"
        "2026-04-20T09:15:07Z ERROR account locked after repeated failed login attempts\n",
    )
    write_file(
        project_root / "logs" / "deploy-current.log",
        "2026-04-20T11:00:00Z INFO starting rollout for checkout\n"
        "2026-04-20T11:00:02Z ERROR missing required environment variable CHECKOUT_DB_URL\n"
        "2026-04-20T11:00:04Z ERROR rollout halted because schema version mismatch was detected\n",
    )


def write_file(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def stop_process(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    if os.name == "nt":
        process.terminate()
    else:
        process.send_signal(signal.SIGTERM)
    try:
        process.wait(timeout=20)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=10)


if __name__ == "__main__":
    raise SystemExit(main())
