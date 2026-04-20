<p align="center">
  <img src="docs/assets/sentinelops-mark.svg" width="140" alt="SentinelOps mark" />
</p>

<h1 align="center">SentinelOps</h1>

<p align="center">
  <strong>why chase outages blind when one copilot can trace the path</strong>
</p>

<p align="center">
  <a href="https://github.com/saikumar1767/Sentinel-Ops/stargazers"><img src="https://img.shields.io/github/stars/saikumar1767/Sentinel-Ops?style=flat&color=FACC15" alt="Stars"></a>
  <a href="https://github.com/saikumar1767/Sentinel-Ops/commits/main"><img src="https://img.shields.io/github/last-commit/saikumar1767/Sentinel-Ops?style=flat" alt="Last Commit"></a>
  <a href="NOTICE"><img src="https://img.shields.io/badge/notice-Apache--2.0-0F172A?style=flat" alt="NOTICE"></a>
  <a href="LICENSE"><img src="https://img.shields.io/github/license/saikumar1767/Sentinel-Ops?style=flat&color=38BDF8" alt="License"></a>
</p>

<p align="center">
  <a href="#install">Install</a> &middot;
  <a href="#repo-copilot">Repo Copilot</a> &middot;
  <a href="#agent-integrations">Agent Integrations</a> &middot;
  <a href="#production">Production</a> &middot;
  <a href="#verification">Verification</a> &middot;
  <a href="#docs">Docs</a>
</p>

---

SentinelOps is a plug-and-play incident and operations copilot that can run in three shapes:

- standalone local operator console
- repo-local copilot inside any project
- production-shaped internal service with OIDC, Postgres, telemetry, and workflow audit trails

It combines FastAPI, Ollama, safe local tooling, retrieval, durable workflows, and generated agent/editor integrations so teams can go from raw logs to grounded incident responses without inventing a custom process per repo.

## Before / After

| Before SentinelOps | After SentinelOps |
| --- | --- |
| Logs live in random folders, runbooks are easy to miss, and every agent guesses repo ops context from scratch. | `sentinelops attach --agent all` creates `.sentinelops/`, repo-local agent context, editor rules, a Codex plugin bundle, and a repeatable ops copilot flow. |
| Incident triage depends on pasted snippets and tribal knowledge. | `/analyze`, `/investigate`, and `/workflow/investigate` can use repo logs, runbooks, deployment manifests, and workflow checkpoints. |
| Production readiness is a separate effort from the local demo. | The same app supports local mode, repo-local mode, and a stricter production profile with OIDC, Postgres, and telemetry guardrails. |

## Install

Pick the install path that fits your environment.

| Platform | Command |
| --- | --- |
| Windows PowerShell | `irm https://raw.githubusercontent.com/saikumar1767/Sentinel-Ops/main/scripts/install_sentinelops.ps1 \| iex` |
| macOS / Linux | `curl -fsSL https://raw.githubusercontent.com/saikumar1767/Sentinel-Ops/main/scripts/install_sentinelops.sh \| bash` |
| Direct with `uv` | `uv tool install --from https://github.com/saikumar1767/Sentinel-Ops/archive/refs/heads/main.zip sentinel-ops` |

After install, the CLI is just:

```bash
sentinelops
```

## Repo Copilot

SentinelOps can be installed into someone else's repo the same way a developer would add a coding copilot or repo rule pack.

```bash
cd your-project
sentinelops attach --agent all
sentinelops
```

Recommended follow-up commands:

```bash
sentinelops doctor
sentinelops paths
sentinelops install-agent --agent all --overwrite
```

What repo-local mode does:

- creates `.sentinelops/` inside the attached repo
- writes `.sentinelops/project.toml` and `.sentinelops/agent-context.md`
- adds `.sentinelops/` to the repo `.gitignore`
- scopes runtime state and logs to that repo
- loads the repo `README`, `docs/`, `runbooks/`, `ops/`, deploy files, and `.github/workflows/`
- auto-detects the attached workspace from any child directory

## Agent Integrations

`sentinelops attach --agent all` wires multiple tools at once.

| Agent / Tool | Generated Surface | What it Gives You |
| --- | --- | --- |
| Codex | `.agents/plugins/marketplace.json`, `plugins/sentinelops-copilot/` | Repo-local plugin, skill, commands, and marketplace entry |
| Cursor | `.cursor/rules/sentinelops.mdc` | Always-on repo rule for ops and incident work |
| Windsurf | `.windsurf/rules/sentinelops.md` | Repo-local ops-copilot instruction file |
| Cline | `.clinerules/sentinelops.md` | Repo-local investigation and readiness workflow guidance |
| GitHub Copilot | `.github/copilot-instructions.md` | Merged SentinelOps block for repo-local operational context |
| Cross-agent | `AGENTS.md` | Shared repo guidance that other tools can read directly |

Safety behavior:

- shared files like `AGENTS.md`, `.agents/plugins/marketplace.json`, and `.github/copilot-instructions.md` are merged instead of blindly replaced
- dedicated generated files are preserved unless you re-run with `--overwrite`

## What SentinelOps Reads

Repo-local retrieval and operator flows prioritize real project context:

- top-level `README*`
- `docs/`, `runbooks/`, `ops/`, `deploy/`, `k8s/`, `helm/`
- `.github/workflows/*.yml` and `.yaml`
- `Dockerfile`, `docker-compose*`, `compose*`, `.env.example`, `.env.*.example`
- repo log roots like `logs/`, `log/`, `data/logs/`, and `var/log/`

## Core Product Surfaces

- Operations console: `/console`
- Console overview: `/console/overview`
- Incident library: `/console/incidents`
- Incident timeline: `/console/timeline`
- Fast analysis: `POST /analyze`
- One-shot investigation: `POST /investigate`
- Workflow investigation: `POST /workflow/investigate`
- Workflow thread history: `GET /workflow/threads`
- Current user: `/me`
- Evaluation summary: `/eval/summary`
- Metrics: `/metrics`

## Production

SentinelOps can stay local, but it also has a stricter production profile for shared company rollouts.

```bash
sentinelops start --profile production
```

Production-oriented requirements:

- `auth_mode=oidc`
- `deployment_mode=production`
- shared Postgres metadata and workflow checkpoint stores
- `https://` public base URL
- OTLP telemetry export
- managed secrets

Starter company-style Docker stack:

```bash
docker compose up --build sentinelops-postgres sentinelops-keycloak sentinelops-api
```

Stricter override:

```bash
docker compose -f compose.yaml -f compose.production.yaml up --build sentinelops-api
```

## Run From Source

```bash
uv sync
ollama pull mistral:7b-instruct
ollama pull nomic-embed-text
uv run sentinelops
```

Open:

- [http://127.0.0.1:8000/console](http://127.0.0.1:8000/console)
- [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

## Verification

Local verification:

```bash
uv run pytest -q
uv run pytest -q tests/test_console_surface.py
uv run pytest -q tests/test_runtime_surface.py
uv run pytest -q tests/test_workflow_api.py
uv run python scripts/run_eval_summary.py
uv run python scripts/run_operations_report.py
```

Repo-local acceptance path:

```bash
sentinelops attach --agent all
sentinelops paths
sentinelops doctor
sentinelops start --no-browser
```

Live dependency check:

```bash
set SENTINELOPS_RUN_LIVE_TESTS=1
uv run pytest -q tests/test_live_stack.py
```

## Docs

- Architecture: [docs/architecture.md](docs/architecture.md)
- Repo copilot validation: [docs/repo-copilot-validation.md](docs/repo-copilot-validation.md)
- Commercial and enterprise usage: [docs/commercial-and-enterprise-usage.md](docs/commercial-and-enterprise-usage.md)
- Operator walkthrough: [docs/operator-walkthrough.md](docs/operator-walkthrough.md)
- Incident library: [docs/incident-library.md](docs/incident-library.md)
- Video walkthrough: [docs/video-walkthrough.md](docs/video-walkthrough.md)
- Interview story: [docs/interview-story.md](docs/interview-story.md)
- Resume bullets: [docs/resume-bullets.md](docs/resume-bullets.md)

## Repo Layout

- `app/` API shell, services, workflow orchestration, static console assets, CLI, and agent integrations
- `config/` checked-in non-secret app config for local and production profiles
- `data/incident_library/` packaged incident profiles
- `data/knowledge/` packaged runbooks, notes, and reference docs
- `docs/` architecture, rollout, validation, and communication assets
- `samples/` starter logs and local demo artifacts
- `scripts/` installers, startup helpers, and reporting commands
- `tests/` API, runtime, workflow, and plug-and-play verification coverage

## License

SentinelOps source in this repository is licensed under Apache-2.0.

- License text: [LICENSE](LICENSE)
- Distribution notice: [NOTICE](NOTICE)
- Security guidance: [SECURITY.md](SECURITY.md)

Commercial use still requires review of deployed models, connected data, and third-party services. See [docs/commercial-and-enterprise-usage.md](docs/commercial-and-enterprise-usage.md).
