from __future__ import annotations

import json
import os
import shutil
import tomllib
from pathlib import Path

from app.settings import PROJECT_ROOT

SENTINELOPS_HOME_ENV = "SENTINELOPS_HOME"
SENTINELOPS_WORKSPACE_ROOT_ENV = "SENTINELOPS_WORKSPACE_ROOT"
SENTINELOPS_WORKSPACE_NAME_ENV = "SENTINELOPS_WORKSPACE_NAME"

_BUNDLED_RELATIVE_PATHS = (
    Path("config"),
    Path("data") / "incident_library",
    Path("data") / "incident_templates",
    Path("data") / "knowledge",
    Path("data") / "logs",
    Path("data") / "reference_incidents",
    Path("samples"),
)
_PROJECT_HOME_DIRNAME = ".sentinelops"
_PROJECT_MANIFEST_FILENAME = "project.toml"
_AGENT_CONTEXT_FILENAME = "agent-context.md"
_PROJECT_MODE_PERSONAL = "personal"
_REPOSITORY_MARKERS = (
    ".git",
    "pyproject.toml",
    "package.json",
    "go.mod",
    "Cargo.toml",
    "pom.xml",
    "build.gradle",
    "docker-compose.yml",
    "docker-compose.yaml",
    "compose.yaml",
    "compose.yml",
)
_DEFAULT_PROJECT_LOG_ROOTS = (
    Path("logs"),
    Path("log"),
    Path("data") / "logs",
    Path("var") / "log",
)
_DEFAULT_PROJECT_DOC_ROOTS = (
    Path("README.md"),
    Path("docs"),
    Path("runbooks"),
    Path("ops"),
    Path("deploy"),
    Path("k8s"),
    Path("helm"),
    Path(".github") / "workflows",
)
_DEFAULT_PROJECT_MODELS = {
    "analyze": "mistral",
    "investigate": "mistral",
    "embedding": "nomic-embed-text",
}
_DEFAULT_PROJECT_STORAGE = {
    "incident_history_dir": "data/runtime/recent_incidents",
    "workflow_checkpoint_path": "data/runtime/workflow/checkpoints.sqlite",
    "audit_db_path": "data/runtime/audit/audit.sqlite",
    "knowledge_index_path": "data/runtime/knowledge/knowledge_index.json",
    "chroma_path": "data/runtime/chroma",
}
_DEFAULT_PROJECT_KNOWLEDGE = {
    "backend": "simple",
    "chroma_client_mode": "persistent",
    "chroma_host": "127.0.0.1",
    "chroma_port": 8012,
    "chroma_ssl": False,
    "chroma_auto_start": False,
}
_PROJECT_GITIGNORE = """data/runtime/
data/chroma/
data/logs/
"""
_REPO_GITIGNORE_ENTRY = ".sentinelops/"


def default_app_home() -> Path:
    configured_home = os.environ.get(SENTINELOPS_HOME_ENV)
    if configured_home:
        return Path(configured_home).expanduser().resolve()
    return (Path.home() / ".sentinelops").resolve()


def packaged_resource_root() -> Path | None:
    bundled_root = Path(__file__).resolve().parent / "_bundled"
    if bundled_root.exists():
        return bundled_root
    return None


def resource_root() -> Path:
    return packaged_resource_root() or PROJECT_ROOT


def project_home(project_root: Path) -> Path:
    return project_root.resolve() / _PROJECT_HOME_DIRNAME


def project_manifest_path(project_root: Path) -> Path:
    return project_home(project_root) / _PROJECT_MANIFEST_FILENAME


def agent_context_path(project_root: Path) -> Path:
    return project_home(project_root) / _AGENT_CONTEXT_FILENAME


def find_attached_project_root(start_path: Path | None = None) -> Path | None:
    for candidate in _search_roots(start_path):
        if project_manifest_path(candidate).is_file():
            return candidate.resolve()
    return None


def detect_repository_root(start_path: Path | None = None) -> Path:
    for candidate in _search_roots(start_path):
        if any((candidate / marker).exists() for marker in _REPOSITORY_MARKERS):
            return candidate.resolve()
    return (start_path or Path.cwd()).expanduser().resolve()


def ensure_app_home(*, app_home: Path | None = None, overwrite: bool = False) -> Path:
    home = (app_home or default_app_home()).expanduser().resolve()
    home.mkdir(parents=True, exist_ok=True)

    source_root = resource_root()
    for relative_path in _BUNDLED_RELATIVE_PATHS:
        source_path = source_root / relative_path
        destination_path = home / relative_path
        if not source_path.exists():
            continue
        _copy_path(source_path, destination_path, overwrite=overwrite)

    _runtime_dir(home).mkdir(parents=True, exist_ok=True)
    return home


def attach_project(
    *,
    project_root: Path | None = None,
    workspace_name: str | None = None,
    log_roots: list[str] | None = None,
    doc_roots: list[str] | None = None,
    ollama_host: str | None = None,
    knowledge_backend: str | None = None,
    chroma_client_mode: str | None = None,
    chroma_host: str | None = None,
    chroma_port: int | None = None,
    chroma_ssl: bool | None = None,
    chroma_auto_start: bool | None = None,
    overwrite: bool = False,
) -> tuple[Path, Path]:
    resolved_project_root = (project_root or detect_repository_root()).expanduser().resolve()
    home = ensure_app_home(app_home=project_home(resolved_project_root), overwrite=overwrite)
    _write_project_manifest(
        resolved_project_root,
        workspace_name=workspace_name,
        log_roots=log_roots,
        doc_roots=doc_roots,
        ollama_host=ollama_host,
        knowledge_backend=knowledge_backend,
        chroma_client_mode=chroma_client_mode,
        chroma_host=chroma_host,
        chroma_port=chroma_port,
        chroma_ssl=chroma_ssl,
        chroma_auto_start=chroma_auto_start,
        overwrite=overwrite,
    )
    _write_project_gitignore(home)
    _ensure_repo_gitignore(resolved_project_root)
    _write_agent_context(resolved_project_root)
    return resolved_project_root, home


def apply_runtime_environment(
    *,
    app_home: Path | None = None,
    profile: str = "local",
    project_root: Path | None = None,
) -> Path:
    resolved_project_root = None
    if project_root is not None:
        resolved_project_root = project_root.expanduser().resolve()
    elif app_home is None:
        resolved_project_root = find_attached_project_root()

    if resolved_project_root is not None:
        resolved_project_root, home = attach_project(project_root=resolved_project_root)
        manifest = read_project_manifest(resolved_project_root)
        workspace_name = project_manifest_workspace_name(manifest, fallback=resolved_project_root.name)
        doc_roots = project_manifest_doc_roots(manifest)
        model_names = project_manifest_models(manifest)
        ollama_host = project_manifest_ollama_host(manifest)
        knowledge_backend = project_manifest_knowledge_backend(manifest)
        chroma_client_mode = project_manifest_chroma_client_mode(manifest)
        chroma_host = project_manifest_chroma_host(manifest)
        chroma_port = project_manifest_chroma_port(manifest)
        chroma_ssl = project_manifest_chroma_ssl(manifest)
        chroma_auto_start = project_manifest_chroma_auto_start(manifest)
        allowed_log_roots = _resolve_project_log_roots(resolved_project_root, home, manifest)
        os.environ[SENTINELOPS_WORKSPACE_ROOT_ENV] = str(resolved_project_root)
        os.environ[SENTINELOPS_WORKSPACE_NAME_ENV] = workspace_name
        os.environ["SENTINELOPS_WORKSPACE_DOC_ROOTS"] = json.dumps(doc_roots)
        os.environ["SENTINELOPS_ANALYZE_MODEL"] = model_names["analyze"]
        os.environ["SENTINELOPS_INVESTIGATE_MODEL"] = model_names["investigate"]
        os.environ["SENTINELOPS_EMBEDDING_MODEL"] = model_names["embedding"]
        if ollama_host:
            os.environ["SENTINELOPS_OLLAMA_HOST"] = ollama_host
        os.environ["SENTINELOPS_KNOWLEDGE_STORE_BACKEND"] = knowledge_backend
        os.environ["SENTINELOPS_CHROMA_CLIENT_MODE"] = chroma_client_mode
        os.environ["SENTINELOPS_CHROMA_HOST"] = chroma_host
        os.environ["SENTINELOPS_CHROMA_PORT"] = str(chroma_port)
        os.environ["SENTINELOPS_CHROMA_SSL"] = "true" if chroma_ssl else "false"
        os.environ["SENTINELOPS_CHROMA_AUTO_START"] = "true" if chroma_auto_start else "false"
    else:
        home = ensure_app_home(app_home=app_home)
        allowed_log_roots = [home / "samples", home / "data" / "logs"]
        os.environ.pop(SENTINELOPS_WORKSPACE_ROOT_ENV, None)
        os.environ.pop(SENTINELOPS_WORKSPACE_NAME_ENV, None)
        os.environ.pop("SENTINELOPS_WORKSPACE_DOC_ROOTS", None)
        os.environ.pop("SENTINELOPS_ANALYZE_MODEL", None)
        os.environ.pop("SENTINELOPS_INVESTIGATE_MODEL", None)
        os.environ.pop("SENTINELOPS_EMBEDDING_MODEL", None)
        os.environ.pop("SENTINELOPS_OLLAMA_HOST", None)
        os.environ.pop("SENTINELOPS_KNOWLEDGE_STORE_BACKEND", None)
        os.environ.pop("SENTINELOPS_CHROMA_CLIENT_MODE", None)
        os.environ.pop("SENTINELOPS_CHROMA_HOST", None)
        os.environ.pop("SENTINELOPS_CHROMA_PORT", None)
        os.environ.pop("SENTINELOPS_CHROMA_SSL", None)
        os.environ.pop("SENTINELOPS_CHROMA_AUTO_START", None)

    runtime = _runtime_dir(home)
    runtime.mkdir(parents=True, exist_ok=True)
    storage_paths = _resolve_project_storage_paths(home, manifest if resolved_project_root is not None else {})

    config_name = "sentinelops.production.toml" if profile == "production" else "sentinelops.toml"
    os.environ[SENTINELOPS_HOME_ENV] = str(home)
    os.environ["SENTINELOPS_CONFIG_FILE"] = str(home / "config" / config_name)
    os.environ["SENTINELOPS_ALLOWED_LOG_ROOTS"] = json.dumps([str(path) for path in allowed_log_roots])
    os.environ["SENTINELOPS_INCIDENT_TEMPLATES_DIR"] = str(home / "data" / "incident_templates")
    os.environ["SENTINELOPS_INCIDENT_HISTORY_DIR"] = str(storage_paths["incident_history_dir"])
    os.environ["SENTINELOPS_WORKFLOW_CHECKPOINT_PATH"] = str(storage_paths["workflow_checkpoint_path"])
    os.environ["SENTINELOPS_AUDIT_DB_PATH"] = str(storage_paths["audit_db_path"])
    os.environ["SENTINELOPS_KNOWLEDGE_BASE_DIR"] = str(home / "data" / "knowledge")
    os.environ["SENTINELOPS_KNOWLEDGE_INDEX_PATH"] = str(storage_paths["knowledge_index_path"])
    os.environ["SENTINELOPS_CHROMA_PATH"] = str(storage_paths["chroma_path"])
    os.environ["SENTINELOPS_INCIDENT_LIBRARY_DIR"] = str(home / "data" / "incident_library")
    os.environ["SENTINELOPS_REFERENCE_INCIDENTS_DIR"] = str(home / "data" / "reference_incidents")
    return home


def runtime_summary(
    *,
    app_home: Path | None = None,
    profile: str = "local",
    project_root: Path | None = None,
) -> dict[str, str]:
    resolved_project_root = None
    if project_root is not None:
        resolved_project_root = project_root.expanduser().resolve()
    elif app_home is None:
        resolved_project_root = find_attached_project_root()

    if resolved_project_root is not None:
        home = project_home(resolved_project_root)
        manifest = read_project_manifest(resolved_project_root)
        workspace_name = project_manifest_workspace_name(manifest, fallback=resolved_project_root.name)
    else:
        home = (app_home or default_app_home()).expanduser().resolve()
        workspace_name = ""
        manifest = {}

    runtime = _runtime_dir(home)
    config_name = "sentinelops.production.toml" if profile == "production" else "sentinelops.toml"
    summary = {
        "app_home": str(home),
        "resource_root": str(resource_root()),
        "config_file": str(home / "config" / config_name),
        "runtime_dir": str(runtime),
        "samples_dir": str(home / "samples"),
        "logs_dir": str(home / "data" / "logs"),
    }
    if resolved_project_root is not None:
        summary["workspace_root"] = str(resolved_project_root)
        summary["workspace_name"] = workspace_name
        summary["project_manifest"] = str(project_manifest_path(resolved_project_root))
        summary["project_mode"] = project_manifest_mode(manifest)
        summary["project_doc_roots"] = json.dumps(project_manifest_doc_roots(manifest))
        summary["project_log_roots"] = json.dumps(project_manifest_log_roots(manifest))
        project_models = project_manifest_models(manifest)
        summary["project_analyze_model"] = project_models["analyze"]
        summary["project_investigate_model"] = project_models["investigate"]
        summary["project_embedding_model"] = project_models["embedding"]
        summary["project_knowledge_backend"] = project_manifest_knowledge_backend(manifest)
        summary["project_chroma_client_mode"] = project_manifest_chroma_client_mode(manifest)
        summary["project_chroma_host"] = project_manifest_chroma_host(manifest)
        summary["project_chroma_port"] = str(project_manifest_chroma_port(manifest))
        summary["project_chroma_auto_start"] = str(project_manifest_chroma_auto_start(manifest)).lower()
        ollama_host = project_manifest_ollama_host(manifest)
        if ollama_host:
            summary["project_ollama_host"] = ollama_host
    return summary


def read_project_manifest(project_root: Path) -> dict[str, object]:
    manifest_path = project_manifest_path(project_root)
    if not manifest_path.is_file():
        return {}

    with manifest_path.open("rb") as handle:
        payload = tomllib.load(handle)
    if isinstance(payload, dict):
        return payload
    return {}


def project_manifest_mode(manifest: dict[str, object]) -> str:
    return _manifest_string(manifest, "mode", default=_PROJECT_MODE_PERSONAL)


def project_manifest_workspace_name(manifest: dict[str, object], *, fallback: str) -> str:
    return _manifest_string(manifest, "workspace", "name", legacy_key="workspace_name", default=fallback)


def project_manifest_log_roots(manifest: dict[str, object]) -> list[str]:
    return _manifest_string_list(
        manifest,
        "logs",
        "roots",
        legacy_key="log_roots",
        default=[path.as_posix() for path in _DEFAULT_PROJECT_LOG_ROOTS],
    )


def project_manifest_doc_roots(manifest: dict[str, object]) -> list[str]:
    return _manifest_string_list(
        manifest,
        "workspace",
        "doc_roots",
        legacy_key="doc_roots",
        default=[path.as_posix() for path in _DEFAULT_PROJECT_DOC_ROOTS],
    )


def project_manifest_models(manifest: dict[str, object]) -> dict[str, str]:
    return {
        name: _manifest_string(
            manifest,
            "models",
            name,
            default=default_value,
        )
        for name, default_value in _DEFAULT_PROJECT_MODELS.items()
    }


def project_manifest_ollama_host(manifest: dict[str, object]) -> str | None:
    return _manifest_string(manifest, "runtime", "ollama_host", default=None)


def project_manifest_knowledge_backend(manifest: dict[str, object]) -> str:
    return _manifest_string(
        manifest,
        "knowledge",
        "backend",
        default=str(_DEFAULT_PROJECT_KNOWLEDGE["backend"]),
    ) or str(_DEFAULT_PROJECT_KNOWLEDGE["backend"])


def project_manifest_chroma_client_mode(manifest: dict[str, object]) -> str:
    return _manifest_string(
        manifest,
        "knowledge",
        "chroma_client_mode",
        default=str(_DEFAULT_PROJECT_KNOWLEDGE["chroma_client_mode"]),
    ) or str(_DEFAULT_PROJECT_KNOWLEDGE["chroma_client_mode"])


def project_manifest_chroma_host(manifest: dict[str, object]) -> str:
    return _manifest_string(
        manifest,
        "knowledge",
        "chroma_host",
        default=str(_DEFAULT_PROJECT_KNOWLEDGE["chroma_host"]),
    ) or str(_DEFAULT_PROJECT_KNOWLEDGE["chroma_host"])


def project_manifest_chroma_port(manifest: dict[str, object]) -> int:
    value = _manifest_int(
        manifest,
        "knowledge",
        "chroma_port",
        default=int(_DEFAULT_PROJECT_KNOWLEDGE["chroma_port"]),
    )
    return value if value is not None else int(_DEFAULT_PROJECT_KNOWLEDGE["chroma_port"])


def project_manifest_chroma_ssl(manifest: dict[str, object]) -> bool:
    return _manifest_bool(
        manifest,
        "knowledge",
        "chroma_ssl",
        default=bool(_DEFAULT_PROJECT_KNOWLEDGE["chroma_ssl"]),
    )


def project_manifest_chroma_auto_start(manifest: dict[str, object]) -> bool:
    return _manifest_bool(
        manifest,
        "knowledge",
        "chroma_auto_start",
        default=bool(_DEFAULT_PROJECT_KNOWLEDGE["chroma_auto_start"]),
    )


def _runtime_dir(home: Path) -> Path:
    return home / "data" / "runtime"


def _search_roots(start_path: Path | None) -> list[Path]:
    current = (start_path or Path.cwd()).expanduser().resolve()
    return [current, *current.parents]


def _resolve_project_log_roots(project_root: Path, home: Path, manifest: dict[str, object]) -> list[Path]:
    configured_roots = _coerce_manifest_paths(project_root, project_manifest_log_roots(manifest))
    defaults = [project_root / relative_path for relative_path in _DEFAULT_PROJECT_LOG_ROOTS]
    fallbacks = [
        home / "samples",
        home / "data" / "logs",
    ]

    ordered_roots: list[Path] = []
    seen: set[Path] = set()
    for path in [*configured_roots, *defaults, *fallbacks]:
        resolved = path.expanduser().resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        ordered_roots.append(resolved)
    return ordered_roots


def _coerce_manifest_paths(project_root: Path, value: object) -> list[Path]:
    if isinstance(value, str):
        items = [value]
    elif isinstance(value, list):
        items = [item for item in value if isinstance(item, str)]
    else:
        items = []
    return [(project_root / item).resolve() for item in items if item.strip()]


def _write_project_manifest(
    project_root: Path,
    *,
    workspace_name: str | None,
    log_roots: list[str] | None,
    doc_roots: list[str] | None,
    ollama_host: str | None,
    knowledge_backend: str | None,
    chroma_client_mode: str | None,
    chroma_host: str | None,
    chroma_port: int | None,
    chroma_ssl: bool | None,
    chroma_auto_start: bool | None,
    overwrite: bool,
) -> None:
    manifest_path = project_manifest_path(project_root)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    if manifest_path.exists() and not overwrite:
        return

    manifest_workspace_name = (workspace_name or project_root.name).strip() or project_root.name
    unique_log_roots = _normalize_manifest_paths(log_roots or _detect_project_log_roots(project_root))
    unique_doc_roots = _normalize_manifest_paths(doc_roots or _detect_project_doc_roots(project_root))
    manifest_ollama_host = (
        ollama_host or os.getenv("SENTINELOPS_OLLAMA_HOST") or "http://localhost:11434"
    ).strip() or "http://localhost:11434"
    manifest_knowledge_backend = (knowledge_backend or str(_DEFAULT_PROJECT_KNOWLEDGE["backend"])).strip() or str(
        _DEFAULT_PROJECT_KNOWLEDGE["backend"]
    )
    default_chroma_client_mode = "persistent" if manifest_knowledge_backend == "chroma" else str(
        _DEFAULT_PROJECT_KNOWLEDGE["chroma_client_mode"]
    )
    manifest_chroma_client_mode = (chroma_client_mode or default_chroma_client_mode).strip() or default_chroma_client_mode
    manifest_chroma_host = (chroma_host or str(_DEFAULT_PROJECT_KNOWLEDGE["chroma_host"])).strip() or str(
        _DEFAULT_PROJECT_KNOWLEDGE["chroma_host"]
    )
    manifest_chroma_port = chroma_port if chroma_port is not None else int(_DEFAULT_PROJECT_KNOWLEDGE["chroma_port"])
    manifest_chroma_ssl = chroma_ssl if chroma_ssl is not None else bool(_DEFAULT_PROJECT_KNOWLEDGE["chroma_ssl"])
    manifest_chroma_auto_start = (
        chroma_auto_start if chroma_auto_start is not None else bool(_DEFAULT_PROJECT_KNOWLEDGE["chroma_auto_start"])
    )

    lines = [
        'schema_version = "2"',
        f'mode = "{_PROJECT_MODE_PERSONAL}"',
        "",
        "[workspace]",
        f'name = "{_escape_toml_string(manifest_workspace_name)}"',
        "doc_roots = [",
    ]
    lines.extend(f'  "{_escape_toml_string(doc_root)}",' for doc_root in unique_doc_roots)
    lines.extend(
        [
            "]",
            "",
            "[logs]",
            "roots = [",
        ]
    )
    lines.extend(f'  "{_escape_toml_string(log_root)}",' for log_root in unique_log_roots)
    lines.extend(
        [
            "]",
            "",
            "[models]",
            f'analyze = "{_DEFAULT_PROJECT_MODELS["analyze"]}"',
            f'investigate = "{_DEFAULT_PROJECT_MODELS["investigate"]}"',
            f'embedding = "{_DEFAULT_PROJECT_MODELS["embedding"]}"',
            "",
            "[runtime]",
            f'ollama_host = "{_escape_toml_string(manifest_ollama_host)}"',
            "",
            "[knowledge]",
            f'backend = "{_escape_toml_string(manifest_knowledge_backend)}"',
            f'chroma_client_mode = "{_escape_toml_string(manifest_chroma_client_mode)}"',
            f'chroma_host = "{_escape_toml_string(manifest_chroma_host)}"',
            f"chroma_port = {manifest_chroma_port}",
            f"chroma_ssl = {str(manifest_chroma_ssl).lower()}",
            f"chroma_auto_start = {str(manifest_chroma_auto_start).lower()}",
            "",
            "[storage]",
            f'incident_history_dir = "{_DEFAULT_PROJECT_STORAGE["incident_history_dir"]}"',
            f'workflow_checkpoint_path = "{_DEFAULT_PROJECT_STORAGE["workflow_checkpoint_path"]}"',
            f'audit_db_path = "{_DEFAULT_PROJECT_STORAGE["audit_db_path"]}"',
            f'knowledge_index_path = "{_DEFAULT_PROJECT_STORAGE["knowledge_index_path"]}"',
            f'chroma_path = "{_DEFAULT_PROJECT_STORAGE["chroma_path"]}"',
        ]
    )
    manifest_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_project_gitignore(home: Path) -> None:
    gitignore_path = home / ".gitignore"
    if gitignore_path.exists():
        return
    gitignore_path.write_text(_PROJECT_GITIGNORE, encoding="utf-8")


def _ensure_repo_gitignore(project_root: Path) -> None:
    gitignore_path = project_root / ".gitignore"
    if not gitignore_path.exists():
        gitignore_path.write_text(_REPO_GITIGNORE_ENTRY + "\n", encoding="utf-8")
        return

    existing = gitignore_path.read_text(encoding="utf-8", errors="replace")
    lines = [line.strip() for line in existing.splitlines()]
    if _REPO_GITIGNORE_ENTRY in lines:
        return

    suffix = "" if existing.endswith("\n") or not existing else "\n"
    gitignore_path.write_text(existing + suffix + _REPO_GITIGNORE_ENTRY + "\n", encoding="utf-8")


def _write_agent_context(project_root: Path) -> None:
    manifest = read_project_manifest(project_root)
    workspace_name = project_manifest_workspace_name(manifest, fallback=project_root.name)
    log_roots = [
        path.relative_to(project_root).as_posix()
        if path.is_relative_to(project_root)
        else str(path)
        for path in _resolve_project_log_roots(project_root, project_home(project_root), manifest)
        if path.is_relative_to(project_root)
    ]
    if not log_roots:
        log_roots = [path.as_posix() for path in _DEFAULT_PROJECT_LOG_ROOTS]
    doc_roots = project_manifest_doc_roots(manifest)
    content = _render_agent_context(
        project_root,
        workspace_name=workspace_name,
        log_roots=log_roots,
        doc_roots=doc_roots,
    )
    agent_context_path(project_root).write_text(content, encoding="utf-8")


def _render_agent_context(
    project_root: Path,
    *,
    workspace_name: str,
    log_roots: list[str],
    doc_roots: list[str],
) -> str:
    quoted_logs = "\n".join(f"- `{log_root}`" for log_root in log_roots)
    quoted_docs = "\n".join(f"- `{doc_root}`" for doc_root in doc_roots)
    manifest = read_project_manifest(project_root)
    models = project_manifest_models(manifest)
    knowledge_backend = project_manifest_knowledge_backend(manifest)
    chroma_client_mode = project_manifest_chroma_client_mode(manifest)
    return f"""# SentinelOps Agent Context

SentinelOps is attached to this repository as a repo-local project copilot.

## Workspace

- Name: `{workspace_name}`
- Root: `{project_root}`
- Project manifest: `.sentinelops/project.toml`
- Repo-local runtime home: `.sentinelops/`
- Local-first mode: `personal`

## Preferred Commands

- `sentinelops`
- `sentinelops doctor`
- `sentinelops pull-models`
- `sentinelops paths`
- `sentinelops start --no-browser`
- `ollama serve`

## When To Use SentinelOps

Use SentinelOps when the task involves:

- incident triage
- log inspection
- runbooks and operational docs
- readiness or health checks
- remediation workflows
- deployment or service failure analysis
- root-cause diagnostics and prior incident memory

## Project Log Roots

{quoted_logs}

## Project Document Roots

{quoted_docs}

## Runtime Defaults

- Chat model: `{models["analyze"]}`
- Investigation model: `{models["investigate"]}`
- Embedding model: `{models["embedding"]}`
- Knowledge backend: `{knowledge_backend}`
- Chroma client mode: `{chroma_client_mode}`

## Notes For Agents

- Start with `sentinelops paths` to confirm the active workspace.
- Use `sentinelops doctor` before assuming model-backed investigation is ready.
- `.sentinelops/project.toml` is the single repo-local control file for logs, docs, models, runtime host, and storage paths.
- Inspect `root_cause_diagnostics` when SentinelOps API output is available.
- Treat saved incident history as repo-local memory that may help with repeat failures.
- Keep operational guidance grounded in this repository and the resources listed in `.sentinelops/project.toml`.
"""


def _detect_project_log_roots(project_root: Path) -> list[str]:
    detected = [
        relative_path.as_posix()
        for relative_path in _DEFAULT_PROJECT_LOG_ROOTS
        if (project_root / relative_path).exists()
    ]
    return detected or [path.as_posix() for path in _DEFAULT_PROJECT_LOG_ROOTS]


def _detect_project_doc_roots(project_root: Path) -> list[str]:
    detected: list[str] = ["README.md"]
    for relative_path in _DEFAULT_PROJECT_DOC_ROOTS:
        if relative_path.as_posix() == "README.md":
            continue
        if (project_root / relative_path).exists():
            detected.append(relative_path.as_posix())

    for candidate in sorted(project_root.iterdir()):
        if not candidate.is_file():
            continue
        lowered = candidate.name.lower()
        if lowered.startswith("dockerfile"):
            detected.append(candidate.name)
            continue
        if lowered in {"docker-compose.yml", "docker-compose.yaml"}:
            detected.append(candidate.name)
            continue
        if lowered.startswith("compose.") and lowered.endswith((".yml", ".yaml")):
            detected.append(candidate.name)
            continue
        if lowered == ".env.example" or (lowered.startswith(".env.") and lowered.endswith(".example")):
            detected.append(candidate.name)

    return _normalize_manifest_paths(detected)


def _normalize_manifest_paths(values: list[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for value in values:
        cleaned = value.strip().replace("\\", "/")
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        normalized.append(cleaned)
    return normalized


def _resolve_project_storage_paths(home: Path, manifest: dict[str, object]) -> dict[str, Path]:
    resolved: dict[str, Path] = {}
    for key, default_relative_path in _DEFAULT_PROJECT_STORAGE.items():
        configured_value = _manifest_string(manifest, "storage", key, default=default_relative_path)
        configured_path = Path(configured_value).expanduser()
        resolved[key] = configured_path.resolve() if configured_path.is_absolute() else (home / configured_path).resolve()
    return resolved


def _manifest_section(manifest: dict[str, object], section: str) -> dict[str, object]:
    value = manifest.get(section)
    if isinstance(value, dict):
        return value
    return {}


def _manifest_string(
    manifest: dict[str, object],
    section_or_key: str,
    key: str | None = None,
    *,
    legacy_key: str | None = None,
    default: str | None = None,
) -> str | None:
    candidate: object = None
    if key is None:
        candidate = manifest.get(section_or_key)
    else:
        candidate = _manifest_section(manifest, section_or_key).get(key)
    if (candidate is None or not str(candidate).strip()) and legacy_key:
        candidate = manifest.get(legacy_key)
    if candidate is None:
        return default
    cleaned = str(candidate).strip()
    return cleaned or default


def _manifest_string_list(
    manifest: dict[str, object],
    section_or_key: str,
    key: str | None = None,
    *,
    legacy_key: str | None = None,
    default: list[str] | None = None,
) -> list[str]:
    if key is None:
        candidate = manifest.get(section_or_key)
    else:
        candidate = _manifest_section(manifest, section_or_key).get(key)
    if candidate is None and legacy_key:
        candidate = manifest.get(legacy_key)

    if isinstance(candidate, str):
        values = [candidate]
    elif isinstance(candidate, list):
        values = [str(item) for item in candidate]
    else:
        values = list(default or [])

    return _normalize_manifest_paths(values)


def _manifest_int(
    manifest: dict[str, object],
    section_or_key: str,
    key: str | None = None,
    *,
    default: int | None = None,
) -> int | None:
    if key is None:
        candidate = manifest.get(section_or_key)
    else:
        candidate = _manifest_section(manifest, section_or_key).get(key)

    if isinstance(candidate, bool):
        return default
    if isinstance(candidate, int):
        return candidate
    if isinstance(candidate, str):
        cleaned = candidate.strip()
        if cleaned:
            try:
                return int(cleaned)
            except ValueError:
                return default
    return default


def _manifest_bool(
    manifest: dict[str, object],
    section_or_key: str,
    key: str | None = None,
    *,
    default: bool = False,
) -> bool:
    if key is None:
        candidate = manifest.get(section_or_key)
    else:
        candidate = _manifest_section(manifest, section_or_key).get(key)

    if isinstance(candidate, bool):
        return candidate
    if isinstance(candidate, str):
        normalized = candidate.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    return default


def _escape_toml_string(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _copy_path(source_path: Path, destination_path: Path, *, overwrite: bool) -> None:
    if source_path.is_dir():
        if destination_path.exists():
            if overwrite:
                shutil.rmtree(destination_path)
            else:
                return
        shutil.copytree(source_path, destination_path)
        return

    destination_path.parent.mkdir(parents=True, exist_ok=True)
    if destination_path.exists() and not overwrite:
        return
    shutil.copy2(source_path, destination_path)
