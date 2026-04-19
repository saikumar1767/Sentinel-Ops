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
_PROJECT_GITIGNORE = """data/runtime/
data/chroma/
data/logs/
"""


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
    overwrite: bool = False,
) -> tuple[Path, Path]:
    resolved_project_root = (project_root or detect_repository_root()).expanduser().resolve()
    home = ensure_app_home(app_home=project_home(resolved_project_root), overwrite=overwrite)
    _write_project_manifest(
        resolved_project_root,
        workspace_name=workspace_name,
        log_roots=log_roots,
        overwrite=overwrite,
    )
    _write_project_gitignore(home)
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
        workspace_name = str(manifest.get("workspace_name") or resolved_project_root.name)
        allowed_log_roots = _resolve_project_log_roots(resolved_project_root, home, manifest)
        os.environ[SENTINELOPS_WORKSPACE_ROOT_ENV] = str(resolved_project_root)
        os.environ[SENTINELOPS_WORKSPACE_NAME_ENV] = workspace_name
    else:
        home = ensure_app_home(app_home=app_home)
        allowed_log_roots = [home / "samples", home / "data" / "logs"]
        os.environ.pop(SENTINELOPS_WORKSPACE_ROOT_ENV, None)
        os.environ.pop(SENTINELOPS_WORKSPACE_NAME_ENV, None)

    runtime = _runtime_dir(home)
    runtime.mkdir(parents=True, exist_ok=True)

    config_name = "sentinelops.production.toml" if profile == "production" else "sentinelops.toml"
    os.environ[SENTINELOPS_HOME_ENV] = str(home)
    os.environ["SENTINELOPS_CONFIG_FILE"] = str(home / "config" / config_name)
    os.environ["SENTINELOPS_ALLOWED_LOG_ROOTS"] = json.dumps([str(path) for path in allowed_log_roots])
    os.environ["SENTINELOPS_INCIDENT_TEMPLATES_DIR"] = str(home / "data" / "incident_templates")
    os.environ["SENTINELOPS_INCIDENT_HISTORY_DIR"] = str(runtime / "recent_incidents")
    os.environ["SENTINELOPS_WORKFLOW_CHECKPOINT_PATH"] = str(runtime / "workflow" / "checkpoints.sqlite")
    os.environ["SENTINELOPS_AUDIT_DB_PATH"] = str(runtime / "audit" / "audit.sqlite")
    os.environ["SENTINELOPS_KNOWLEDGE_BASE_DIR"] = str(home / "data" / "knowledge")
    os.environ["SENTINELOPS_KNOWLEDGE_INDEX_PATH"] = str(runtime / "knowledge" / "knowledge_index.json")
    os.environ["SENTINELOPS_CHROMA_PATH"] = str(runtime / "chroma")
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
        workspace_name = str(read_project_manifest(resolved_project_root).get("workspace_name") or resolved_project_root.name)
    else:
        home = (app_home or default_app_home()).expanduser().resolve()
        workspace_name = ""

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


def _runtime_dir(home: Path) -> Path:
    return home / "data" / "runtime"


def _search_roots(start_path: Path | None) -> list[Path]:
    current = (start_path or Path.cwd()).expanduser().resolve()
    return [current, *current.parents]


def _resolve_project_log_roots(project_root: Path, home: Path, manifest: dict[str, object]) -> list[Path]:
    configured_roots = _coerce_manifest_paths(project_root, manifest.get("log_roots"))
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
    overwrite: bool,
) -> None:
    manifest_path = project_manifest_path(project_root)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    if manifest_path.exists() and not overwrite:
        return

    manifest_workspace_name = (workspace_name or project_root.name).strip() or project_root.name
    configured_log_roots = log_roots or [path.as_posix() for path in _DEFAULT_PROJECT_LOG_ROOTS]
    unique_log_roots: list[str] = []
    seen: set[str] = set()
    for log_root in configured_log_roots:
        cleaned = log_root.strip().replace("\\", "/")
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        unique_log_roots.append(cleaned)

    lines = [
        'schema_version = "1"',
        f'workspace_name = "{_escape_toml_string(manifest_workspace_name)}"',
        "log_roots = [",
    ]
    lines.extend(f'  "{_escape_toml_string(log_root)}",' for log_root in unique_log_roots)
    lines.append("]")
    manifest_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_project_gitignore(home: Path) -> None:
    gitignore_path = home / ".gitignore"
    if gitignore_path.exists():
        return
    gitignore_path.write_text(_PROJECT_GITIGNORE, encoding="utf-8")


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
