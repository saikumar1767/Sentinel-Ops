# SentinelOps Repository Guide

## What This Repo Is

SentinelOps is an installable incident and operations copilot product. This repository contains:

- the FastAPI app and operator console
- the CLI and repo attachment flow
- the repo-local single-config contract in `.sentinelops/project.toml`
- deterministic root-cause diagnostics and incident-memory indexing
- generated agent/editor integration scaffolding
- local and production config profiles
- packaged incident and knowledge fixtures
- validation and product docs

## Golden Commands

- Install from source:
  `uv sync`
- Start locally:
  `uv run sentinelops`
- Attach the repo-local copilot:
  `uv run sentinelops attach --project-root . --agent all --knowledge-backend chroma`
- Attach from Docker to host Ollama:
  `uv run sentinelops attach --project-root . --agent all --knowledge-backend chroma --ollama-host http://host.docker.internal:11434`
- Pull the reviewed local model set:
  `uv run sentinelops pull-models`
- Inspect the repo-local control contract:
  `uv run sentinelops paths`
- Verify readiness:
  `uv run sentinelops doctor`
- Run the full suite:
  `uv run pytest -q`

## Repo Areas

- `app/` product code and CLI
- `config/` checked-in non-secret config profiles
- `docs/` product, rollout, and validation docs
- `data/` packaged incident and knowledge fixtures
- `tests/` verification coverage

## Current Brain Contract

- `/investigate` and completed `/workflow/*` responses expose `root_cause_diagnostics`.
- LangGraph workflow includes an `analyze_root_cause` stage before hypothesis drafting.
- Saved incidents include top error lines, next steps, and diagnostics.
- When `incident_memory_auto_index=true`, saved incidents are upserted into the active retrieval backend for future investigations.
- Runtime hardening includes bounded request bodies, security headers, constant-time token checks, and resilient SQLite defaults.

## Change Rules

- If you change CLI, install, repo attachment, or agent integration behavior, update `README.md`, `docs/repo-copilot-validation.md`, and the root agent files.
- Keep the local-first path primary. Shared auth and centralized deployment are optional overlays, not the default repo story.
- If you change the app version, update `app/settings.py`, `pyproject.toml`, `config/*.toml`, `app/schemas.py`, and `uv.lock`.
- If you change production readiness or commercial boundaries, update `docs/commercial-and-enterprise-usage.md`, `SECURITY.md`, and `NOTICE` when needed.
- Treat packaged knowledge markdown under `data/` as product fixtures, not repo narrative docs.
