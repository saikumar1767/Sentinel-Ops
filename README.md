SentinelOps Month 3

What this does
SentinelOps is a local FastAPI incident-analysis app with two operational paths and a local retrieval layer:
- `POST /analyze` classifies pasted log text and adds retrieved supporting evidence.
- `POST /investigate` gathers file-based evidence with safe local tools, retrieves relevant knowledge-base chunks, and returns a structured incident report with citations.
- `POST /knowledge/ingest` rebuilds the local knowledge index.
- `POST /knowledge/search` searches the indexed knowledge base directly.

Current capabilities
- Structured JSON outputs for both `/analyze` and `/investigate`
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
- Saved incident summaries in `data/recent_incidents/`

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

Stable Chroma runtime model
- Chroma should be started outside the FastAPI app.
- The recommended final setup is:
  - Ollama running
  - Chroma running in WSL
  - FastAPI running separately
- `SENTINELOPS_CHROMA_HOST=127.0.0.1` is the recommended default on Windows because WSL-hosted Chroma binds reliably on IPv4.
- `SENTINELOPS_CHROMA_AUTO_START=false` is the recommended final setting.
- Auto-start can still be enabled for local convenience, but it is no longer the default or recommended mode.

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

Rebuild the knowledge index:
```powershell
Invoke-RestMethod http://127.0.0.1:8000/knowledge/ingest `
  -Method POST `
  -ContentType "application/json" `
  -Body '{"reset":true,"confirm_reset":true}'
```

Search the knowledge base:
```powershell
Invoke-RestMethod http://127.0.0.1:8000/knowledge/search `
  -Method POST `
  -ContentType "application/json" `
  -Body '{"query":"Why did startup fail with DB timeout?","top_k":4,"incident_type_hint":"database"}'
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
- `/health` is a minimal liveness endpoint. It only confirms that the API process is up and should be used for process/container supervision.
- `/ready` is the detailed readiness endpoint. It checks the configured models, retrieval backend, and endpoint capabilities before declaring the app ready to serve traffic.
- `/health` and `/ready` now intentionally have different payload shapes: `/health` is small and stable, while `/ready` carries dependencies and capabilities.
- `/analyze` and `/investigate` attempt RAG whenever the embedding model and knowledge store are ready. If retrieval is unavailable, they still return `200`, but `retrieval_status` becomes `unavailable`.
- `/knowledge/search` and `/knowledge/ingest` require the configured embedding model and retrieval backend. If either is unavailable, they return `503` with a dependency-specific message.
- destructive reindex now requires `confirm_reset=true`

Local data layout
- `data/logs/` sample log files for investigation tools
- `data/incident_templates/` incident checklists
- `data/recent_incidents/` saved investigation summaries
- `data/knowledge/` RAG documents
- `data/eval_cases/` analyze eval cases
- `data/tool_eval_cases/` investigation eval cases
- `data/rag_eval_cases/` retrieval eval cases

Evaluation
- Full suite:
  `uv run pytest -q`
- Analyze evals:
  `uv run pytest -q tests/test_eval_smoke.py`
- Investigate evals:
  `uv run pytest -q tests/test_investigate_eval.py`
- Retrieval evals:
  `uv run pytest -q tests/test_rag_eval.py`
- Deterministic eval summary report:
  `uv run python scripts/run_eval_summary.py`

Current verification
- `52` tests pass locally.
- The seeded knowledge corpus indexes more than `30` documents.

Project structure
- `app/main.py`
- `app/dependencies.py`
- `app/settings.py`
- `app/ollama_client.py`
- `app/prompts.py`
- `app/services/analyze_service.py`
- `app/services/investigation_service.py`
- `app/rag/`
- `app/tools/`
- `app/evaluation.py`
- `data/knowledge/`
- `data/rag_eval_cases/`
- `tests/test_eval_smoke.py`
- `tests/test_investigate_eval.py`
- `tests/test_rag_eval.py`
