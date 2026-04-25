# SentinelOps Claude Code Context

SentinelOps is an installable, local-first incident and operations copilot.

This repository contains:

- the FastAPI API and operator console
- the CLI and repo attachment flow
- the single repo-local config contract in `.sentinelops/project.toml`
- deterministic root-cause diagnostics and incident-memory indexing
- generated agent and editor integrations
- local and production config profiles
- live validation and rollout docs

## Primary Product Story

The main path is:

1. install `sentinelops`
2. run `sentinelops attach --agent all` inside a repo
3. let `.sentinelops/project.toml` become the repo-local control plane
4. run `sentinelops pull-models`
5. run `sentinelops doctor`
6. run `sentinelops`

Local-first personal mode is the default product. Shared auth and centralized deployment are optional overlays.

## Current Brain Contract

- `/investigate` and completed `/workflow/*` responses include typed `root_cause_diagnostics`.
- The LangGraph workflow runs causal analysis before hypothesis drafting and keeps approval pauses for sensitive remediation.
- Saved incidents include top error lines, next steps, and diagnostics, then become retrieval memory when `incident_memory_auto_index=true`.
- The API shell now enforces bounded request bodies, emits security headers, uses constant-time token checks, and configures SQLite for WAL, foreign keys, and busy timeouts.

## Important Files

- `README.md`
- `docs/architecture.md`
- `docs/repo-copilot-validation.md`
- `docs/commercial-and-enterprise-usage.md`
- `SECURITY.md`

## Important Commands

- `uv sync`
- `uv run sentinelops`
- `uv run sentinelops attach --project-root . --agent all --knowledge-backend chroma`
- `uv run sentinelops attach --project-root . --agent all --knowledge-backend chroma --ollama-host http://host.docker.internal:11434` when running SentinelOps inside Docker against host Ollama
- `uv run sentinelops pull-models`
- `uv run sentinelops doctor`
- `uv run pytest -q`
- `uv run python scripts/run_repo_live_check.py --pull-models`

## Claude Skills In This Repo

- `/sentinelops-check`
- `/sentinelops-start`
- `/sentinelops-investigate`
- `/sentinelops-pull-models`

## Repo Rules

- Keep CLI, bootstrap, runtime, and generated agent integrations aligned.
- Treat `.sentinelops/project.toml` as the single repo-local control contract when changing attach/runtime behavior.
- Keep docs and generated instructions aligned with the root-cause diagnostics and incident-memory contract.
- If install, runtime, validation, or agent integration behavior changes, update README, validation docs, and the root agent files in the same change.
- Keep the local-first story primary. Do not accidentally make shared-enterprise assumptions the default path.
