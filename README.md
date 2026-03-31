SentinelOps Week 1

What this does
A local FastAPI app that accepts pasted log text and uses Ollama to return structured JSON.

Requirements
- Python 3.11+
- uv installed and available in PowerShell
- Ollama installed on Windows

First-time setup
1. Open PowerShell in this project folder.
2. Install Python dependencies:
   uv sync
3. Pull the Week 1 model:
   ollama pull llama3.2

How to start the app
1. Make sure Ollama is running.
   - Open the Ollama app from the Start menu, or
   - Run: ollama serve
2. In the project folder, start the FastAPI server:
   uv run uvicorn app.main:app --reload
3. Open the API in your browser:
   http://127.0.0.1:8000/docs

Quick test
Health check:
Invoke-RestMethod http://127.0.0.1:8000/health

Analyze a log:
Invoke-RestMethod http://127.0.0.1:8000/analyze `
  -Method POST `
  -ContentType "application/json" `
  -Body '{"log_text":"2026-03-29 09:10:22 ERROR database connection timeout after 30 seconds"}'

Week 3 evaluation loop
1. Start Ollama if it is not already running.
2. Start the API in one PowerShell window:
   uv run uvicorn app.main:app --reload
3. Run the HTTP evaluation script in another PowerShell window:
   uv run python scripts/run_eval.py
4. Run the parametrized pytest suite:
   uv run pytest -q

Evaluation data
- data/eval_cases/ contains the JSON eval cases
- scripts/run_eval.py calls the local /analyze endpoint with Requests
- tests/test_eval_smoke.py runs the repeatable pytest checks across all cases

Endpoints
GET /health
POST /analyze

Sample request
{"log_text":"2026-03-29 09:10:22 ERROR database connection timeout after 30 seconds"}

Project structure
- app/main.py
- app/schemas.py
- app/ollama_client.py
- app/evaluation.py
- data/eval_cases/
- scripts/run_eval.py
- tests/test_eval_smoke.py
- samples/sample1.log
- samples/sample2.log
- samples/sample3.log
- samples/sample4.log
- samples/sample5.log
- pyproject.toml
- uv.lock
