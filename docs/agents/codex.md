# Codex CLI Setup

This guide installs SentinelOps as repo-local operational context for OpenAI Codex CLI.

## Windows PowerShell From Scratch

1. Install Git:

```powershell
winget install --id Git.Git -e
```

2. Install `uv`:

```powershell
winget install --id astral-sh.uv -e
```

3. Install Node.js LTS:

```powershell
winget install --id OpenJS.NodeJS.LTS -e
```

4. Install Ollama:

```powershell
winget install --id Ollama.Ollama -e
```

5. Install Codex CLI:

```powershell
npm install -g @openai/codex
```

6. Configure Codex authentication according to your OpenAI account or company policy.

7. Open a second terminal and keep Ollama running:

```powershell
ollama serve
```

8. Install SentinelOps:

```powershell
uv tool install --from https://github.com/saikumar1767/Sentinel-Ops/archive/refs/heads/main.zip sentinel-ops --force
```

9. Attach SentinelOps in your project:

```powershell
cd C:\path\to\your-project
git init
sentinelops attach --agent codex --knowledge-backend chroma
sentinelops pull-models
sentinelops doctor
sentinelops start --no-browser
codex
```

Skip `git init` if the project is already a Git repo.

## macOS / Linux From Scratch

```bash
# Install Git, Node.js LTS, uv, and Ollama first.
npm install -g @openai/codex
uv tool install --from https://github.com/saikumar1767/Sentinel-Ops/archive/refs/heads/main.zip sentinel-ops --force

# In another terminal:
ollama serve

# In your project:
cd /path/to/your-project
git init
sentinelops attach --agent codex --knowledge-backend chroma
sentinelops pull-models
sentinelops doctor
sentinelops start --no-browser
codex
```

## Expected Files

```text
.sentinelops/project.toml
.sentinelops/agent-context.md
AGENTS.md
.agents/plugins/marketplace.json
plugins/sentinelops-copilot/
```

## How Codex Knows To Use SentinelOps

Codex sees the generated `AGENTS.md` guidance and the repo-local SentinelOps plugin bundle.

For incidents, logs, readiness, deploy health, or runbook questions, Codex should use:

```bash
sentinelops paths
sentinelops doctor
sentinelops start --no-browser
```

## Company Model Endpoint

```bash
sentinelops attach --agent codex --knowledge-backend chroma --ollama-host https://models.example.internal
```

