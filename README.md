SentinelOps Month 4

What this does
SentinelOps is a local FastAPI incident-investigation system for developer and on-call workflows. It combines safe local evidence gathering, retrieval over team knowledge, and a controlled LangGraph workflow so incidents can be investigated in a repeatable, reviewable way.

Primary API paths
- `POST /analyze`
  Analyze pasted log text and return a grounded structured summary.
- `POST /investigate`
  Run the one-shot tool-assisted investigation flow.
- `POST /workflow/investigate`
  Start the Month 4 checkpointed investigation workflow.
- `GET /workflow/{thread_id}`
  Inspect the current workflow thread state.
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
- `GET /eval/summary`
  Return the deterministic local evaluation report, including workflow coverage.

Month 4 product goal
Month 4 turns SentinelOps from a one-shot RAG helper into a controlled incident workflow:
- ingest request
- classify incident
- gather evidence with safe tools
- retrieve supporting knowledge from Chroma or the simple fallback store
- draft a grounded hypothesis
- draft a remediation plan
- pause for human review when approval is required
- finalize engineer and manager summaries in a stable JSON schema

This is intentionally a fixed workflow, not an unrestricted autonomous agent.

Current capabilities
- Structured JSON outputs for `/analyze`, `/investigate`, and `/workflow/*`
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

Architecture
- FastAPI
  API shell and service boundary
- Ollama
  Local model runtime for structured analysis and investigation drafting
- Chroma or simple store
  Local retrieval backend behind one service interface
- InvestigationService
  One-shot evidence gathering, retrieval, grounding, and structured output
- WorkflowService + LangGraph
  Month 4 orchestration, checkpointing, thread inspection, approval interrupts, and resume behavior

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

Setup
1. Open PowerShell in this project folder.
2. Install dependencies:
   `uv sync`
3. Pull the local models you want to use:
   `ollama pull llama3.2`
   `ollama pull embeddinggemma`
4. Optional: copy `.env.example` to `.env` and adjust settings.

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
6. Open the docs:
   [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

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
- `SENTINELOPS_ANALYZE_MODEL`
- `SENTINELOPS_INVESTIGATE_MODEL`
- `SENTINELOPS_EMBEDDING_MODEL`
- `SENTINELOPS_OLLAMA_HOST`
- `SENTINELOPS_ALLOWED_LOG_ROOTS`
- `SENTINELOPS_TOOL_MAX_ITERATIONS`
- `SENTINELOPS_KNOWLEDGE_STORE_BACKEND`
- `SENTINELOPS_KNOWLEDGE_COLLECTION_NAME`
- `SENTINELOPS_KNOWLEDGE_BASE_DIR`
- `SENTINELOPS_KNOWLEDGE_INDEX_PATH`
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
- `/ready` is the detailed readiness endpoint. It checks configured models, retrieval backend, and endpoint capabilities before declaring the app ready to serve traffic.
- `/analyze` and `/investigate` attempt RAG whenever the embedding model and knowledge store are ready. If retrieval is unavailable, they still return `200`, but `retrieval_status` becomes `unavailable`.
- `/workflow/*` persists thread state through checkpoints and returns inspectable state even when a workflow fails.
- `/knowledge/search` and `/knowledge/ingest` require the configured embedding model and retrieval backend. If either is unavailable, they return `503` with a dependency-specific message.
- Destructive reindex requires `confirm_reset=true`.

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
- Deterministic eval summary report:
  `uv run python scripts/run_eval_summary.py`

Deterministic evaluation coverage
- `18` analyze cases
- `10` one-shot investigation cases
- `10` retrieval cases
- `10` workflow cases
- `48` deterministic eval cases surfaced through `/eval/summary`

Current verification
- `77` tests pass locally via `uv run pytest -q`
- The deterministic evaluation summary now includes workflow metrics alongside analyze, investigate, and RAG metrics
- Workflow failure, pause, approve, reject, and auto-complete paths are all covered in tests

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
