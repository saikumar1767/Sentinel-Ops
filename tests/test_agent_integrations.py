import json
from pathlib import Path

from app import bootstrap
from app.agent_integrations import CODEX_PLUGIN_NAME, install_agent_integrations


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _seed_source_root(source_root: Path) -> None:
    _write(source_root / "config" / "sentinelops.toml", 'app_name = "SentinelOps"\n')
    _write(source_root / "config" / "sentinelops.production.toml", 'deployment_mode = "production"\n')
    _write(source_root / "data" / "incident_templates" / "database.md", "# template\n")
    _write(source_root / "data" / "incident_library" / "incident.json", "{}\n")
    _write(source_root / "data" / "knowledge" / "runbook.md", "# runbook\n")
    _write(source_root / "data" / "logs" / "app.log", "log\n")
    _write(source_root / "data" / "reference_incidents" / "incident.json", "{}\n")
    _write(source_root / "samples" / "sample1.log", "sample\n")


def test_install_agent_integrations_generates_codex_bundle(tmp_path, monkeypatch) -> None:
    source_root = tmp_path / "source"
    project_root = tmp_path / "checkout-service"
    project_root.mkdir(parents=True, exist_ok=True)
    (project_root / ".git").mkdir()
    _seed_source_root(source_root)
    monkeypatch.setattr(bootstrap, "resource_root", lambda: source_root)

    result = install_agent_integrations(
        project_root=project_root,
        agent="codex",
    )

    marketplace_path = project_root / ".agents" / "plugins" / "marketplace.json"
    plugin_manifest_path = project_root / "plugins" / CODEX_PLUGIN_NAME / ".codex-plugin" / "plugin.json"
    skill_path = (
        project_root
        / "plugins"
        / CODEX_PLUGIN_NAME
        / "skills"
        / "project-ops-copilot"
        / "SKILL.md"
    )
    agents_path = project_root / "AGENTS.md"

    assert result.project_root == project_root.resolve()
    assert result.installed_agents == ("codex",)
    assert not result.skipped_files
    assert marketplace_path in result.written_files
    assert plugin_manifest_path.exists()
    assert skill_path.exists()
    assert agents_path.exists()

    marketplace_payload = json.loads(marketplace_path.read_text(encoding="utf-8"))
    plugin_names = [plugin["name"] for plugin in marketplace_payload["plugins"]]
    assert CODEX_PLUGIN_NAME in plugin_names

    agents_text = agents_path.read_text(encoding="utf-8")
    assert "<!-- sentinelops:start -->" in agents_text
    assert "checkout-service" in agents_text
    assert ".sentinelops/project.toml" in agents_text


def test_install_agent_integrations_merges_shared_repo_files(tmp_path, monkeypatch) -> None:
    source_root = tmp_path / "source"
    project_root = tmp_path / "payments-service"
    project_root.mkdir(parents=True, exist_ok=True)
    (project_root / ".git").mkdir()
    _seed_source_root(source_root)
    monkeypatch.setattr(bootstrap, "resource_root", lambda: source_root)

    (project_root / "AGENTS.md").write_text("# Team Rules\n\nKeep tests green.\n", encoding="utf-8")
    _write(
        project_root / ".github" / "copilot-instructions.md",
        "# Existing Copilot Rules\n\nPrefer small diffs.\n",
    )

    result = install_agent_integrations(
        project_root=project_root,
        agent="all",
    )

    assert result.installed_agents == ("claude", "codex", "cursor", "windsurf", "cline", "copilot")
    assert (project_root / ".claude" / "skills" / "sentinelops-check" / "SKILL.md").exists()
    assert (project_root / ".claude" / "agents" / "sentinelops-ops-copilot.md").exists()
    assert (project_root / ".cursor" / "rules" / "sentinelops.mdc").exists()
    assert (project_root / ".windsurf" / "rules" / "sentinelops.md").exists()
    assert (project_root / ".clinerules" / "sentinelops.md").exists()

    agents_text = (project_root / "AGENTS.md").read_text(encoding="utf-8")
    assert "# Team Rules" in agents_text
    assert "<!-- sentinelops:start -->" in agents_text

    claude_text = (project_root / "CLAUDE.md").read_text(encoding="utf-8")
    assert "<!-- sentinelops:claude:start -->" in claude_text
    assert "/sentinelops-check" in claude_text

    copilot_text = (project_root / ".github" / "copilot-instructions.md").read_text(encoding="utf-8")
    assert "# Existing Copilot Rules" in copilot_text
    assert "<!-- sentinelops:copilot:start -->" in copilot_text


def test_install_agent_integrations_skips_existing_managed_files_without_overwrite(tmp_path, monkeypatch) -> None:
    source_root = tmp_path / "source"
    project_root = tmp_path / "catalog-service"
    project_root.mkdir(parents=True, exist_ok=True)
    (project_root / ".git").mkdir()
    _seed_source_root(source_root)
    monkeypatch.setattr(bootstrap, "resource_root", lambda: source_root)

    install_agent_integrations(project_root=project_root, agent="codex")
    command_path = project_root / "plugins" / CODEX_PLUGIN_NAME / "commands" / "start-sentinelops.md"
    command_path.write_text("custom command\n", encoding="utf-8")

    result = install_agent_integrations(project_root=project_root, agent="codex", overwrite=False)

    assert command_path in result.skipped_files
    assert command_path.read_text(encoding="utf-8") == "custom command\n"

    overwritten = install_agent_integrations(project_root=project_root, agent="codex", overwrite=True)
    assert command_path in overwritten.written_files
    assert "Start SentinelOps in the current attached repository." in command_path.read_text(encoding="utf-8")
