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
        "SENTINELOPS_WORKSPACE_ROOT",
        "SENTINELOPS_WORKSPACE_NAME",
        "SENTINELOPS_WORKSPACE_DOC_ROOTS",
        "SENTINELOPS_ANALYZE_MODEL",
        "SENTINELOPS_INVESTIGATE_MODEL",
        "SENTINELOPS_EMBEDDING_MODEL",
        "SENTINELOPS_OLLAMA_HOST",
        "SENTINELOPS_KNOWLEDGE_STORE_BACKEND",
        "SENTINELOPS_CHROMA_CLIENT_MODE",
        "SENTINELOPS_CHROMA_HOST",
        "SENTINELOPS_CHROMA_PORT",
        "SENTINELOPS_CHROMA_SSL",
        "SENTINELOPS_CHROMA_AUTO_START",
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


def test_attach_project_creates_repo_local_manifest_and_gitignore(tmp_path, monkeypatch) -> None:
    source_root = tmp_path / "source"
    project_root = tmp_path / "checkout-service"
    project_root.mkdir(parents=True, exist_ok=True)
    (project_root / ".git").mkdir()
    (project_root / ".gitignore").write_text("node_modules/\n", encoding="utf-8")
    _write(source_root / "config" / "sentinelops.toml", 'app_name = "SentinelOps"\n')
    _write(source_root / "config" / "sentinelops.production.toml", 'deployment_mode = "production"\n')
    _write(source_root / "data" / "incident_templates" / "database.md", "# template\n")
    _write(source_root / "data" / "incident_library" / "incident.json", "{}\n")
    _write(source_root / "data" / "knowledge" / "runbook.md", "# runbook\n")
    _write(source_root / "data" / "logs" / "app.log", "log\n")
    _write(source_root / "data" / "reference_incidents" / "incident.json", "{}\n")
    _write(source_root / "samples" / "sample1.log", "sample\n")

    monkeypatch.setattr(bootstrap, "resource_root", lambda: source_root)

    attached_root, home = bootstrap.attach_project(
        project_root=project_root,
        workspace_name="Checkout Service",
        log_roots=["logs", "services/api/logs"],
        ollama_host="http://host.docker.internal:11434",
        knowledge_backend="chroma",
        chroma_client_mode="persistent",
        chroma_host="127.0.0.1",
        chroma_port=8012,
        chroma_auto_start=True,
    )

    manifest_path = project_root / ".sentinelops" / "project.toml"
    assert attached_root == project_root.resolve()
    assert home == (project_root / ".sentinelops").resolve()
    assert manifest_path.exists()
    assert (project_root / ".sentinelops" / ".gitignore").exists()
    assert (project_root / ".sentinelops" / "agent-context.md").exists()
    manifest_text = manifest_path.read_text(encoding="utf-8")
    assert 'schema_version = "2"' in manifest_text
    assert 'mode = "personal"' in manifest_text
    assert '[workspace]' in manifest_text
    assert 'name = "Checkout Service"' in manifest_text
    assert '[logs]' in manifest_text
    assert '"services/api/logs"' in manifest_text
    assert '[models]' in manifest_text
    assert '[runtime]' in manifest_text
    assert 'ollama_host = "http://host.docker.internal:11434"' in manifest_text
    assert '[knowledge]' in manifest_text
    assert 'backend = "chroma"' in manifest_text
    assert 'chroma_client_mode = "persistent"' in manifest_text
    assert "chroma_auto_start = true" in manifest_text
    assert '[storage]' in manifest_text
    repo_gitignore = (project_root / ".gitignore").read_text(encoding="utf-8")
    assert "node_modules/" in repo_gitignore
    assert ".sentinelops/" in repo_gitignore

    agent_context = (project_root / ".sentinelops" / "agent-context.md").read_text(encoding="utf-8")
    assert "Checkout Service" in agent_context
    assert "`sentinelops doctor`" in agent_context
    assert ".sentinelops/project.toml" in agent_context


def test_apply_runtime_environment_uses_attached_project_when_manifest_exists(tmp_path, monkeypatch) -> None:
    source_root = tmp_path / "source"
    project_root = tmp_path / "payments-service"
    project_root.mkdir(parents=True, exist_ok=True)
    (project_root / ".git").mkdir()
    (project_root / "docs").mkdir()
    (project_root / "logs").mkdir()
    _write(source_root / "config" / "sentinelops.toml", 'app_name = "SentinelOps"\n')
    _write(source_root / "config" / "sentinelops.production.toml", 'deployment_mode = "production"\n')
    _write(source_root / "data" / "incident_templates" / "database.md", "# template\n")
    _write(source_root / "data" / "incident_library" / "incident.json", "{}\n")
    _write(source_root / "data" / "knowledge" / "runbook.md", "# runbook\n")
    _write(source_root / "data" / "logs" / "app.log", "log\n")
    _write(source_root / "data" / "reference_incidents" / "incident.json", "{}\n")
    _write(source_root / "samples" / "sample1.log", "sample\n")

    monkeypatch.setattr(bootstrap, "resource_root", lambda: source_root)
    monkeypatch.chdir(project_root)
    tracked_keys = [
        "SENTINELOPS_HOME",
        "SENTINELOPS_CONFIG_FILE",
        "SENTINELOPS_ALLOWED_LOG_ROOTS",
        "SENTINELOPS_WORKSPACE_ROOT",
        "SENTINELOPS_WORKSPACE_NAME",
        "SENTINELOPS_WORKSPACE_DOC_ROOTS",
        "SENTINELOPS_ANALYZE_MODEL",
        "SENTINELOPS_INVESTIGATE_MODEL",
        "SENTINELOPS_EMBEDDING_MODEL",
        "SENTINELOPS_OLLAMA_HOST",
        "SENTINELOPS_KNOWLEDGE_STORE_BACKEND",
        "SENTINELOPS_CHROMA_CLIENT_MODE",
        "SENTINELOPS_CHROMA_HOST",
        "SENTINELOPS_CHROMA_PORT",
        "SENTINELOPS_CHROMA_SSL",
        "SENTINELOPS_CHROMA_AUTO_START",
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
    bootstrap.attach_project(project_root=project_root, workspace_name="Payments Service", log_roots=["logs"])
    try:
        home = bootstrap.apply_runtime_environment(profile="local")

        assert home == (project_root / ".sentinelops").resolve()
        assert Path(os.environ["SENTINELOPS_WORKSPACE_ROOT"]) == project_root.resolve()
        assert os.environ["SENTINELOPS_WORKSPACE_NAME"] == "Payments Service"
        allowed_roots = json.loads(os.environ["SENTINELOPS_ALLOWED_LOG_ROOTS"])
        assert str((project_root / "logs").resolve()) in allowed_roots
        doc_roots = json.loads(os.environ["SENTINELOPS_WORKSPACE_DOC_ROOTS"])
        assert "README.md" in doc_roots
        assert os.environ["SENTINELOPS_ANALYZE_MODEL"] == "mistral"
        assert os.environ["SENTINELOPS_INVESTIGATE_MODEL"] == "mistral"
        assert os.environ["SENTINELOPS_EMBEDDING_MODEL"] == "nomic-embed-text"
        assert os.environ["SENTINELOPS_OLLAMA_HOST"] == "http://localhost:11434"
        assert os.environ["SENTINELOPS_KNOWLEDGE_STORE_BACKEND"] == "simple"
        assert os.environ["SENTINELOPS_CHROMA_CLIENT_MODE"] == "persistent"
        assert os.environ["SENTINELOPS_CHROMA_HOST"] == "127.0.0.1"
        assert os.environ["SENTINELOPS_CHROMA_PORT"] == "8012"
        assert os.environ["SENTINELOPS_CHROMA_AUTO_START"] == "false"

        summary = bootstrap.runtime_summary()
        assert summary["workspace_root"] == str(project_root.resolve())
        assert summary["workspace_name"] == "Payments Service"
        assert summary["project_mode"] == "personal"
        assert summary["project_knowledge_backend"] == "simple"
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def test_apply_runtime_environment_honors_manifest_overrides(tmp_path, monkeypatch) -> None:
    source_root = tmp_path / "source"
    project_root = tmp_path / "inventory-service"
    project_root.mkdir(parents=True, exist_ok=True)
    (project_root / ".git").mkdir()
    (project_root / "docs").mkdir()
    (project_root / "ops").mkdir()
    (project_root / "custom-logs").mkdir()
    _write(source_root / "config" / "sentinelops.toml", 'app_name = "SentinelOps"\n')
    _write(source_root / "config" / "sentinelops.production.toml", 'deployment_mode = "production"\n')
    _write(source_root / "data" / "incident_templates" / "database.md", "# template\n")
    _write(source_root / "data" / "incident_library" / "incident.json", "{}\n")
    _write(source_root / "data" / "knowledge" / "runbook.md", "# runbook\n")
    _write(source_root / "data" / "logs" / "app.log", "log\n")
    _write(source_root / "data" / "reference_incidents" / "incident.json", "{}\n")
    _write(source_root / "samples" / "sample1.log", "sample\n")

    monkeypatch.setattr(bootstrap, "resource_root", lambda: source_root)
    tracked_keys = [
        "SENTINELOPS_HOME",
        "SENTINELOPS_CONFIG_FILE",
        "SENTINELOPS_ALLOWED_LOG_ROOTS",
        "SENTINELOPS_WORKSPACE_ROOT",
        "SENTINELOPS_WORKSPACE_NAME",
        "SENTINELOPS_WORKSPACE_DOC_ROOTS",
        "SENTINELOPS_ANALYZE_MODEL",
        "SENTINELOPS_INVESTIGATE_MODEL",
        "SENTINELOPS_EMBEDDING_MODEL",
        "SENTINELOPS_OLLAMA_HOST",
        "SENTINELOPS_KNOWLEDGE_STORE_BACKEND",
        "SENTINELOPS_CHROMA_CLIENT_MODE",
        "SENTINELOPS_CHROMA_HOST",
        "SENTINELOPS_CHROMA_PORT",
        "SENTINELOPS_CHROMA_SSL",
        "SENTINELOPS_CHROMA_AUTO_START",
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
    bootstrap.attach_project(project_root=project_root)
    (project_root / ".sentinelops" / "project.toml").write_text(
        'schema_version = "2"\n'
        'mode = "personal"\n\n'
        "[workspace]\n"
        'name = "Inventory Service"\n'
        'doc_roots = ["docs", "ops"]\n\n'
        "[logs]\n"
        'roots = ["custom-logs"]\n\n'
        "[models]\n"
        'analyze = "mistral"\n'
        'investigate = "ministral:8b-instruct"\n'
        'embedding = "nomic-embed-text"\n\n'
        "[runtime]\n"
        'ollama_host = "http://127.0.0.1:22434"\n\n'
        "[knowledge]\n"
        'backend = "chroma"\n'
        'chroma_client_mode = "persistent"\n'
        'chroma_host = "127.0.0.1"\n'
        "chroma_port = 8013\n"
        "chroma_ssl = false\n"
        "chroma_auto_start = true\n\n"
        "[storage]\n"
        'incident_history_dir = "runtime/incidents"\n'
        'workflow_checkpoint_path = "runtime/workflow.sqlite"\n'
        'audit_db_path = "runtime/audit.sqlite"\n'
        'knowledge_index_path = "runtime/knowledge.json"\n'
        'chroma_path = "runtime/chroma-db"\n',
        encoding="utf-8",
    )

    try:
        bootstrap.apply_runtime_environment(project_root=project_root)

        assert json.loads(os.environ["SENTINELOPS_WORKSPACE_DOC_ROOTS"]) == ["docs", "ops"]
        assert os.environ["SENTINELOPS_ANALYZE_MODEL"] == "mistral"
        assert os.environ["SENTINELOPS_INVESTIGATE_MODEL"] == "ministral:8b-instruct"
        assert os.environ["SENTINELOPS_OLLAMA_HOST"] == "http://127.0.0.1:22434"
        assert os.environ["SENTINELOPS_KNOWLEDGE_STORE_BACKEND"] == "chroma"
        assert os.environ["SENTINELOPS_CHROMA_PORT"] == "8013"
        assert os.environ["SENTINELOPS_CHROMA_AUTO_START"] == "true"
        assert Path(os.environ["SENTINELOPS_INCIDENT_HISTORY_DIR"]).name == "incidents"
        assert Path(os.environ["SENTINELOPS_WORKFLOW_CHECKPOINT_PATH"]).name == "workflow.sqlite"
        assert Path(os.environ["SENTINELOPS_CHROMA_PATH"]).name == "chroma-db"
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
