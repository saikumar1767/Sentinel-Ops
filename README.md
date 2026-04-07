SentinelOps Month 5

What this does
SentinelOps is a local FastAPI incident-investigation system for developer and on-call workflows. It combines safe local evidence gathering, retrieval over team knowledge, and a controlled LangGraph workflow so incidents can be investigated in a repeatable, reviewable way.

Primary API paths
- `POST /analyze`
  Analyze pasted log text and return a grounded structured summary.
- `POST /investigate`
  Run the one-shot tool-assisted investigation flow.
- `POST /workflow/investigate`
  Start the checkpointed investigation workflow.
- `GET /workflow/{thread_id}`
  Inspect the current workflow thread state.
- `GET /workflow/{thread_id}/audit`
  Inspect the approval audit trail for that workflow thread.
- `POST /workflow/{thread_id}/resume`
  Resume a paused workflow with an explicit human decision.
- `POST /workflow/{thread_id}/approve`
  Approve the pending remediation review and continue to completion.
- `POST /workflow/{thread_id}/reject`
  Reject or edit the proposed remediation plan before completion.
- `POST /knowledge/ingest`
  Rebuild the local knowledge index.
- `POST /knowledge/search`
  Search the indexed knowledge base directly.
- `GET /metrics`
  Inspect request, latency, retry, cache-hit, and token usage telemetry.
- `GET /ready/strict`
  Check strict readiness for all configured capabilities, including knowledge ingest and search.
- `GET /eval/summary`
  Return the deterministic local evaluation report, including workflow coverage.

Month 5 product goal
Month 5 keeps the controlled incident workflow from Month 4 and wraps it in a production-minded shell:
- ingest request
- emit request IDs, latency headers, and problem-details errors
- track request volumes, route latency, model retries, cache hits, and token usage
- retry transient Ollama failures with bounded backoff
- cache deterministic local model responses to reduce repeated work
- cache repeated retrieval searches and embedding-heavy knowledge lookups
- optionally instrument FastAPI with OpenTelemetry for local tracing
- keep the existing approval-gated workflow and grounded JSON outputs intact

This is still intentionally a fixed workflow, not an unrestricted autonomous agent.

Current capabilities
- Structured JSON outputs for `/analyze`, `/investigate`, and `/workflow/*`
- Request IDs and per-request latency headers on every response
- Problem-details JSON for validation and runtime-facing HTTP errors
- In-memory `/metrics` endpoint for request and model telemetry
- Bounded Ollama retries with exponential backoff
- Bounded LRU-style TTL caches for Ollama and retrieval paths, surfaced through `/metrics`
- Optional OpenTelemetry FastAPI instrumentation with `console` or `otlp` exporters
- Custom spans around analyze, investigate, retrieval, tool execution, and workflow nodes
- Startup config validation so bad local configuration fails fast
- Safe local investigation tools:
  - `read_log_file(path)`
  - `grep_error_pattern(path, pattern, max_lines)`
  - `compare_two_logs(path_a, path_b)`
  - `load_incident_template(incident_type)`
  - `list_recent_incidents(limit)`
- Local RAG over:
  - runbooks
  - README files
  - incident templates
  - prior incident summaries
  - GitHub issue notes
  - troubleshooting notes
- Metadata-aware retrieval by document type and incident type
- Checkpointed LangGraph workflow threads with SQLite persistence
- Approval interrupts and resume flow for operationally sensitive remediation plans
- Workflow failure persistence so broken runs are inspectable instead of silently disappearing
- Deterministic workflow eval coverage in the same evaluation surface as analyze, investigate, and RAG
- Router/module separation between the FastAPI shell and service logic
- Lean Docker packaging for occasional integration or demo sessions
- Non-root container runtime and GitHub Actions smoke-test wiring
- Live integration test scaffolding for real Ollama and Chroma when explicitly enabled

Architecture
- FastAPI
  API shell and service boundary
- Runtime middleware
  Request logging, latency headers, and normalized error handling
- Startup validation + telemetry wiring
  Fail-fast config checks and optional OpenTelemetry FastAPI instrumentation
- Ollama
  Local model runtime for structured analysis and investigation drafting, with retries and cache
- Chroma or simple store
  Local retrieval backend behind one service interface
- RuntimeMetrics
  Lightweight in-memory counters for request and model usage telemetry
- InvestigationService
  One-shot evidence gathering, retrieval, grounding, and structured output
- WorkflowService + LangGraph
  Checkpointing, thread inspection, approval interrupts, and resume behavior

Workflow lifecycle
1. Start with `POST /workflow/investigate`
2. Receive a `thread_id` and the current checkpointed state
3. If approval is required, the thread pauses with `status=waiting_for_approval`
4. Inspect the paused thread with `GET /workflow/{thread_id}`
5. Continue with one of:
   - `POST /workflow/{thread_id}/approve`
   - `POST /workflow/{thread_id}/reject`
   - `POST /workflow/{thread_id}/resume`
6. Read the final structured report from the completed thread response

Safety posture
- SentinelOps drafts remediation plans and summaries
- SentinelOps does not execute shell commands, SQL, or production changes on your behalf
- Approval gates exist so the workflow can safely evolve toward real operational review patterns without granting unrestricted autonomy

Requirements
- Python 3.11+
- `uv`
- Ollama installed locally
- Docker Desktop only if you want the optional containerized run mode

Setup
1. Open PowerShell in this project folder.
2. Install dependencies:
   `uv sync`
3. Pull the local models you want to use:
   `ollama pull llama3.2`
   `ollama pull embeddinggemma`
4. Optional: copy `.env.example` to `.env` and adjust settings.
   If you want local tracing, enable `SENTINELOPS_TELEMETRY_ENABLED=true` and choose `console` or `otlp`.

How to run
1. Start Ollama:
   `ollama serve`
2. Start Chroma externally:
   `powershell -ExecutionPolicy Bypass -File scripts/start_chroma_wsl.ps1`
   Cold WSL startup can take up to 90 seconds on this machine. If startup fails, inspect `~/.sentinelops/logs/chroma.log` inside WSL.
3. Optional: verify Chroma directly:
   `powershell -ExecutionPolicy Bypass -File scripts/check_chroma_wsl.ps1`
4. Start FastAPI:
   `uv run uvicorn app.main:app --reload`
5. Verify SentinelOps dependency readiness:
   `Invoke-RestMethod http://127.0.0.1:8000/health`
   `Invoke-RestMethod http://127.0.0.1:8000/ready`
   `Invoke-RestMethod http://127.0.0.1:8000/metrics`
6. Open the docs:
   [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

Optional Docker run
1. Keep Ollama and Chroma running outside Docker on the host machine.
2. Build and start the API container:
   `docker compose up --build`
3. The container uses `host.docker.internal` for Ollama and Chroma by default, which matches this laptop-friendly architecture.

Knowledge store backend
The repo includes two local vector-store paths behind one service interface:
- `chroma`
  Default. Runs reliably on this Windows machine by hosting Chroma inside WSL and connecting over HTTP.
- `simple`
  Fallback pure-Python index kept for deterministic tests and as a backup option.

Chroma setup on Windows
1. Install Chroma inside WSL once:
   `powershell -ExecutionPolicy Bypass -File scripts/setup_chroma_wsl.ps1`
2. Start Chroma manually:
   `powershell -ExecutionPolicy Bypass -File scripts/start_chroma_wsl.ps1`
3. Check that Chroma is reachable:
   `powershell -ExecutionPolicy Bypass -File scripts/check_chroma_wsl.ps1`
4. Stop it when needed:
   `powershell -ExecutionPolicy Bypass -File scripts/stop_chroma_wsl.ps1`
5. If startup times out, inspect the WSL log:
   `wsl.exe -d Ubuntu -- bash -lc 'tail -n 50 $HOME/.sentinelops/logs/chroma.log'`

Stable runtime model
- Ollama runs separately from the API
- Chroma runs separately from the API
- FastAPI stays focused on serving requests and orchestration
- Runtime investigation outputs and workflow checkpoints are written under `data/runtime/`

Quick requests
Health check:
`Invoke-RestMethod http://127.0.0.1:8000/health`

Readiness check:
`Invoke-RestMethod http://127.0.0.1:8000/ready`

Strict readiness check:
`Invoke-RestMethod http://127.0.0.1:8000/ready/strict`

Metrics snapshot:
`Invoke-RestMethod http://127.0.0.1:8000/metrics`

Analyze pasted log text:
```powershell
Invoke-RestMethod http://127.0.0.1:8000/analyze `
  -Method POST `
  -ContentType "application/json" `
  -Body '{"log_text":"2026-03-29 09:10:22 ERROR database connection timeout after 30 seconds"}'
```

Investigate with tools plus retrieval:
```powershell
Invoke-RestMethod http://127.0.0.1:8000/investigate `
  -Method POST `
  -ContentType "application/json" `
  -Body '{"prompt":"Investigate this incident.","candidate_log_paths":["data/logs/database-current.log","data/logs/database-previous.log"],"incident_type_hint":"database"}'
```

Start a checkpointed workflow investigation:
```powershell
Invoke-RestMethod http://127.0.0.1:8000/workflow/investigate `
  -Method POST `
  -ContentType "application/json" `
  -Body '{"prompt":"Investigate this incident using the failing run and the previous healthy run.","candidate_log_paths":["data/logs/database-current.log","data/logs/database-previous.log"],"incident_type_hint":"database","require_approval_for_remediation":true}'
```

Inspect the workflow thread:
```powershell
Invoke-RestMethod http://127.0.0.1:8000/workflow/<thread_id>
```

Approve a paused workflow:
```powershell
Invoke-RestMethod http://127.0.0.1:8000/workflow/<thread_id>/approve `
  -Method POST `
  -ContentType "application/json" `
  -Body '{"review_notes":"Approved for the on-call team to execute."}'
```

Reject and replace the remediation plan:
```powershell
Invoke-RestMethod http://127.0.0.1:8000/workflow/<thread_id>/reject `
  -Method POST `
  -ContentType "application/json" `
  -Body '{"reason":"Use a safer reviewed checklist before making runtime changes.","edited_remediation_plan":["Freeze deploys touching the checkout service until the database saturation is verified.","Page the database owner and confirm a safe rollback or failover path before restarting workers."]}'
```

Show the deterministic evaluation summary:
```powershell
Invoke-RestMethod http://127.0.0.1:8000/eval/summary
```

Response shapes
`/analyze` returns:
- `incident_type`
- `severity`
- `summary`
- `suspected_root_cause`
- `recommended_action`
- `retrieved_evidence`
- `retrieval_status`
- `source_citations`
- `top_error_lines`
- `confidence`

`/investigate` returns:
- `incident_type`
- `severity`
- `top_error_lines`
- `suspected_root_cause`
- `next_steps`
- `manager_summary`
- `retrieved_evidence`
- `retrieval_status`
- `source_citations`
- `confidence`

`/workflow/*` thread responses include:
- `thread_id`
- `status`
- `current_stage`
- `current_step`
- `available_actions`
- `approval_required`
- `approval_status`
- `tool_results`
- `retrieved_chunks`
- `remediation_plan`
- `approval_request`
- `final_report`
- `errors`

Workflow error responses use problem-details style JSON and include:
- `type`
- `title`
- `status`
- `detail`
- `instance`
- `code`
- `thread_id` when relevant

Useful settings
- `SENTINELOPS_LOG_LEVEL`
- `SENTINELOPS_STARTUP_VALIDATE_CONFIG`
- `SENTINELOPS_TELEMETRY_ENABLED`
- `SENTINELOPS_TELEMETRY_SERVICE_NAME`
- `SENTINELOPS_TELEMETRY_EXPORTER`
- `SENTINELOPS_TELEMETRY_OTLP_ENDPOINT`
- `SENTINELOPS_ANALYZE_MODEL`
- `SENTINELOPS_INVESTIGATE_MODEL`
- `SENTINELOPS_EMBEDDING_MODEL`
- `SENTINELOPS_OLLAMA_HOST`
- `SENTINELOPS_OLLAMA_MAX_RETRIES`
- `SENTINELOPS_OLLAMA_RETRY_BACKOFF_SECONDS`
- `SENTINELOPS_OLLAMA_CACHE_ENABLED`
- `SENTINELOPS_OLLAMA_CACHE_TTL_SECONDS`
- `SENTINELOPS_ANALYZE_MODEL_COST_PER_1K_TOKENS`
- `SENTINELOPS_INVESTIGATE_MODEL_COST_PER_1K_TOKENS`
- `SENTINELOPS_EMBEDDING_MODEL_COST_PER_1K_TOKENS`
- `SENTINELOPS_ALLOWED_LOG_ROOTS`
- `SENTINELOPS_TOOL_MAX_ITERATIONS`
- `SENTINELOPS_KNOWLEDGE_STORE_BACKEND`
- `SENTINELOPS_KNOWLEDGE_COLLECTION_NAME`
- `SENTINELOPS_KNOWLEDGE_BASE_DIR`
- `SENTINELOPS_KNOWLEDGE_INDEX_PATH`
- `SENTINELOPS_RETRIEVAL_CACHE_ENABLED`
- `SENTINELOPS_RETRIEVAL_CACHE_TTL_SECONDS`
- `SENTINELOPS_CHROMA_PATH`
- `SENTINELOPS_CHROMA_CLIENT_MODE`
- `SENTINELOPS_CHROMA_HOST`
- `SENTINELOPS_CHROMA_PORT`
- `SENTINELOPS_CHROMA_AUTO_START`
- `SENTINELOPS_CHROMA_WSL_DISTRO`
- `SENTINELOPS_CHROMA_WSL_BINARY`
- `SENTINELOPS_CHROMA_WSL_DATA_DIR`

Operational expectations
- `/health` is a minimal liveness endpoint. It only confirms that the API process is up and should be used for process or container supervision.
- `/ready` is the traffic-readiness endpoint. It stays green when core analysis and investigation traffic can still run, even if knowledge-specific features are degraded.
- `/ready/strict` is the full-capability readiness endpoint. Use it for release rehearsal or packaging checks when knowledge ingest and search must also be healthy.
- `/metrics` is a lightweight runtime snapshot. It is intentionally in-memory and resets when the app restarts.
- If `SENTINELOPS_STARTUP_VALIDATE_CONFIG=true`, invalid local config fails fast during app startup instead of surfacing later during requests.
- If `SENTINELOPS_TELEMETRY_ENABLED=true`, FastAPI request tracing is instrumented through OpenTelemetry. `console` works best for lightweight local debugging on this machine.
- `/analyze` and `/investigate` attempt RAG whenever the embedding model and knowledge store are ready. If retrieval is unavailable, they still return `200`, but `retrieval_status` becomes `unavailable`.
- Repeated knowledge queries can be served from the local retrieval cache to reduce repeated embedding and vector-store work.
- `/workflow/*` persists thread state through checkpoints and returns inspectable state even when a workflow fails.
- `/knowledge/search` and `/knowledge/ingest` require the configured embedding model and retrieval backend. If either is unavailable, they return `503` with a dependency-specific message.
- Destructive reindex requires `confirm_reset=true`.
- Approval actions record thread-linked decision history into the workflow audit trail exposed by `GET /workflow/{thread_id}/audit`.
- HTTP validation and runtime-facing failures return `application/problem+json`.

Local data layout
- `data/logs/`
  Sample log files for investigation tools
- `data/incident_templates/`
  Seeded incident checklists
- `data/recent_incidents/`
  Seeded prior incident summaries used as knowledge fixtures
- `data/runtime/recent_incidents/`
  Runtime incident summaries written by live workflow completion
- `data/runtime/workflow/`
  LangGraph checkpoint database for workflow threads
- `data/knowledge/`
  RAG documents
- `data/eval_cases/`
  Analyze eval cases
- `data/tool_eval_cases/`
  Investigation eval cases
- `data/rag_eval_cases/`
  Retrieval eval cases

Evaluation
- Full suite:
  `uv run pytest -q`
- Analyze evals:
  `uv run pytest -q tests/test_eval_smoke.py`
- Investigate evals:
  `uv run pytest -q tests/test_investigate_eval.py`
- Retrieval evals:
  `uv run pytest -q tests/test_rag_eval.py`
- Workflow evals:
  `uv run pytest -q tests/test_workflow_eval.py`
- Workflow API coverage:
  `uv run pytest -q tests/test_workflow_api.py`
- Live Ollama and Chroma integration check:
  `set SENTINELOPS_RUN_LIVE_TESTS=1` then `uv run pytest -q tests/test_live_stack.py`
- Deterministic eval summary report:
  `uv run python scripts/run_eval_summary.py`

Deterministic evaluation coverage
- `18` analyze cases
- `10` one-shot investigation cases
- `10` retrieval cases
- `10` workflow cases
- `48` deterministic eval cases surfaced through `/eval/summary`

Current verification
- `96` tests pass locally via `uv run pytest -q`
- The deterministic evaluation summary now includes workflow metrics alongside analyze, investigate, and RAG metrics
- Workflow failure, pause, approve, reject, and auto-complete paths are all covered in tests
- Month 5 startup validation, retrieval cache, metrics, retry, and problem-detail behavior are covered in dedicated tests
- Month 5 startup validation, retrieval cache, metrics, retry, and problem-detail behavior are covered in dedicated tests
- `docker compose config` validates the packaged container wiring for local demo mode

Project structure
- `app/main.py`
- `app/dependencies.py`
- `app/settings.py`
- `app/ollama_client.py`
- `app/prompts.py`
- `app/services/analyze_service.py`
- `app/services/investigation_service.py`
- `app/services/workflow_service.py`
- `app/workflows/`
- `app/rag/`
- `app/tools/`
- `app/evaluation.py`
- `data/knowledge/`
