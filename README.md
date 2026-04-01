SentinelOps Month 2

What this does
A local FastAPI app that now supports two separate flows:
- `POST /analyze` keeps the original Month 1 pasted-log summarizer.
- `POST /investigate` runs a controlled Ollama tool loop, gathers local evidence, and returns a structured incident report.

Requirements
- Python 3.11+
- `uv` installed and available in PowerShell
- Ollama installed on Windows

First-time setup
1. Open PowerShell in this project folder.
2. Install dependencies:
   `uv sync`
3. Pull the local model:
   `ollama pull llama3.2`
4. Optional: copy `.env.example` to `.env` and adjust settings.

How to start the app
1. Make sure Ollama is running.
   - Open the Ollama app from the Start menu, or
   - Run `ollama serve`
2. Start FastAPI:
   `uv run uvicorn app.main:app --reload`
3. Open the docs:
   [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

Quick test
Health check:
`Invoke-RestMethod http://127.0.0.1:8000/health`

Analyze a pasted log:
```powershell
Invoke-RestMethod http://127.0.0.1:8000/analyze `
  -Method POST `
  -ContentType "application/json" `
  -Body '{"log_text":"2026-03-29 09:10:22 ERROR database connection timeout after 30 seconds"}'
```

Investigate with tools:
```powershell
Invoke-RestMethod http://127.0.0.1:8000/investigate `
  -Method POST `
  -ContentType "application/json" `
  -Body '{"prompt":"Investigate this incident.","candidate_log_paths":["data/logs/database-current.log","data/logs/database-previous.log"],"incident_type_hint":"database"}'
```

Available local tools in `/investigate`
- `read_log_file(path)`
- `grep_error_pattern(path, pattern, max_lines)`
- `compare_two_logs(path_a, path_b)`
- `load_incident_template(incident_type)`
- `list_recent_incidents(limit)`

Investigation response shape
- `incident_type`
- `severity`
- `top_error_lines`
- `suspected_root_cause`
- `next_steps`
- `manager_summary`
- `evidence_used`
- `confidence`

Configuration
Settings are loaded from environment variables with `pydantic-settings`.

Useful keys:
- `SENTINELOPS_ANALYZE_MODEL`
- `SENTINELOPS_INVESTIGATE_MODEL`
- `SENTINELOPS_OLLAMA_HOST`
- `SENTINELOPS_ALLOWED_LOG_ROOTS`
- `SENTINELOPS_TOOL_MAX_ITERATIONS`

Local data layout
- `data/logs/` holds safe sample logs for tool use
- `data/incident_templates/` holds canned incident checklists
- `data/recent_incidents/` holds saved investigation summaries
- `data/tool_eval_cases/` holds scripted tool-use eval cases

Evaluation
Analyze flow:
1. Start Ollama and the API.
2. Run `uv run python scripts/run_eval.py`
3. Run `uv run pytest -q tests/test_eval_smoke.py`

Investigate flow:
1. Run `uv run pytest -q tests/test_investigate_eval.py`
2. The tool-use evals use FastAPI dependency overrides and a scripted Ollama gateway so the service logic stays deterministic.

Project structure
- `app/main.py`
- `app/dependencies.py`
- `app/settings.py`
- `app/ollama_client.py`
- `app/services/analyze_service.py`
- `app/services/investigation_service.py`
- `app/tools/file_tools.py`
- `app/tools/incident_tools.py`
- `app/tools/tool_registry.py`
- `app/evaluation.py`
- `data/eval_cases/`
- `data/logs/`
- `data/incident_templates/`
- `data/recent_incidents/`
- `data/tool_eval_cases/`
- `tests/test_eval_smoke.py`
- `tests/test_investigate_eval.py`
