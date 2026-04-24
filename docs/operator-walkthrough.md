# SentinelOps Operator Walkthrough

## Goal

Explain the product in under 5 minutes using the current repo-local and operator-facing flows.

## Before You Start

Choose one of these launch paths:

1. Installed CLI:
   `sentinelops`
2. Source repo:
   `uv run sentinelops`

Keep these tabs ready:

- `/console`
- `/docs`
- `/eval/summary`

If you want to show the repo-local copilot story first, run this once inside a demo repo:

```bash
sentinelops attach --agent all --knowledge-backend chroma
sentinelops pull-models
```

## Suggested Order

### 1. Open with the product framing

Say:

> SentinelOps is a plug-and-play incident and operations copilot. It can run as a standalone operator console, attach directly to a repo, and use logs, runbooks, deployment files, and approval-aware workflows to produce grounded incident responses.

### 2. Show the repo-local shape

Point to:

- `.sentinelops/project.toml`
- `.sentinelops/agent-context.md`
- `.claude/skills/`
- `AGENTS.md`
- generated agent/editor files

Say:

> The new repo-local mode is what makes SentinelOps feel like a real copilot product. I can install it once, attach it to any repo, and it generates the local contract that other tools and agents can read.

### 3. Show the console overview

Point to:

- readiness
- evaluation summary
- launch command
- workspace root when attached

Say:

> The product is built to be inspectable. I can verify readiness, review evaluation coverage, and then run incident profiles against the live API.

### 4. Run the workflow path

Choose `Database Pool Exhaustion Workflow`.

Show:

- incident profile request
- expected outcome
- workflow result
- evidence panel
- approval pause

Approve it and point out:

- final report
- citations
- timeline refresh
- thread history

### 5. Run a fast investigation

Choose `Network DNS Regression Investigation`.

Show:

- one-shot `/investigate`
- grounded citations
- concise summary

### 6. Show resilience

Choose `Service Restart With Missing Log Path`.

Show:

- workflow completion
- tool results panel
- safe failure on the missing log

### 7. Close with proof

Open `/eval/summary` and `docs/repo-copilot-validation.md`.

Say:

> SentinelOps is intentionally practical on constrained hardware, but it now also behaves like a real installable repo copilot. The app, docs, validation flow, and generated integrations are all part of the product surface.
