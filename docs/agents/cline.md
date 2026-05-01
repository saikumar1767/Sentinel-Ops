# Cline Setup

This guide installs SentinelOps repo guidance for Cline.

Cline can run in VS Code and compatible editors. The SentinelOps integration writes a `.clinerules/` rule file.

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

4. Install Visual Studio Code:

```powershell
winget install --id Microsoft.VisualStudioCode -e
```

5. Install Cline in VS Code:

```powershell
code --install-extension saoudrizwan.claude-dev
```

6. Open a second terminal and keep Ollama running:

```powershell
ollama serve
```

7. Install SentinelOps:

```powershell
uv tool install --from https://github.com/saikumar1767/Sentinel-Ops/archive/refs/heads/main.zip sentinel-ops --force
```

8. Attach SentinelOps in your project:

```powershell
cd C:\path\to\your-project
git init
sentinelops attach --agent cline --knowledge-backend chroma
sentinelops pull-models
sentinelops doctor
sentinelops start --no-browser
code .
```

Skip `git init` if the project is already a Git repo.

## macOS / Linux From Scratch

```bash
# Install Git, uv, Ollama, VS Code, and Cline first.
code --install-extension saoudrizwan.claude-dev
uv tool install --from https://github.com/saikumar1767/Sentinel-Ops/archive/refs/heads/main.zip sentinel-ops --force

# In another terminal:
ollama serve

# In your project:
cd /path/to/your-project
git init
sentinelops attach --agent cline --knowledge-backend chroma
sentinelops pull-models
sentinelops doctor
sentinelops start --no-browser
code .
```

## Expected Files

```text
.sentinelops/project.toml
.sentinelops/agent-context.md
AGENTS.md
.clinerules/sentinelops.md
```

## How Cline Knows To Use SentinelOps

Cline reads the generated `.clinerules/sentinelops.md` rule.

SentinelOps also merges an `AGENTS.md` block as shared repo guidance for tools that use that convention.

When the task touches logs, incidents, readiness, deployment failures, runbooks, or remediation, Cline should use SentinelOps commands and local API routes.

## Company Model Endpoint

```bash
sentinelops attach --agent cline --knowledge-backend chroma --ollama-host https://models.example.internal
```

