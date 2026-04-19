from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

from app.settings import PROJECT_ROOT

SENTINELOPS_HOME_ENV = "SENTINELOPS_HOME"

_BUNDLED_RELATIVE_PATHS = (
    Path("config"),
    Path("data") / "incident_library",
    Path("data") / "incident_templates",
    Path("data") / "knowledge",
    Path("data") / "logs",
    Path("data") / "reference_incidents",
    Path("samples"),
)


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


def apply_runtime_environment(*, app_home: Path | None = None, profile: str = "local") -> Path:
    home = ensure_app_home(app_home=app_home)
    runtime = _runtime_dir(home)
    runtime.mkdir(parents=True, exist_ok=True)

    config_name = "sentinelops.production.toml" if profile == "production" else "sentinelops.toml"
    os.environ[SENTINELOPS_HOME_ENV] = str(home)
    os.environ["SENTINELOPS_CONFIG_FILE"] = str(home / "config" / config_name)
    os.environ.setdefault(
        "SENTINELOPS_ALLOWED_LOG_ROOTS",
        json.dumps([str(home / "samples"), str(home / "data" / "logs")]),
    )
    os.environ.setdefault("SENTINELOPS_INCIDENT_TEMPLATES_DIR", str(home / "data" / "incident_templates"))
    os.environ.setdefault("SENTINELOPS_INCIDENT_HISTORY_DIR", str(runtime / "recent_incidents"))
    os.environ.setdefault("SENTINELOPS_WORKFLOW_CHECKPOINT_PATH", str(runtime / "workflow" / "checkpoints.sqlite"))
    os.environ.setdefault("SENTINELOPS_AUDIT_DB_PATH", str(runtime / "audit" / "audit.sqlite"))
    os.environ.setdefault("SENTINELOPS_KNOWLEDGE_BASE_DIR", str(home / "data" / "knowledge"))
    os.environ.setdefault("SENTINELOPS_KNOWLEDGE_INDEX_PATH", str(runtime / "knowledge" / "knowledge_index.json"))
    os.environ.setdefault("SENTINELOPS_CHROMA_PATH", str(runtime / "chroma"))
    os.environ.setdefault("SENTINELOPS_INCIDENT_LIBRARY_DIR", str(home / "data" / "incident_library"))
    os.environ.setdefault("SENTINELOPS_REFERENCE_INCIDENTS_DIR", str(home / "data" / "reference_incidents"))
    return home


def runtime_summary(*, app_home: Path | None = None, profile: str = "local") -> dict[str, str]:
    home = (app_home or default_app_home()).expanduser().resolve()
    runtime = _runtime_dir(home)
    config_name = "sentinelops.production.toml" if profile == "production" else "sentinelops.toml"
    return {
        "app_home": str(home),
        "resource_root": str(resource_root()),
        "config_file": str(home / "config" / config_name),
        "runtime_dir": str(runtime),
        "samples_dir": str(home / "samples"),
        "logs_dir": str(home / "data" / "logs"),
    }


def _runtime_dir(home: Path) -> Path:
    return home / "data" / "runtime"


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
