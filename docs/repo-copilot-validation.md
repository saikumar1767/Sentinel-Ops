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

When validating from Docker against Ollama on the host machine, use:

```bash
sentinelops attach --agent all --knowledge-backend chroma --ollama-host http://host.docker.internal:11434
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
- container runs can stamp the correct Ollama endpoint with `--ollama-host`
- readiness clearly explains whether Ollama and retrieval are ready

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

## Built-in Strict Validation Script

The repository now includes a repeatable handoff check:

```bash
uv run python scripts/run_repo_live_check.py --pull-models
```

Docker/container equivalent:

```bash
python scripts/run_repo_live_check.py --use-installed-cli --pull-models --ollama-host http://host.docker.internal:11434
```

Before a Docker validation can be trusted, confirm the container can reach both PyPI and the host Ollama service:

```bash
docker run --rm python:3.11-slim python -c "import urllib.request; print(urllib.request.urlopen('https://pypi.org/simple/uv/', timeout=10).status)"
docker run --rm --add-host=host.docker.internal:host-gateway python:3.11-slim python -c "import urllib.request; print(urllib.request.urlopen('http://host.docker.internal:11434/api/tags', timeout=10).status)"
```

If either command fails, fix Docker Desktop networking or expose Ollama on a host interface before judging SentinelOps.

What it does:

- creates a temporary dummy repo with docs, runbooks, deploy files, and log scenarios
- attaches SentinelOps with generated Claude and other agent files
- pulls the configured Ollama models when asked
- starts the app
- exercises health, readiness, knowledge ingest, analyze, investigate, workflow approval, audit, and thread listing
- asserts that repo-local runbooks are actually used as evidence

## Gold-Standard Expectations

- shared generated files are merged, not blindly replaced
- dedicated generated files are only replaced with `--overwrite`
- `.sentinelops/project.toml` is sufficient to understand what SentinelOps will read and where it will store runtime state
- health and readiness surfaces explain missing dependencies clearly
- `sentinelops pull-models` removes the need to remember manual model pull commands
- Claude Code users get repo-local skills and memory files automatically when the repo is attached
- the app works both as a standalone product and as a repo-local copilot
- production requirements remain explicit instead of being hidden behind a fake "enterprise-ready" claim
