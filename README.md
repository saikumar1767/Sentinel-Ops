SentinelOps

SentinelOps is an edge-first incident copilot for log triage, grounded investigations, and approval-aware workflow execution. It combines FastAPI, Ollama, safe local tools, durable workflow checkpoints, shared workflow metadata, and optional OIDC auth so an operator can move from raw evidence to a structured response quickly.

Install
- Windows PowerShell:
  `irm https://raw.githubusercontent.com/saikumar1767/Sentinel-Ops/main/scripts/install_sentinelops.ps1 | iex`
- macOS / Linux:
  `curl -fsSL https://raw.githubusercontent.com/saikumar1767/Sentinel-Ops/main/scripts/install_sentinelops.sh | bash`
- Direct with `uv`:
  `uv tool install --from https://github.com/saikumar1767/Sentinel-Ops/archive/refs/heads/main.zip sentinel-ops`

Use
- Start the standalone workspace:
  `sentinelops`
- Attach SentinelOps to the repo you are currently working in:
  `sentinelops attach`
- Start SentinelOps as that repo's copilot:
  `sentinelops`
- Start without opening browser:
  `sentinelops start --no-browser`
- Validate the attached repo or standalone workspace:
  `sentinelops doctor`
- Show the active workspace and runtime paths:
  `sentinelops paths`

Use SentinelOps in your own repo
1. Open a project repository:
   `cd your-project`
2. Attach SentinelOps once:
   `sentinelops attach`
3. Start the project copilot:
   `sentinelops`
4. Optional: add extra repo log roots:
   `sentinelops attach --overwrite --log-root logs --log-root services/api/logs`

Repo copilot behavior
- SentinelOps creates a repo-local home at `.sentinelops/`
- Running `sentinelops` inside that repo, or any child directory, auto-detects the attached project
- The loader reads the repo's `README`, `docs/`, `runbooks/`, `ops/`, deployment manifests, and GitHub workflow files
- Log tools automatically look in common repo log roots such as `logs/`, `log/`, `data/logs/`, and `var/log/`
- Repo-specific settings live in `.sentinelops/project.toml`

Plug-and-play behavior
- Standalone mode bootstraps `~/.sentinelops`
- Repo mode bootstraps `.sentinelops/` inside the attached project
- Starter config and product data are copied automatically
- Console opens automatically when the API becomes healthy
- Installer paths do not require Git; they install from the public GitHub source archive
- Local profile works with one command; production profile is available with `sentinelops start --profile production`
- Once a repo is attached, `sentinelops` behaves like a project-local copilot instead of a separate demo workspace

Core product surfaces
- Operations console: `/console`
- Console overview: `/console/overview`
- Incident library: `/console/incidents`
- Incident timeline: `/console/timeline`
- Fast analysis: `POST /analyze`
- One-shot investigation: `POST /investigate`
- Workflow investigation: `POST /workflow/investigate`
- Workflow thread history: `GET /workflow/threads`
- Evaluation summary: `/eval/summary`
- Current user: `/me`
- Metrics: `/metrics`

Run from source repo
1. Install dependencies:
   `uv sync`
2. Pull the local models:
   `ollama pull mistral:7b-instruct`
   `ollama pull nomic-embed-text`
3. Start from the repo:
   `uv run sentinelops`
4. Open:
   [http://127.0.0.1:8000/console](http://127.0.0.1:8000/console)

Manual startup
1. Start Ollama:
   `ollama serve`
2. Start the API:
   `uv run sentinelops start --host 127.0.0.1 --port 8000 --reload`
3. Open:
   [http://127.0.0.1:8000/console](http://127.0.0.1:8000/console)

Shared company-style stack
1. Keep Ollama running on the host:
   `ollama serve`
2. Start the shared infra:
   `docker compose up --build sentinelops-postgres sentinelops-keycloak sentinelops-api`
3. Switch auth on with env vars when you are ready:
   `SENTINELOPS_AUTH_MODE=oidc`
   `SENTINELOPS_AUTH_OIDC_ISSUER_URL=http://127.0.0.1:8081/realms/sentinelops`
   `SENTINELOPS_AUTH_OIDC_AUDIENCE=sentinelops-api`

Production-oriented compose profile
1. Use the production config and override file:
   `docker compose -f compose.yaml -f compose.production.yaml up --build sentinelops-api`
2. Supply all required external URLs and secrets:
   `SENTINELOPS_PUBLIC_BASE_URL`
   `SENTINELOPS_METADATA_DATABASE_URL`
   `SENTINELOPS_WORKFLOW_CHECKPOINT_DATABASE_URL`
   `SENTINELOPS_AUTH_OIDC_ISSUER_URL`
   `SENTINELOPS_AUTH_OIDC_AUDIENCE`
   `SENTINELOPS_TELEMETRY_OTLP_ENDPOINT`

Security and config
- `config/sentinelops.toml` is the single checked-in app config for non-secret settings.
- `config/sentinelops.production.toml` is the stricter production profile.
- Secrets should stay in environment variables or secret mounts, not in the TOML file.
- `auth_mode=disabled` keeps the local single-operator experience simple.
- `auth_mode=api_key` and `auth_mode=oidc` enable shared-user access with identity and RBAC.
- `deployment_mode=production` refuses to start unless OIDC, shared databases, OTLP telemetry, and an `https://` public URL are configured.
- `model_license_policy=permissive_only` is the default guardrail for commercially friendlier default model choices.

What the console gives you
- A live operator console for running incident profiles against the real API
- An incident library with request payloads, expected outcomes, and workflow paths
- A saved incident timeline that blends recent runtime incidents with reference incidents
- Evaluation and readiness summaries so the system is inspectable before use

Key architecture decisions
- Ollama runs outside Docker so local GPU access stays simple and memory overhead stays lower.
- Shared workflow metadata can move to PostgreSQL through `SENTINELOPS_METADATA_DATABASE_URL`.
- Workflow checkpoints can also move to PostgreSQL through `SENTINELOPS_WORKFLOW_CHECKPOINT_DATABASE_URL`.
- FastAPI owns the transport layer, OpenAPI contracts, and the console entrypoint.
- LangGraph is used only where durable checkpoints and approval pauses add value.
- Recorded incident profiles are part of the product surface so the app stays reproducible on one machine.

Useful routes
- `GET /health`
- `GET /ready`
- `GET /ready/strict`
- `GET /me`
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
- Commercial and enterprise usage: [docs/commercial-and-enterprise-usage.md](docs/commercial-and-enterprise-usage.md)
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
- `config/` checked-in non-secret app configuration
- `data/runtime/audit/` local fallback workflow audit trail
- `docs/` product, architecture, and communication assets
- `scripts/` local startup and reporting commands

License
- SentinelOps source in this repository is licensed under Apache-2.0: [LICENSE](LICENSE)
