# Claude Repo Context

SentinelOps is a plug-and-play incident and operations copilot.

Use this repo context when working here:

- the product is both a standalone app and a repo-local copilot
- the default product path is local-first personal mode, not shared deployment
- the main user flow is `sentinelops attach --agent all` followed by `sentinelops`
- `.sentinelops/project.toml` is the repo-local source of truth for logs, docs, models, runtime host, and storage
- repo-local state lives in `.sentinelops/`
- docs and root agent files must stay in sync with CLI and integration changes

High-signal commands:

- `uv run sentinelops`
- `uv run sentinelops attach --project-root . --agent all`
- `uv run sentinelops doctor`
- `uv run sentinelops paths`
- `uv run pytest -q`

If install, attachment, or version behavior changes, update:

- `README.md`
- `docs/repo-copilot-validation.md`
- `AGENTS.md`
- `.github/copilot-instructions.md`
- `.cursor/rules/`
- `.windsurf/rules/`
- `.clinerules/`
