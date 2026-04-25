---
name: sentinelops-check
description: Check SentinelOps workspace context and readiness for the current repository. Use when a task involves incidents, logs, runbooks, deployment health, or when the user asks whether SentinelOps is ready.
allowed-tools: Bash Read Grep Glob
---

# SentinelOps Check

1. Read `.sentinelops/agent-context.md` if it exists.
2. Run `sentinelops paths`.
3. Run `sentinelops doctor`.
4. Summarize:
   - workspace root and workspace name
   - project manifest path
   - configured doc roots and log roots
   - active models and retrieval backend
   - whether incident-memory indexing is enabled if config output exposes it
   - anything missing or degraded

If Ollama is reachable but models are missing, tell the user to run `/sentinelops-pull-models`.
