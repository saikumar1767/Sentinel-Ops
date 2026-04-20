# SentinelOps Repository Guide

## What This Repo Is

SentinelOps is an installable incident and operations copilot product. This repository contains:

- the FastAPI app and operator console
- the CLI and repo attachment flow
- the repo-local single-config contract in `.sentinelops/project.toml`
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
  `uv run sentinelops attach --project-root . --agent all`
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

## Change Rules

- If you change CLI, install, repo attachment, or agent integration behavior, update `README.md`, `docs/repo-copilot-validation.md`, and the root agent files.
- Keep the local-first path primary. Shared auth and centralized deployment are optional overlays, not the default repo story.
- If you change the app version, update `app/settings.py`, `pyproject.toml`, `config/*.toml`, `app/schemas.py`, and `uv.lock`.
- If you change production readiness or commercial boundaries, update `docs/commercial-and-enterprise-usage.md`, `SECURITY.md`, and `NOTICE` when needed.
- Treat packaged knowledge markdown under `data/` as product fixtures, not repo narrative docs.
