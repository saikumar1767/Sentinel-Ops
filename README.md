SentinelOps

SentinelOps is a local-first incident copilot for log triage, grounded investigations, and approval-aware workflow execution. It combines FastAPI, Ollama, Chroma, safe local tools, and durable workflow checkpoints so an operator can move from raw evidence to a structured response quickly.

Core product surfaces
- Operations console: `/console`
- Console overview: `/console/overview`
- Incident library: `/console/incidents`
- Incident timeline: `/console/timeline`
- Fast analysis: `POST /analyze`
- One-shot investigation: `POST /investigate`
- Workflow investigation: `POST /workflow/investigate`
- Evaluation summary: `/eval/summary`
- Metrics: `/metrics`

Run locally
1. Install dependencies:
   `uv sync`
2. Pull the local models:
   `ollama pull llama3.2`
   `ollama pull embeddinggemma`
3. Start everything:
   `powershell -ExecutionPolicy Bypass -File scripts/start_sentinelops.ps1`
4. Open:
   [http://127.0.0.1:8000/console](http://127.0.0.1:8000/console)

Manual startup
1. Start Ollama:
   `ollama serve`
2. Start Chroma:
   `powershell -ExecutionPolicy Bypass -File scripts/start_chroma_wsl.ps1`
3. Start the API:
   `uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload`
4. Open:
   [http://127.0.0.1:8000/console](http://127.0.0.1:8000/console)

What the console gives you
- A live operator console for running incident profiles against the real API
- An incident library with request payloads, expected outcomes, and workflow paths
- A saved incident timeline that blends recent runtime incidents with reference incidents
- Evaluation and readiness summaries so the system is inspectable before use

Key architecture decisions
- Ollama runs outside Docker so local GPU access stays simple and memory overhead stays lower.
- Chroma remains local and lightweight.
- FastAPI owns the transport layer, OpenAPI contracts, and the console entrypoint.
- LangGraph is used only where durable checkpoints and approval pauses add value.
- Recorded incident profiles are part of the product surface so the app stays reproducible on one machine.

Useful routes
- `GET /health`
- `GET /ready`
- `GET /ready/strict`
- `GET /console/overview`
- `GET /console/incidents`
- `GET /console/timeline`
- `GET /docs`
- `GET /eval/summary`
- `GET /metrics`

Example requests

Analyze:
```powershell
Invoke-RestMethod http://127.0.0.1:8000/analyze `
  -Method POST `
  -ContentType "application/json" `
  -Body '{"log_text":"2026-03-31 18:45:09 ERROR readiness probe failed with connection refused on port 8080\n2026-03-31 18:45:14 ERROR missing required environment variable STRIPE_SIGNING_SECRET"}'
```

Investigate:
```powershell
Invoke-RestMethod http://127.0.0.1:8000/investigate `
  -Method POST `
  -ContentType "application/json" `
  -Body '{"prompt":"Investigate this network incident using the failing run and the previous healthy run.","candidate_log_paths":["data/logs/network-current.log","data/logs/network-previous.log"],"incident_type_hint":"network"}'
```

Workflow:
```powershell
Invoke-RestMethod http://127.0.0.1:8000/workflow/investigate `
  -Method POST `
  -ContentType "application/json" `
  -Body '{"thread_id":"ops-database-workflow","prompt":"Investigate this incident using the failing run and the previous healthy run.","candidate_log_paths":["data/logs/database-current.log","data/logs/database-previous.log"],"incident_type_hint":"database","require_approval_for_remediation":true}'
```

Operations proof
- Full test suite:
  `uv run pytest -q`
- Console/API coverage:
  `uv run pytest -q tests/test_console_surface.py`
- Runtime coverage:
  `uv run pytest -q tests/test_runtime_surface.py`
- Workflow coverage:
  `uv run pytest -q tests/test_workflow_api.py`
- Evaluation summary:
  `uv run python scripts/run_eval_summary.py`
- Operations report:
  `uv run python scripts/run_operations_report.py`
- Live Ollama and Chroma check:
  `set SENTINELOPS_RUN_LIVE_TESTS=1`
  `uv run pytest -q tests/test_live_stack.py`

Supporting docs
- Architecture: [docs/architecture.md](docs/architecture.md)
- Operator walkthrough: [docs/operator-walkthrough.md](docs/operator-walkthrough.md)
- Incident library notes: [docs/incident-library.md](docs/incident-library.md)
- Video walkthrough: [docs/video-walkthrough.md](docs/video-walkthrough.md)
- Resume bullets: [docs/resume-bullets.md](docs/resume-bullets.md)
- Interview story: [docs/interview-story.md](docs/interview-story.md)

Project layout
- `app/` API, services, workflows, static console assets
- `data/incident_library/` packaged incident profiles
- `data/reference_incidents/` reference incident history
- `data/runtime/recent_incidents/` runtime incident captures
- `data/runtime/workflow/` workflow checkpoints
- `data/runtime/audit/` workflow audit trail
- `docs/` product, architecture, and communication assets
- `scripts/` local startup and reporting commands
