from __future__ import annotations

import argparse
import os
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

import uvicorn

from app.agent_integrations import AgentInstallResult, SUPPORTED_AGENTS, install_agent_integrations
from app.bootstrap import apply_runtime_environment, attach_project, ensure_app_home, runtime_summary


def build_parser() -> argparse.ArgumentParser:
    agent_choices = ("all", *SUPPORTED_AGENTS)
    parser = argparse.ArgumentParser(
        prog="sentinelops",
        description="Plug-and-play launcher and utility CLI for SentinelOps.",
    )
    subparsers = parser.add_subparsers(dest="command")

    start_parser = subparsers.add_parser("start", help="Start SentinelOps and open the console.")
    start_parser.add_argument("--host", default="127.0.0.1")
    start_parser.add_argument("--port", type=int, default=8000)
    start_parser.add_argument("--profile", choices=("local", "production"), default="local")
    start_parser.add_argument("--home", type=Path, default=None)
    start_parser.add_argument("--project-root", type=Path, default=None)
    start_parser.add_argument("--reload", action="store_true")
    start_parser.add_argument("--no-browser", action="store_true")

    init_parser = subparsers.add_parser("init", help="Bootstrap SentinelOps home/config/data.")
    init_parser.add_argument("--home", type=Path, default=None)
    init_parser.add_argument("--overwrite", action="store_true")

    attach_parser = subparsers.add_parser(
        "attach",
        help="Attach SentinelOps to the current repo so it acts as a project copilot.",
    )
    attach_parser.add_argument("--project-root", type=Path, default=None)
    attach_parser.add_argument("--name", default=None)
    attach_parser.add_argument("--log-root", action="append", default=[])
    attach_parser.add_argument("--doc-root", action="append", default=[])
    attach_parser.add_argument("--agent", choices=agent_choices, default=None)
    attach_parser.add_argument("--overwrite", action="store_true")

    install_agent_parser = subparsers.add_parser(
        "install-agent",
        help="Generate repo-local agent and editor integration files for an attached project.",
    )
    install_agent_parser.add_argument("--project-root", type=Path, default=None)
    install_agent_parser.add_argument("--agent", choices=agent_choices, default="all")
    install_agent_parser.add_argument("--overwrite", action="store_true")

    doctor_parser = subparsers.add_parser("doctor", help="Validate config and print runtime readiness.")
    doctor_parser.add_argument("--profile", choices=("local", "production"), default="local")
    doctor_parser.add_argument("--home", type=Path, default=None)
    doctor_parser.add_argument("--project-root", type=Path, default=None)

    paths_parser = subparsers.add_parser("paths", help="Print important SentinelOps paths.")
    paths_parser.add_argument("--profile", choices=("local", "production"), default="local")
    paths_parser.add_argument("--home", type=Path, default=None)
    paths_parser.add_argument("--project-root", type=Path, default=None)

    subparsers.add_parser("version", help="Print SentinelOps version.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    command = args.command or "start"

    try:
        if command == "start":
            return _start_command(
                host=args.host,
                port=args.port,
                profile=args.profile,
                app_home=args.home,
                project_root=args.project_root,
                reload=args.reload,
                open_browser=not args.no_browser,
            )
        if command == "init":
            home = ensure_app_home(app_home=args.home, overwrite=args.overwrite)
            print(f"SentinelOps home ready at {home}")
            return 0
        if command == "attach":
            project_root, home = attach_project(
                project_root=args.project_root,
                workspace_name=args.name,
                log_roots=args.log_root,
                doc_roots=args.doc_root,
                overwrite=args.overwrite,
            )
            print(f"SentinelOps attached to {project_root}")
            print(f"Project home: {home}")
            print(f"Project config: {project_root / '.sentinelops' / 'project.toml'}")
            if args.agent:
                result = install_agent_integrations(
                    project_root=project_root,
                    agent=args.agent,
                    overwrite=args.overwrite,
                )
                _print_agent_install_result(result)
            print("Next: run `sentinelops` from this repo to start the project copilot.")
            return 0
        if command == "install-agent":
            result = install_agent_integrations(
                project_root=args.project_root,
                agent=args.agent,
                overwrite=args.overwrite,
            )
            _print_agent_install_result(result)
            return 0
        if command == "doctor":
            return _doctor_command(profile=args.profile, app_home=args.home, project_root=args.project_root)
        if command == "paths":
            for key, value in runtime_summary(
                app_home=args.home,
                profile=args.profile,
                project_root=args.project_root,
            ).items():
                print(f"{key}: {value}")
            return 0
        if command == "version":
            from app.settings import Settings

            print(Settings().app_version)
            return 0

        parser.print_help()
        return 1
    except Exception as exc:
        print(f"SentinelOps error: {exc}", file=sys.stderr)
        return 1


def _start_command(
    *,
    host: str,
    port: int,
    profile: str,
    app_home: Path | None,
    project_root: Path | None,
    reload: bool,
    open_browser: bool,
) -> int:
    home = apply_runtime_environment(app_home=app_home, profile=profile, project_root=project_root)
    console_host = "127.0.0.1" if host in {"0.0.0.0", "::"} else host
    console_url = f"http://{console_host}:{port}/console"

    print(f"SentinelOps home: {home}")
    workspace_root = os.environ.get("SENTINELOPS_WORKSPACE_ROOT")
    if workspace_root:
        print(f"Project workspace: {workspace_root}")
    _print_ollama_hint()
    if open_browser:
        browser_thread = threading.Thread(
            target=_open_when_ready,
            args=(console_url,),
            daemon=True,
        )
        browser_thread.start()

    uvicorn.run(
        "app.main:app",
        host=host,
        port=port,
        reload=reload,
        factory=False,
    )
    return 0


def _doctor_command(*, profile: str, app_home: Path | None, project_root: Path | None) -> int:
    apply_runtime_environment(app_home=app_home, profile=profile, project_root=project_root)

    from app.dependencies import (
        get_authentication_service,
        get_knowledge_base_service,
        get_ollama_gateway,
        get_runtime_metrics,
        get_settings,
        get_workflow_audit_trail,
        get_workflow_thread_store,
    )
    from app.services.runtime_health_service import RuntimeHealthService
    from app.startup import validate_settings

    get_settings.cache_clear()
    get_authentication_service.cache_clear()
    get_ollama_gateway.cache_clear()
    get_knowledge_base_service.cache_clear()
    get_runtime_metrics.cache_clear()
    get_workflow_audit_trail.cache_clear()
    get_workflow_thread_store.cache_clear()

    settings = get_settings()
    validate_settings(settings)
    report = RuntimeHealthService(settings).readiness_report(scope="strict" if profile == "production" else "traffic")

    print(f"deployment_mode: {settings.deployment_mode}")
    summary = runtime_summary(app_home=app_home, profile=profile, project_root=project_root)
    if "workspace_root" in summary:
        print(f"workspace_root: {summary['workspace_root']}")
        print(f"workspace_name: {summary['workspace_name']}")
        print(f"project_mode: {summary['project_mode']}")
        print(f"project_manifest: {summary['project_manifest']}")
    print(f"config_file: {summary['config_file']}")
    print(f"ready: {report.ready}")
    print(f"status: {report.status}")
    print(f"summary: {report.summary}")
    print("dependencies:")
    for name, dependency in report.dependencies.items():
        print(f"  - {name}: {dependency.status} :: {dependency.detail}")
    print("capabilities:")
    for name, capability in report.capabilities.items():
        print(f"  - {name}: {capability.status} :: {capability.detail}")
    return 0


def _print_ollama_hint() -> None:
    ollama_host = os.environ.get("SENTINELOPS_OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")
    try:
        urllib.request.urlopen(f"{ollama_host}/api/tags", timeout=2).read(1)
        print(f"Ollama reachable at {ollama_host}")
    except Exception:
        print(f"Ollama not reachable at {ollama_host}. Start `ollama serve` if model requests fail.")


def _print_agent_install_result(result: AgentInstallResult) -> None:
    print(f"Agent integrations ready for: {', '.join(result.installed_agents)}")
    print(f"Project root: {result.project_root}")
    if result.written_files:
        print("Written files:")
        for path in result.written_files:
            print(f"  - {path}")
    if result.skipped_files:
        print("Skipped existing files (re-run with --overwrite to replace):")
        for path in result.skipped_files:
            print(f"  - {path}")


def _open_when_ready(console_url: str) -> None:
    health_url = console_url.removesuffix("/console") + "/health"
    deadline = time.time() + 45
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(health_url, timeout=2):
                webbrowser.open(console_url)
                return
        except (urllib.error.URLError, TimeoutError):
            time.sleep(1)
    print(f"SentinelOps did not become ready at {health_url} within 45 seconds.", file=sys.stderr)
