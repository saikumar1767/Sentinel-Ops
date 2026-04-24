---
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
