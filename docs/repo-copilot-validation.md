# Repo Copilot Validation

## Goal

Prove that SentinelOps behaves like a real plug-and-play repo copilot, not just a source repository that works only for the author.

## Acceptance Checklist

The repo-local experience is acceptable only if all of these are true:

1. A user can install `sentinelops` without cloning this repo.
2. A user can run `sentinelops attach --agent all` inside a fresh repo.
3. SentinelOps creates `.sentinelops/`, repo agent context, Claude skills, and generated agent/editor files.
4. `.sentinelops/project.toml` contains the repo-local control contract for docs, logs, models, Ollama, retrieval backend, and storage.
5. `sentinelops paths` reports the attached workspace correctly.
6. `sentinelops doctor` reports readiness clearly.
7. `sentinelops pull-models` can bootstrap the configured Ollama models.
8. `sentinelops start --no-browser` boots the API and console successfully.
9. Health, readiness, docs, analyze, investigate, workflow, and thread-history routes can be exercised against a realistic dummy repo scenario.
10. `/investigate` and completed `/workflow/*` responses include `root_cause_diagnostics` with cited signals, a timeline, evidence strength, and missing-evidence notes.
11. Completed investigations are saved with top error lines, next steps, and diagnostics, then indexed into the active knowledge backend when `incident_memory_auto_index=true`.

## Golden Validation Flow

### 1. Install SentinelOps from GitHub

Windows PowerShell:

```powershell
irm https://raw.githubusercontent.com/saikumar1767/Sentinel-Ops/main/scripts/install_sentinelops.ps1 | iex
```

macOS / Linux:

```bash
curl -fsSL https://raw.githubusercontent.com/saikumar1767/Sentinel-Ops/main/scripts/install_sentinelops.sh | bash
```

### 2. Create a dummy project

The dummy repo should contain:

- a `.git/` directory or another supported repo marker
- a `README.md`
- `docs/` or `runbooks/`
- realistic log files under `logs/` or another configured log root
- at least one deploy artifact such as a `Dockerfile`, `compose.yaml`, or `.github/workflows/deploy.yml`

### 3. Attach SentinelOps

```bash
cd dummy-project
sentinelops attach --agent all --knowledge-backend chroma
```

For the default local workflow, `sentinelops attach` uses Ollama at `http://localhost:11434`.

When validating a company-managed model endpoint, use:

```bash
sentinelops attach --agent all --knowledge-backend chroma --ollama-host https://models.example.internal
```

Expected results:

- `.sentinelops/project.toml`
- `.sentinelops/agent-context.md`
- `AGENTS.md`
- `CLAUDE.md`
- `.claude/skills/`
- `.claude/agents/`
- `.agents/plugins/marketplace.json`
- `plugins/sentinelops-copilot/`
- editor rule files for supported agents

Optional repo-specific overrides:

```bash
sentinelops attach \
  --log-root services/api/logs \
  --doc-root docs \
  --doc-root runbooks \
  --knowledge-backend simple
```

### 4. Confirm the workspace contract

```bash
sentinelops paths
sentinelops doctor
sentinelops pull-models
sentinelops doctor
```

Expected results:

- the workspace root points to the dummy repo
- the runtime home is repo-local
- `project_mode` reports `personal`
- the reported doc roots, log roots, models, and knowledge backend match `.sentinelops/project.toml`
- remote model endpoint validations can stamp the correct model URL with `--ollama-host`
- readiness clearly explains whether Ollama and retrieval are ready
- the active config exposes bounded request-body behavior through `max_request_body_bytes`

### 5. Start SentinelOps

```bash
sentinelops start --host 0.0.0.0 --port 8000 --no-browser
```

Expected routes:

- `GET /health`
- `GET /ready`
- `GET /ready/strict`
- `GET /docs`
- `GET /console`
- `GET /workflow/threads`

### 6. Exercise the main API paths

Recommended sequence:

1. `POST /knowledge/ingest`
2. `POST /analyze` with pasted dummy log text
3. `POST /investigate` with candidate log paths in the dummy repo
4. `POST /workflow/investigate` with a thread id and approval requirement
5. `POST /workflow/{thread_id}/approve`
6. `GET /workflow/{thread_id}/audit`
7. `GET /workflow/threads`

Expected investigation and workflow payload checks:

- `root_cause_diagnostics.generated_by` is `deterministic_root_cause_engine`
- diagnostics contain at least one cited signal for the dummy database and authentication scenarios
- before/after log pairs set `regression_detected=true` when new error lines are present
- workflow start can pause for approval and workflow completion preserves diagnostics in `final_report`
- saved incidents contain `top_error_lines`, `next_steps`, and `root_cause_diagnostics`
- a second investigation can retrieve prior incident memory after a saved summary is indexed

## Built-in Strict Validation Script

The repository now includes a repeatable handoff check:

```bash
uv run python scripts/run_repo_live_check.py --pull-models
```

Installed CLI equivalent:

```bash
python scripts/run_repo_live_check.py --use-installed-cli --pull-models
```

Docker is a maintainer and CI smoke-test path, not the normal developer install path. Before a Docker validation can be trusted, confirm the container can reach PyPI:

```bash
docker run --rm python:3.11-slim python -c "import urllib.request; print(urllib.request.urlopen('https://pypi.org/simple/uv/', timeout=10).status)"
```

If the command fails, fix Docker Desktop networking before judging SentinelOps.

What it does:

- creates a temporary dummy repo with docs, runbooks, deploy files, and log scenarios
- attaches SentinelOps with generated Claude and other agent files
- pulls the configured Ollama models when asked
- starts the app
- exercises health, readiness, knowledge ingest, analyze, investigate, workflow approval, audit, and thread listing
- asserts that repo-local runbooks are actually used as evidence
- checks the install path as a real attached project rather than relying on the SentinelOps source tree as the workspace

## Gold-Standard Expectations

- shared generated files are merged, not blindly replaced
- dedicated generated files are only replaced with `--overwrite`
- `.sentinelops/project.toml` is sufficient to understand what SentinelOps will read and where it will store runtime state
- health and readiness surfaces explain missing dependencies clearly
- `sentinelops pull-models` removes the need to remember manual model pull commands
- Claude Code users get repo-local skills and memory files automatically when the repo is attached
- root-cause output is typed, deterministic, cited, and available to both one-shot and LangGraph workflow paths
- the LangGraph workflow performs causal analysis before hypothesis drafting and preserves approval pauses for sensitive remediation
- saved incidents become repo-local retrieval memory through efficient upsert instead of full-index rewrites
- runtime hardening is visible: bounded request bodies, standard security headers, constant-time token checks, and resilient SQLite defaults
- the app works both as a standalone product and as a repo-local copilot
- production requirements remain explicit instead of being hidden behind a fake "enterprise-ready" claim
