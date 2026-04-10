# SentinelOps Operator Walkthrough

## Goal

Explain the product in under 4 minutes using stable operator flows.

## Before you start

1. Run:
   `powershell -ExecutionPolicy Bypass -File scripts/start_sentinelops.ps1`
2. Open:
   `http://127.0.0.1:8000/console`
3. Keep these tabs ready:
   - `/console`
   - `/docs`
   - `/eval/summary`

## Suggested order

### 1. Open with the product framing

Say:

> SentinelOps is a local-first incident copilot that turns logs, runbooks, and safe evidence gathering into grounded incident responses.

### 2. Show the console overview

Point to:
- readiness
- evaluation summary
- one-command launch path

Say:

> The product is built to be inspectable. I can verify readiness, review evaluation coverage, and then run incident profiles against the live API.

### 3. Run the workflow path

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

### 4. Run a fast investigation

Choose `Network DNS Regression Investigation`.

Show:
- one-shot `/investigate`
- grounded citations
- concise summary

### 5. Show resilience

Choose `Service Restart With Missing Log Path`.

Show:
- workflow completion
- tool results panel
- safe failure on the missing log

### 6. Close with proof

Open `/eval/summary`.

Say:

> SentinelOps is intentionally practical on constrained hardware: Ollama and Chroma are local, the app degrades safely, and the evaluation suite keeps the main paths measurable.
