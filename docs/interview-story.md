# Interview Story

## 30-second version

SentinelOps is a local-first incident copilot I built to turn messy log evidence into grounded incident responses. It combines FastAPI, Ollama, Chroma, and LangGraph so it can handle fast analysis, deeper investigations, and approval-aware workflows while still running reliably on a constrained laptop.

## 2-minute version

The problem I focused on was incident triage speed and clarity. Teams usually have logs, runbooks, and prior incident notes, but the evidence is fragmented and hard to turn into a grounded response quickly. I built SentinelOps as a local-first service that accepts logs, retrieves relevant knowledge, and returns structured output instead of open-ended text.

There are three main paths. `/analyze` is the fast single-shot route for pasted logs. `/investigate` is the one-shot operator path that reads local logs, compares runs, and retrieves supporting knowledge. `/workflow/*` is the durable path with checkpoints, approval pauses, and audit history for more sensitive remediation planning.

One of the main design decisions was staying practical on constrained hardware. Ollama runs outside Docker, Chroma stays local, and the incident library keeps key flows reproducible. That let me focus on product quality, evaluations, and operator experience instead of premature infrastructure complexity.

## 10-minute deep dive

### Problem

The core problem is not only summarizing logs. It is building a repeatable path from evidence to action that is:
- grounded in real artifacts
- safe under uncertainty
- easy to inspect

### Architecture

The API shell is FastAPI. Model calls go through Ollama. Retrieval goes through a local Chroma-backed knowledge service. The workflow layer uses LangGraph only where checkpointing and approval pauses add real value. On top of that, SentinelOps includes an operator console, incident library, evaluation summary, and persistent incident timeline.

### Technical decisions

1. Local-first deployment
   This avoids overloading the machine and keeps the system reproducible.

2. Structured contracts everywhere
   The API returns typed JSON, problem-detail errors, readiness reports, metrics snapshots, and inspectable workflow thread state.

3. Safe workflow design
   Instead of acting autonomously, the workflow pauses before risky remediation and records the result in audit history.

4. Operator-facing product surface
   The console, incident library, timeline, evaluations, and launch scripts are treated as part of the product, not optional polish.

### Tradeoffs

- I did not build full cloud deployment because it would add infrastructure noise without improving the core incident product.
- I removed the half-finished token auth layer because a local operator product with fake login semantics is more confusing than useful.
- I did not add a large frontend framework because clarity, reliability, and inspectability mattered more than UI complexity.

### What went wrong and what improved

One real lesson was that "feature complete" does not mean "operator ready." After the backend was solid, the product still needed a clearer face: a console, incident library, cleaner docs, and a better communication layer. That productization pass made the system much easier to understand and use.

### What I would do next in production

- move auth to real OIDC/JWT
- use managed secrets
- add centralized tracing and logs
- add background jobs for long workflows
- add role-based approvals and multi-user attribution

## Likely interviewer questions

### Why not cloud?

Because the key challenge here was proving product value and system design on constrained hardware. The local-first approach was a deliberate design constraint, not a shortcut.

### Why LangGraph?

Because the workflow benefits from checkpointing, inspectable state, and approval pauses. I avoided agent tooling until there was a real orchestration need.

### How do you know it works?

I used deterministic evaluation summaries, live API checks, an incident library, and a saved incident timeline. The goal was not just to build the features but to make them measurable and inspectable.
