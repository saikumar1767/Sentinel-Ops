# Interview Story

## 30-Second Version

SentinelOps is a plug-and-play incident and operations copilot I built to turn messy log evidence into grounded incident responses. It combines FastAPI, Ollama, safe local tools, retrieval, and approval-aware workflows, and it can now attach directly to any repo so the copilot understands project-specific runbooks, deployment files, and log roots.

## 2-Minute Version

The problem I focused on was incident triage speed and clarity. Teams usually have logs, runbooks, deployment files, and prior incident notes, but the evidence is fragmented and hard to turn into a grounded response quickly. I built SentinelOps as an installable service that can run locally, attach to a repo, retrieve relevant knowledge, and return structured output instead of open-ended text.

There are three main paths. `/analyze` is the fast route for pasted logs. `/investigate` is the one-shot operator path that reads repo-local logs, compares runs, and retrieves supporting knowledge. `/workflow/*` is the durable path with checkpoints, approval pauses, and audit history for more sensitive remediation planning.

One of the key productization steps was making it feel like a real copilot product instead of only a source repo demo. The CLI can now attach SentinelOps to any repo, create `.sentinelops/`, generate repo-local agent/editor integrations, and keep the attached workspace as the source of operational context.

## 10-Minute Deep Dive

### Problem

The core problem is not only summarizing logs. It is building a repeatable path from evidence to action that is:

- grounded in real artifacts
- safe under uncertainty
- easy to inspect
- portable across repos and teams

### Architecture

The API shell is FastAPI. Model calls go through Ollama. Retrieval can blend packaged knowledge with repo-local docs and runbooks. The workflow layer uses LangGraph where checkpointing and approval pauses add real value. On top of that, SentinelOps includes an operator console, incident library, evaluation summary, durable thread history, and generated agent/editor integrations.

### Technical Decisions

1. Installable CLI product, not just a codebase
   The `sentinelops` CLI makes bootstrapping, repo attachment, readiness checks, and startup repeatable.

2. Repo-local context instead of global guesswork
   `.sentinelops/project.toml` and `.sentinelops/agent-context.md` let the copilot understand each attached project's operational footprint.

3. Structured contracts everywhere
   The API returns typed JSON, problem-detail errors, readiness reports, metrics snapshots, and inspectable workflow thread state.

4. Safe workflow design
   Instead of acting autonomously, the workflow pauses before risky remediation and records the result in audit history.

5. Product surfaces are part of the architecture
   The console, incident library, timeline, validations, installers, and generated agent integrations are treated as core product surfaces, not optional polish.

### Tradeoffs

- I did not pretend the repo is magically company-ready just because it is installable. Production still needs real identity, secrets, telemetry, and legal/security review.
- I kept Ollama outside Docker because local GPU simplicity mattered more than squeezing everything into one container.
- I used repo-local generated files instead of inventing a custom control plane because portability and inspectability mattered more than hidden automation.

### What Went Wrong And What Improved

One real lesson was that "feature complete" does not mean "operator ready" and "operator ready" does not mean "plug-and-play inside another repo." After the backend was solid, the product still needed a clearer face: a CLI, repo-local attachment, generated agent/editor instructions, a better README, and a validation story that worked outside my own machine.

### What I Would Do Next In Production

- add stronger background job execution for long-running analysis
- add policy-gated action execution
- expand telemetry and operational ownership
- add more formal workspace and team separation
- deepen governance around retention, PII handling, and model/legal review

## Likely Interviewer Questions

### Why not cloud-first?

Because the core challenge was proving product value and system design on constrained hardware first. The local-first constraint sharpened the product and kept the architecture inspectable.

### Why LangGraph?

Because the workflow benefits from checkpointing, inspectable state, and approval pauses. I avoided heavier orchestration layers until there was a real need.

### How do you know it works?

I used deterministic evaluation summaries, live API checks, an incident library, repo-local attachment flows, and clean-environment validation paths. The goal was not just to build the features but to make them measurable and installable.
