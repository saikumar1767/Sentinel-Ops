# SentinelOps Repo Rule

This repository builds SentinelOps, a plug-and-play incident and operations copilot.

- Keep repo-local install flow, generated agent/editor integrations, and docs in sync.
- Treat `.sentinelops/project.toml` as the local control contract when changing attach or runtime behavior.
- Keep Claude Code skills, repo memory, and the rest of the generated agent files in sync with the CLI.
- Update README and validation docs when the product story changes.
- Prefer SentinelOps-specific operational context over generic guidance.
- Preserve the current brain contract: deterministic root-cause diagnostics, LangGraph causal analysis, saved incident memory, and local-first runtime hardening.
