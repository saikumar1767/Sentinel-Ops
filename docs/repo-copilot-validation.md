# Repo Copilot Validation

## Goal

Prove that SentinelOps behaves like a real plug-and-play repo copilot, not just a source repository that works only for the author.

## Acceptance Checklist

The repo-local experience is acceptable only if all of these are true:

1. A user can install `sentinelops` without cloning this repo.
2. A user can run `sentinelops attach --agent all` inside a fresh repo.
3. SentinelOps creates `.sentinelops/`, repo agent context, and generated agent/editor files.
4. `.sentinelops/project.toml` contains the repo-local control contract for docs, logs, models, runtime host, and storage.
5. `sentinelops paths` reports the attached workspace correctly.
6. `sentinelops doctor` reports readiness clearly.
7. `sentinelops start --no-browser` boots the API and console successfully.
8. Health and docs routes respond.
9. Analysis, investigation, and workflow routes can be exercised against a realistic dummy repo scenario.

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
- at least one deploy or workflow artifact such as a `Dockerfile`, `compose.yaml`, or `.github/workflows/deploy.yml`

### 3. Attach SentinelOps

```bash
cd dummy-project
sentinelops attach --agent all
```

Expected results:

- `.sentinelops/project.toml`
- `.sentinelops/agent-context.md`
- `AGENTS.md`
- `.agents/plugins/marketplace.json`
- `plugins/sentinelops-copilot/`
- editor rule files for supported agents

Optional repo-specific overrides:

```bash
sentinelops attach --log-root services/api/logs --doc-root docs --doc-root runbooks
```

### 4. Confirm the workspace contract

```bash
sentinelops paths
sentinelops doctor
```

Expected results:

- the workspace root points to the dummy repo
- the runtime home is repo-local
- `project_mode` reports `personal`
- the reported doc roots and log roots match `.sentinelops/project.toml`
- readiness clearly explains whether the model host is reachable

### 5. Start SentinelOps

```bash
sentinelops start --host 0.0.0.0 --port 8000 --no-browser
```

Expected routes:

- `GET /health`
- `GET /ready`
- `GET /docs`
- `GET /console`
- `GET /workflow/threads`

### 6. Exercise the main API paths

Recommended sequence:

1. `POST /analyze` with pasted dummy log text
2. `POST /investigate` with candidate log paths in the dummy repo
3. `POST /workflow/investigate` with a thread id and approval requirement
4. `GET /workflow/threads` to confirm durable thread metadata is visible

## Gold-Standard Expectations

- shared generated files are merged, not blindly replaced
- dedicated generated files are only replaced with `--overwrite`
- `.sentinelops/project.toml` is sufficient to understand what SentinelOps will read and where it will store runtime state
- health and readiness surfaces explain missing dependencies clearly
- the app works both as a standalone product and as a repo-local copilot
- production requirements remain explicit instead of being hidden behind a fake "enterprise-ready" claim
