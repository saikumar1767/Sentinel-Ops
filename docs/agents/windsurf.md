# Windsurf Setup

This guide installs SentinelOps repo guidance for Windsurf.

## Windows From Scratch

1. Install Git:

```powershell
winget install --id Git.Git -e
```

2. Install `uv`:

```powershell
winget install --id astral-sh.uv -e
```

3. Install Ollama:

```powershell
winget install --id Ollama.Ollama -e
```

4. Install Windsurf from:

```text
https://windsurf.com/windsurf/download
```

5. Open a second terminal and keep Ollama running:

```powershell
ollama serve
```

6. Install SentinelOps:

```powershell
uv tool install --from https://github.com/saikumar1767/Sentinel-Ops/archive/refs/heads/main.zip sentinel-ops --force
```

7. Attach SentinelOps in your project:

```powershell
cd C:\path\to\your-project
git init
sentinelops attach --agent windsurf --knowledge-backend chroma
sentinelops pull-models
sentinelops doctor
sentinelops start --no-browser
```

Skip `git init` if the project is already a Git repo.

8. Open the same folder in Windsurf.

## macOS / Linux From Scratch

```bash
# Install Git, uv, Ollama, and Windsurf first.
uv tool install --from https://github.com/saikumar1767/Sentinel-Ops/archive/refs/heads/main.zip sentinel-ops --force

# In another terminal:
ollama serve

# In your project:
cd /path/to/your-project
git init
sentinelops attach --agent windsurf --knowledge-backend chroma
sentinelops pull-models
sentinelops doctor
sentinelops start --no-browser
```

## Expected Files

```text
.sentinelops/project.toml
.sentinelops/agent-context.md
.windsurf/rules/sentinelops.md
```

## How Windsurf Knows To Use SentinelOps

Windsurf reads the generated `.windsurf/rules/sentinelops.md` rule.

When the task involves incidents, logs, deploy health, readiness, runbooks, or remediation, Windsurf should use SentinelOps as the repo-local operations source of truth.

## Company Model Endpoint

```bash
sentinelops attach --agent windsurf --knowledge-backend chroma --ollama-host https://models.example.internal
```

