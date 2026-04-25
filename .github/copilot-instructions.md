# SentinelOps Repo Instructions

SentinelOps is both a standalone incident copilot and a repo-local operations copilot.

When working in this repo:

- keep the CLI, repo attachment flow, and generated agent/editor integrations aligned
- keep `.sentinelops/project.toml` treated as the repo-local source of truth for workspace resources
- keep Claude Code skills and `CLAUDE.md` aligned with the repo-local install story
- treat `README.md` and `docs/repo-copilot-validation.md` as first-class product surfaces
- update version references consistently across `app/settings.py`, `pyproject.toml`, `config/*.toml`, `app/schemas.py`, and `uv.lock`
- prefer repo-specific operational context over generic advice when the task touches logs, readiness, workflows, or deploy health
- preserve the current brain contract: deterministic `root_cause_diagnostics`, LangGraph `analyze_root_cause`, saved incident memory, and local-first runtime hardening
