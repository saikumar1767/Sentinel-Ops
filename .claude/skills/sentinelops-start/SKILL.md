---
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
