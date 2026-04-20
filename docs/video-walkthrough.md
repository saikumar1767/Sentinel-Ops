# SentinelOps Video Walkthrough

## Target Length

3 to 5 minutes

## Recording Goal

A viewer should understand:

- what SentinelOps does
- how repo-local installation works
- why the incident workflow is technically credible
- what proof exists that it works

## Shot List

### Shot 1: Product and problem

Screen:

- top of `README.md`
- repo-local install flow

Narration:

> SentinelOps is a plug-and-play incident and operations copilot. You can run it as a local console or attach it directly to an engineering repo so it understands that project's logs, runbooks, and deploy context.

### Shot 2: Repo-local setup

Screen:

- `sentinelops attach --agent all`
- `.sentinelops/agent-context.md`
- generated `AGENTS.md`

Narration:

> One command bootstraps the repo-local workspace, writes the project contract, and generates agent/editor integrations so the repo can carry its own operational context.

### Shot 3: Readiness and proof

Screen:

- `sentinelops doctor`
- console overview
- evaluation card

Narration:

> The product includes readiness checks, deterministic evaluations, and a compact runtime so it is easy to trust and easy to inspect.

### Shot 4: Workflow path

Screen:

- select `Database Pool Exhaustion Workflow`
- run it
- show approval pause

Narration:

> The workflow gathers safe evidence, retrieves supporting documentation, drafts a remediation plan, and pauses before sensitive action completes.

### Shot 5: Approval and timeline

Screen:

- approve the workflow
- show final report and citations
- show timeline update

Narration:

> That creates both a structured report and a durable incident history for later review.

### Shot 6: One-shot investigation

Screen:

- select `Network DNS Regression Investigation`
- run it

Narration:

> When durable workflow state is not needed, the one-shot investigation route provides a faster grounded answer.

### Shot 7: Close

Screen:

- `/docs`
- `/eval/summary`
- `docs/repo-copilot-validation.md`

Narration:

> SentinelOps now ships as an installable CLI, a repo-local copilot, an operator console, and a production-shaped service. The docs, validations, and generated integrations are all part of the product.
