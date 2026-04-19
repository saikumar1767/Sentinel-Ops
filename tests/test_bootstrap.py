import json
import os
from pathlib import Path

from app import bootstrap


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_ensure_app_home_copies_bundled_resources(tmp_path, monkeypatch) -> None:
    source_root = tmp_path / "source"
    _write(source_root / "config" / "sentinelops.toml", 'app_name = "SentinelOps"\n')
    _write(source_root / "data" / "incident_templates" / "database.md", "# template\n")
    _write(source_root / "data" / "incident_library" / "incident.json", "{}\n")
    _write(source_root / "data" / "knowledge" / "runbook.md", "# runbook\n")
    _write(source_root / "data" / "logs" / "app.log", "log\n")
    _write(source_root / "data" / "reference_incidents" / "incident.json", "{}\n")
    _write(source_root / "samples" / "sample1.log", "sample\n")

    monkeypatch.setattr(bootstrap, "resource_root", lambda: source_root)
    home = bootstrap.ensure_app_home(app_home=tmp_path / "home")

    assert (home / "config" / "sentinelops.toml").exists()
    assert (home / "data" / "incident_templates" / "database.md").exists()
    assert (home / "data" / "incident_library" / "incident.json").exists()
    assert (home / "data" / "knowledge" / "runbook.md").exists()
    assert (home / "samples" / "sample1.log").exists()
    assert (home / "data" / "runtime").exists()


def test_apply_runtime_environment_sets_expected_paths(tmp_path, monkeypatch) -> None:
    source_root = tmp_path / "source"
    _write(source_root / "config" / "sentinelops.toml", 'app_name = "SentinelOps"\n')
    _write(source_root / "config" / "sentinelops.production.toml", 'deployment_mode = "production"\n')
    _write(source_root / "data" / "incident_templates" / "database.md", "# template\n")
    _write(source_root / "data" / "incident_library" / "incident.json", "{}\n")
    _write(source_root / "data" / "knowledge" / "runbook.md", "# runbook\n")
    _write(source_root / "data" / "logs" / "app.log", "log\n")
    _write(source_root / "data" / "reference_incidents" / "incident.json", "{}\n")
    _write(source_root / "samples" / "sample1.log", "sample\n")

    monkeypatch.setattr(bootstrap, "resource_root", lambda: source_root)
    monkeypatch.delenv("SENTINELOPS_ALLOWED_LOG_ROOTS", raising=False)
    monkeypatch.delenv("SENTINELOPS_CONFIG_FILE", raising=False)
    tracked_keys = [
        "SENTINELOPS_HOME",
        "SENTINELOPS_CONFIG_FILE",
        "SENTINELOPS_ALLOWED_LOG_ROOTS",
        "SENTINELOPS_INCIDENT_TEMPLATES_DIR",
        "SENTINELOPS_INCIDENT_HISTORY_DIR",
        "SENTINELOPS_WORKFLOW_CHECKPOINT_PATH",
        "SENTINELOPS_AUDIT_DB_PATH",
        "SENTINELOPS_KNOWLEDGE_BASE_DIR",
        "SENTINELOPS_KNOWLEDGE_INDEX_PATH",
        "SENTINELOPS_CHROMA_PATH",
        "SENTINELOPS_INCIDENT_LIBRARY_DIR",
        "SENTINELOPS_REFERENCE_INCIDENTS_DIR",
    ]
    previous = {key: os.environ.get(key) for key in tracked_keys}

    try:
        home = bootstrap.apply_runtime_environment(app_home=tmp_path / "home", profile="production")

        assert Path(os.environ["SENTINELOPS_HOME"]) == home
        assert Path(os.environ["SENTINELOPS_CONFIG_FILE"]).name == "sentinelops.production.toml"
        allowed_roots = json.loads(os.environ["SENTINELOPS_ALLOWED_LOG_ROOTS"])
        assert str(home / "samples") in allowed_roots
        assert Path(os.environ["SENTINELOPS_INCIDENT_LIBRARY_DIR"]) == home / "data" / "incident_library"
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
