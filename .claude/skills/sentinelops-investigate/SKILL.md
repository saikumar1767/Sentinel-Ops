---
name: sentinelops-investigate
description: Use SentinelOps as the first repo-local copilot for incidents, log analysis, runbook lookup, deployment health checks, and remediation workflow guidance.
allowed-tools: Bash Read Grep Glob
---

# SentinelOps Investigate

When the user asks about incidents, logs, readiness, deployment failures, or runbooks:

1. Read `.sentinelops/agent-context.md` if it exists.
2. Run `sentinelops paths`.
3. Run `sentinelops doctor` if readiness or live model-backed investigation matters.
4. Prefer the repo-specific docs, runbooks, deploy files, and log roots listed by SentinelOps over generic advice.
5. If live API context helps, start SentinelOps with `sentinelops start --no-browser`.
6. Ground conclusions in:
   - repo logs
   - repo runbooks
   - SentinelOps analyze, investigate, knowledge, and workflow routes when available
   - `root_cause_diagnostics` when the API returns it
   - saved incident memory when a similar prior incident exists

Do not claim features are ready if `sentinelops doctor` says otherwise.
