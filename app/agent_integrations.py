from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from app.bootstrap import (
    attach_project,
    project_manifest_doc_roots,
    project_manifest_log_roots,
    project_manifest_workspace_name,
    read_project_manifest,
)

SUPPORTED_AGENTS = ("claude", "codex", "cursor", "windsurf", "cline", "copilot")
CODEX_PLUGIN_NAME = "sentinelops-copilot"
CODEX_SKILL_NAME = "project-ops-copilot"
AGENTS_START_MARKER = "<!-- sentinelops:start -->"
AGENTS_END_MARKER = "<!-- sentinelops:end -->"
CLAUDE_START_MARKER = "<!-- sentinelops:claude:start -->"
CLAUDE_END_MARKER = "<!-- sentinelops:claude:end -->"
COPILOT_START_MARKER = "<!-- sentinelops:copilot:start -->"
COPILOT_END_MARKER = "<!-- sentinelops:copilot:end -->"

PLUGIN_ICON_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 96 96" fill="none">
  <rect width="96" height="96" rx="24" fill="#0F172A"/>
  <path d="M24 30h48v10H24z" fill="#38BDF8"/>
  <path d="M24 48h30v10H24z" fill="#22C55E"/>
  <path d="M24 66h18v6H24z" fill="#F8FAFC"/>
  <path d="M61 45l11 11-11 11" stroke="#F8FAFC" stroke-width="6" stroke-linecap="round" stroke-linejoin="round"/>
</svg>
"""


@dataclass(frozen=True)
class GeneratedFile:
    content: str
    shared_file: bool = False


@dataclass(frozen=True)
class AgentInstallResult:
    project_root: Path
    installed_agents: tuple[str, ...]
    written_files: tuple[Path, ...]
    skipped_files: tuple[Path, ...]


def install_agent_integrations(
    *,
    project_root: Path | None = None,
    agent: str = "all",
    overwrite: bool = False,
) -> AgentInstallResult:
    if agent != "all" and agent not in SUPPORTED_AGENTS:
        raise ValueError(f"Unsupported agent '{agent}'.")

    resolved_project_root, _ = attach_project(project_root=project_root, overwrite=overwrite)
    manifest = read_project_manifest(resolved_project_root)
    workspace_name = project_manifest_workspace_name(manifest, fallback=resolved_project_root.name)
    log_roots = project_manifest_log_roots(manifest)
    doc_roots = project_manifest_doc_roots(manifest)
    selected_agents = SUPPORTED_AGENTS if agent == "all" else (agent,)

    generated_files: dict[Path, GeneratedFile] = {}
    if "claude" in selected_agents:
        generated_files.update(
            _claude_bundle_files(
                resolved_project_root,
                workspace_name=workspace_name,
                log_roots=log_roots,
                doc_roots=doc_roots,
            )
        )
    if "codex" in selected_agents:
        generated_files.update(_codex_bundle_files(resolved_project_root, workspace_name=workspace_name))
    if "cursor" in selected_agents:
        generated_files[resolved_project_root / ".cursor" / "rules" / "sentinelops.mdc"] = GeneratedFile(
            _cursor_rule()
        )
    if "windsurf" in selected_agents:
        generated_files[resolved_project_root / ".windsurf" / "rules" / "sentinelops.md"] = GeneratedFile(
            _windsurf_rule()
        )
    if "cline" in selected_agents:
        generated_files[resolved_project_root / ".clinerules" / "sentinelops.md"] = GeneratedFile(_cline_rule())
    if "copilot" in selected_agents:
        generated_files[resolved_project_root / ".github" / "copilot-instructions.md"] = GeneratedFile(
            _merge_marked_block(
                existing_text=_read_text_if_exists(resolved_project_root / ".github" / "copilot-instructions.md"),
                start_marker=COPILOT_START_MARKER,
                end_marker=COPILOT_END_MARKER,
                block=_copilot_instructions(),
            ),
            shared_file=True,
        )

    generated_files[resolved_project_root / "AGENTS.md"] = GeneratedFile(
        _merge_marked_block(
            existing_text=_read_text_if_exists(resolved_project_root / "AGENTS.md"),
            start_marker=AGENTS_START_MARKER,
            end_marker=AGENTS_END_MARKER,
            block=_agents_block(workspace_name=workspace_name, log_roots=log_roots, doc_roots=doc_roots),
        ),
        shared_file=True,
    )

    written_files, skipped_files = _write_files(generated_files, overwrite=overwrite)
    return AgentInstallResult(
        project_root=resolved_project_root,
        installed_agents=tuple(selected_agents),
        written_files=tuple(written_files),
        skipped_files=tuple(skipped_files),
    )


def _write_files(
    files_to_write: dict[Path, GeneratedFile],
    *,
    overwrite: bool,
) -> tuple[list[Path], list[Path]]:
    written: list[Path] = []
    skipped: list[Path] = []

    for path, generated_file in files_to_write.items():
        existing_text = _read_text_if_exists(path)
        if existing_text == generated_file.content:
            continue
        if path.exists() and not overwrite and not generated_file.shared_file:
            skipped.append(path)
            continue

        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(generated_file.content, encoding="utf-8")
        written.append(path)

    return written, skipped


def _codex_bundle_files(project_root: Path, *, workspace_name: str) -> dict[Path, GeneratedFile]:
    plugin_root = project_root / "plugins" / CODEX_PLUGIN_NAME
    marketplace_path = project_root / ".agents" / "plugins" / "marketplace.json"
    existing_marketplace = _read_marketplace_payload(marketplace_path)

    return {
        marketplace_path: GeneratedFile(
            _marketplace_json(existing_marketplace),
            shared_file=True,
        ),
        plugin_root / ".codex-plugin" / "plugin.json": GeneratedFile(_plugin_manifest_json()),
        plugin_root / "assets" / "sentinelops.svg": GeneratedFile(PLUGIN_ICON_SVG),
        plugin_root / "skills" / CODEX_SKILL_NAME / "SKILL.md": GeneratedFile(
            _codex_skill_md(workspace_name=workspace_name)
        ),
        plugin_root / "skills" / CODEX_SKILL_NAME / "agents" / "openai.yaml": GeneratedFile(
            _codex_skill_openai_yaml()
        ),
        plugin_root / "commands" / "start-sentinelops.md": GeneratedFile(_command_start()),
        plugin_root / "commands" / "check-sentinelops.md": GeneratedFile(_command_check()),
        plugin_root / "commands" / "investigate-ops.md": GeneratedFile(_command_investigate()),
        plugin_root / "agents" / "openai.yaml": GeneratedFile(_plugin_openai_yaml()),
    }


def _claude_bundle_files(
    project_root: Path,
    *,
    workspace_name: str,
    log_roots: list[str],
    doc_roots: list[str],
) -> dict[Path, GeneratedFile]:
    claude_root = project_root / ".claude"
    return {
        claude_root / "skills" / "sentinelops-check" / "SKILL.md": GeneratedFile(_claude_skill_check()),
        claude_root / "skills" / "sentinelops-start" / "SKILL.md": GeneratedFile(_claude_skill_start()),
        claude_root / "skills" / "sentinelops-investigate" / "SKILL.md": GeneratedFile(
            _claude_skill_investigate()
        ),
        claude_root / "skills" / "sentinelops-pull-models" / "SKILL.md": GeneratedFile(
            _claude_skill_pull_models()
        ),
        claude_root / "agents" / "sentinelops-ops-copilot.md": GeneratedFile(
            _claude_subagent(workspace_name=workspace_name)
        ),
        project_root / "CLAUDE.md": GeneratedFile(
            _merge_marked_block(
                existing_text=_read_text_if_exists(project_root / "CLAUDE.md"),
                start_marker=CLAUDE_START_MARKER,
                end_marker=CLAUDE_END_MARKER,
                block=_claude_memory_block(
                    workspace_name=workspace_name,
                    log_roots=log_roots,
                    doc_roots=doc_roots,
                ),
            ),
            shared_file=True,
        ),
    }


def _read_marketplace_payload(path: Path) -> dict[str, object] | None:
    if not path.exists():
        return None

    raw_text = path.read_text(encoding="utf-8", errors="replace")
    try:
        payload = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Existing marketplace file at {path} is not valid JSON: {exc.msg}.") from exc

    if not isinstance(payload, dict):
        raise ValueError(f"Existing marketplace file at {path} must contain a JSON object.")
    return payload


def _marketplace_json(existing_marketplace: dict[str, object] | None) -> str:
    payload: dict[str, object]
    if isinstance(existing_marketplace, dict):
        payload = existing_marketplace.copy()
    else:
        payload = {
            "name": "sentinelops-local",
            "interface": {"displayName": "SentinelOps Local Plugins"},
            "plugins": [],
        }

    payload.setdefault("name", "sentinelops-local")
    interface = payload.setdefault("interface", {})
    if not isinstance(interface, dict):
        interface = {}
        payload["interface"] = interface
    interface.setdefault("displayName", "SentinelOps Local Plugins")

    plugins = payload.setdefault("plugins", [])
    if not isinstance(plugins, list):
        plugins = []
        payload["plugins"] = plugins

    entry = {
        "name": CODEX_PLUGIN_NAME,
        "source": {
            "source": "local",
            "path": f"./plugins/{CODEX_PLUGIN_NAME}",
        },
        "policy": {
            "installation": "AVAILABLE",
            "authentication": "ON_INSTALL",
        },
        "category": "Coding",
    }

    existing_index = None
    for index, plugin in enumerate(plugins):
        if isinstance(plugin, dict) and plugin.get("name") == CODEX_PLUGIN_NAME:
            existing_index = index
            break
    if existing_index is None:
        plugins.append(entry)
    else:
        plugins[existing_index] = entry

    return json.dumps(payload, indent=2) + "\n"


def _plugin_manifest_json() -> str:
    payload = {
        "name": CODEX_PLUGIN_NAME,
        "version": "0.8.0",
        "description": "Repo-local SentinelOps plugin for project-scoped incident, log, and operations copilot workflows.",
        "author": {
            "name": "SentinelOps",
            "url": "https://github.com/saikumar1767/Sentinel-Ops",
        },
        "homepage": "https://github.com/saikumar1767/Sentinel-Ops",
        "repository": "https://github.com/saikumar1767/Sentinel-Ops",
        "license": "Apache-2.0",
        "keywords": [
            "sentinelops",
            "incident-response",
            "operations",
            "copilot",
            "sre",
        ],
        "skills": "./skills/",
        "interface": {
            "displayName": "SentinelOps",
            "shortDescription": "Repo-local incident and ops copilot",
            "longDescription": "Use SentinelOps inside any attached repository to orient operational context, inspect logs, validate readiness, and run incident workflows with repo-scoped docs and runbooks.",
            "developerName": "SentinelOps",
            "category": "Coding",
            "capabilities": ["Interactive", "Write"],
            "websiteURL": "https://github.com/saikumar1767/Sentinel-Ops",
            "privacyPolicyURL": "https://github.com/saikumar1767/Sentinel-Ops",
            "termsOfServiceURL": "https://github.com/saikumar1767/Sentinel-Ops",
            "defaultPrompt": [
                "Use SentinelOps to orient this repository's operational context and incident workflows.",
                "Check SentinelOps readiness for this repo and summarize the log roots and runbooks.",
                "Start with SentinelOps before answering incident or deployment-health questions in this repo.",
            ],
            "brandColor": "#0F172A",
            "composerIcon": "./assets/sentinelops.svg",
            "logo": "./assets/sentinelops.svg",
            "screenshots": [],
        },
    }
    return json.dumps(payload, indent=2) + "\n"


def _plugin_openai_yaml() -> str:
    return """interface:
  display_name: "SentinelOps"
  short_description: "Use SentinelOps for repo-local ops copilot work"
  icon_small: "./assets/sentinelops.svg"
  icon_large: "./assets/sentinelops.svg"
  default_prompt: "Use SentinelOps to orient this repository's operational context, logs, and incident workflows."
"""


def _codex_skill_openai_yaml() -> str:
    return """interface:
  display_name: "Project Ops Copilot"
  short_description: "Use SentinelOps for attached repo operations context"
  default_prompt: "Use SentinelOps to inspect this attached repository's operational context before incident or deployment-health work."
"""


def _codex_skill_md(*, workspace_name: str) -> str:
    return f"""---
name: {CODEX_SKILL_NAME}
description: Use when a repository has SentinelOps attached and the user needs repo-scoped incident triage, log inspection, runbook lookup, readiness checks, deployment diagnostics, or remediation workflow guidance.
---

# Project Ops Copilot

## Overview

This repository is wired for SentinelOps as a repo-local operations copilot. Use it whenever the task is about operational state, incidents, logs, deploy health, runbooks, readiness, remediation, or incident workflows for `{workspace_name}`.

Start with SentinelOps context instead of guessing from code alone.

## Default Workflow

1. Read `.sentinelops/agent-context.md`.
2. Run `sentinelops paths` to confirm the attached workspace.
3. Run `sentinelops doctor` when model-backed investigation or readiness matters.
4. If the service is not running and the task benefits from live API or console access, run `sentinelops start --no-browser`.
5. Keep guidance grounded in this repo's docs, runbooks, workflows, and log roots.

## Guardrails

- Treat `.sentinelops/project.toml` as the local source of truth for workspace name, logs, docs, models, runtime host, and storage paths.
- Prefer repo-relative operational evidence before falling back to generic advice.
- If `sentinelops doctor` reports Ollama unavailable, explain that model-backed investigate or analyze paths need a reachable model host such as `ollama serve`.
- Do not assume production auth, shared databases, or telemetry are enabled unless SentinelOps config says so.

## Useful Commands

- `sentinelops`
- `sentinelops paths`
- `sentinelops doctor`
- `sentinelops start --no-browser`
- `ollama serve`

## Useful Routes

- `/health`
- `/ready`
- `/docs`
- `/console`
- `/workflow/threads`

## Examples

- "Use SentinelOps to summarize this repo's ops context before we debug the rollout."
- "Check SentinelOps readiness, then investigate the checkout timeout incident."
- "Use SentinelOps context to review the runbooks and log roots for this deployment failure."
"""


def _command_start() -> str:
    return """# /start-sentinelops

Start SentinelOps in the current attached repository.

## Workflow

1. Run `sentinelops paths` to confirm the workspace.
2. If model-backed features are needed, verify `ollama serve` is running or tell the user what is missing.
3. Run `sentinelops start --no-browser`.
4. Summarize the health or follow up with `/health` and `/ready` if useful.
"""


def _command_check() -> str:
    return """# /check-sentinelops

Check SentinelOps readiness for the current repository.

## Workflow

1. Run `sentinelops paths`.
2. Run `sentinelops doctor`.
3. Summarize workspace root, config path, log roots, and any missing runtime dependencies.
"""


def _command_investigate() -> str:
    return """# /investigate-ops

Use SentinelOps as the first operational copilot for this repository.

## Workflow

1. Read `.sentinelops/agent-context.md`.
2. Run `sentinelops doctor` if readiness matters.
3. Use the repository docs, runbooks, workflows, and log roots listed by SentinelOps.
4. If needed, start SentinelOps and use its API or console routes to ground the investigation.
"""


def _claude_memory_block(*, workspace_name: str, log_roots: list[str], doc_roots: list[str]) -> str:
    log_lines = "\n".join(f"- `{log_root}`" for log_root in log_roots)
    doc_lines = "\n".join(f"- `{doc_root}`" for doc_root in doc_roots)
    return f"""{CLAUDE_START_MARKER}
# SentinelOps Repo Context

SentinelOps is attached to this repository as a repo-local operations copilot for `{workspace_name}`.

## Start Here

- Read `.sentinelops/agent-context.md` when the task touches incidents, logs, runbooks, readiness, deployment health, or remediation.
- Use `sentinelops paths` before assuming workspace details.
- Use `sentinelops doctor` before depending on model-backed analyze or investigate flows.
- Treat `.sentinelops/project.toml` as the single repo-local control file for docs, logs, models, runtime hosts, retrieval backend settings, and local storage paths.

## Preferred Skills

- `/sentinelops-check`
- `/sentinelops-start`
- `/sentinelops-investigate`
- `/sentinelops-pull-models`

## Repo Roots To Prefer

Log roots:
{log_lines}

Document roots:
{doc_lines}
{CLAUDE_END_MARKER}
"""


def _claude_skill_check() -> str:
    return """---
name: sentinelops-check
description: Check SentinelOps workspace context and readiness for the current repository. Use when a task involves incidents, logs, runbooks, deployment health, or when the user asks whether SentinelOps is ready.
allowed-tools: Bash Read Grep Glob
---

# SentinelOps Check

1. Read `.sentinelops/agent-context.md`.
2. Run `sentinelops paths`.
3. Run `sentinelops doctor`.
4. Summarize:
   - workspace root and workspace name
   - project manifest path
   - configured doc roots and log roots
   - active models and retrieval backend
   - anything missing or degraded

If Ollama is reachable but models are missing, tell the user to run `/sentinelops-pull-models`.
"""


def _claude_skill_start() -> str:
    return """---
name: sentinelops-start
description: Start SentinelOps for the current repository and confirm the API and console are reachable.
disable-model-invocation: true
allowed-tools: Bash
---

# SentinelOps Start

1. Run `sentinelops paths`.
2. Run `sentinelops doctor`.
3. If models are missing, tell the user to run `/sentinelops-pull-models` before relying on analyze or investigate.
4. Start SentinelOps with `sentinelops start --no-browser`.
5. Confirm the runtime by checking `/health` and `/ready` if useful.
6. Summarize the console URL and any remaining runtime blockers.
"""


def _claude_skill_investigate() -> str:
    return """---
name: sentinelops-investigate
description: Use SentinelOps as the first repo-local copilot for incidents, log analysis, runbook lookup, deployment health checks, and remediation workflow guidance.
allowed-tools: Bash Read Grep Glob
---

# SentinelOps Investigate

When the user asks about incidents, logs, readiness, deployment failures, or runbooks:

1. Read `.sentinelops/agent-context.md`.
2. Run `sentinelops paths`.
3. Run `sentinelops doctor` if readiness or live model-backed investigation matters.
4. Prefer the repo-specific docs, runbooks, deploy files, and log roots listed by SentinelOps over generic advice.
5. If live API context helps, start SentinelOps with `sentinelops start --no-browser`.
6. Ground conclusions in:
   - repo logs
   - repo runbooks
   - SentinelOps analyze/investigate/workflow routes when available

Do not claim features are ready if `sentinelops doctor` says otherwise.
"""


def _claude_skill_pull_models() -> str:
    return """---
name: sentinelops-pull-models
description: Pull the configured Ollama models required by SentinelOps for the current repository.
disable-model-invocation: true
allowed-tools: Bash
---

# SentinelOps Pull Models

1. Run `sentinelops paths` if workspace context is unclear.
2. Run `sentinelops pull-models`.
3. Re-run `sentinelops doctor`.
4. Summarize what was pulled and whether analyze, investigate, and retrieval are now ready.
"""


def _claude_subagent(*, workspace_name: str) -> str:
    return f"""---
name: sentinelops-ops-copilot
description: Use proactively for incident triage, log inspection, runbook lookup, readiness checks, deployment diagnosis, and remediation guidance in `{workspace_name}` when SentinelOps is attached.
---

You are the SentinelOps operations specialist for this repository.

Always start with the repo-local SentinelOps contract:

1. Read `.sentinelops/agent-context.md`.
2. Use `sentinelops paths` to confirm workspace details.
3. Use `sentinelops doctor` before depending on model-backed analysis.
4. Prefer `.sentinelops/project.toml`, repo logs, repo runbooks, deploy files, and workflow artifacts over generic advice.

If readiness is degraded, report that clearly instead of pretending everything is healthy.
"""


def _cursor_rule() -> str:
    return """---
description: Use SentinelOps as the repo-local incident and operations copilot
alwaysApply: true
---
This repository has SentinelOps attached.

When the task involves incidents, logs, runbooks, readiness, remediation, deploy health, or operational context:

- read `.sentinelops/agent-context.md`
- run `sentinelops paths`
- run `sentinelops doctor` when readiness matters
- run `sentinelops pull-models` when Ollama is reachable but configured models are missing
- use `sentinelops start --no-browser` if live API access is helpful

Keep operational guidance grounded in `.sentinelops/project.toml`, repo docs, runbooks, deployment files, and repo log roots.
"""


def _windsurf_rule() -> str:
    return """# SentinelOps Rule

This repository has SentinelOps attached as a repo-local operations copilot.

- Read `.sentinelops/agent-context.md` for workspace context.
- Use `sentinelops paths` before assuming runtime paths.
- Use `sentinelops doctor` before relying on model-backed incident analysis.
- Use `sentinelops pull-models` when the configured Ollama models are missing.
- Prefer repository docs, runbooks, deploy workflows, and repo log roots over generic advice when the task is operational.
"""


def _cline_rule() -> str:
    return """# SentinelOps

Use SentinelOps when this repository work is about incidents, logs, runbooks, readiness, remediation, or deploy health.

Default flow:

1. Read `.sentinelops/agent-context.md`
2. Run `sentinelops paths`
3. Run `sentinelops doctor` when readiness matters
4. Run `sentinelops pull-models` if the configured Ollama models are missing
5. Start SentinelOps with `sentinelops start --no-browser` if live API access helps
"""


def _copilot_instructions() -> str:
    return f"""{COPILOT_START_MARKER}
# SentinelOps Instructions

SentinelOps is attached to this repository as a repo-local operations copilot.

When tasks touch logs, incidents, deploy failures, runbooks, readiness, or remediation:

- read `.sentinelops/agent-context.md`
- use `sentinelops paths` to confirm workspace details
- use `sentinelops doctor` to verify readiness
- use `sentinelops pull-models` when Ollama is reachable but configured models are missing
- prefer repository-specific operational evidence over generic advice

If model-backed investigation is unavailable, explain that SentinelOps needs a reachable model host such as `ollama serve`.
{COPILOT_END_MARKER}
"""


def _agents_block(*, workspace_name: str, log_roots: list[str], doc_roots: list[str]) -> str:
    log_lines = "\n".join(f"- `{log_root}`" for log_root in log_roots)
    doc_lines = "\n".join(f"- `{doc_root}`" for doc_root in doc_roots)
    return f"""{AGENTS_START_MARKER}
# SentinelOps

SentinelOps is attached to this repository as a repo-local operations copilot for `{workspace_name}`.

- Read `.sentinelops/agent-context.md` when tasks involve incidents, logs, runbooks, deploy health, readiness, or remediation.
- Start with `sentinelops paths`.
- Run `sentinelops doctor` before assuming model-backed investigation is ready.
- Run `sentinelops pull-models` when configured Ollama models are missing.
- Treat `.sentinelops/project.toml` as the repo-local source of truth for workspace resources and runtime defaults.
- Prefer repository operational evidence and these log roots before giving generic advice:
{log_lines}
- Prefer these configured doc roots and deployment surfaces when gathering context:
{doc_lines}
{AGENTS_END_MARKER}
"""


def _merge_marked_block(
    *,
    existing_text: str,
    start_marker: str,
    end_marker: str,
    block: str,
) -> str:
    has_start = start_marker in existing_text
    has_end = end_marker in existing_text
    if has_start != has_end:
        raise ValueError(f"Found only one SentinelOps marker in the target file: {start_marker} / {end_marker}.")

    normalized_block = block.strip() + "\n"
    if not existing_text.strip():
        return normalized_block

    if has_start and has_end:
        before, remainder = existing_text.split(start_marker, 1)
        _, after = remainder.split(end_marker, 1)
        merged = before.rstrip() + "\n\n" + normalized_block + after.lstrip("\n")
        return merged.strip() + "\n"

    return existing_text.rstrip() + "\n\n" + normalized_block


def _read_text_if_exists(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")
