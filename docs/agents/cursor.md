# Cursor Setup

This guide installs SentinelOps repo guidance for Cursor.

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

4. Install Cursor from:

```text
https://cursor.com/download
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
sentinelops attach --agent cursor --knowledge-backend chroma
sentinelops pull-models
sentinelops doctor
sentinelops start --no-browser
```

Skip `git init` if the project is already a Git repo.

8. Open the same folder in Cursor.

## macOS / Linux From Scratch

```bash
# Install Git, uv, Ollama, and Cursor first.
uv tool install --from https://github.com/saikumar1767/Sentinel-Ops/archive/refs/heads/main.zip sentinel-ops --force

# In another terminal:
ollama serve

# In your project:
cd /path/to/your-project
git init
sentinelops attach --agent cursor --knowledge-backend chroma
sentinelops pull-models
sentinelops doctor
sentinelops start --no-browser
```

## Expected Files

```text
.sentinelops/project.toml
.sentinelops/agent-context.md
AGENTS.md
.cursor/rules/sentinelops.mdc
```

## How Cursor Knows To Use SentinelOps

Cursor reads the generated `.cursor/rules/sentinelops.mdc` rule.

SentinelOps also merges an `AGENTS.md` block as shared repo guidance for tools that use that convention.

When the task involves logs, incidents, deploy failures, readiness, runbooks, or remediation, Cursor should prefer SentinelOps context and commands.

## Company Model Endpoint

```bash
sentinelops attach --agent cursor --knowledge-backend chroma --ollama-host https://models.example.internal
```

