# GitHub Copilot Setup

This guide installs SentinelOps repo instructions for GitHub Copilot.

The SentinelOps integration writes `.github/copilot-instructions.md` so Copilot Chat can use repo-local SentinelOps context.

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

5. Install GitHub Copilot extensions in VS Code:

```powershell
code --install-extension GitHub.copilot
code --install-extension GitHub.copilot-chat
```

6. Sign in to GitHub Copilot in VS Code.

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
sentinelops attach --agent copilot --knowledge-backend chroma
sentinelops pull-models
sentinelops doctor
sentinelops start --no-browser
code .
```

Skip `git init` if the project is already a Git repo.

## macOS / Linux From Scratch

```bash
# Install Git, uv, Ollama, VS Code, and GitHub Copilot first.
code --install-extension GitHub.copilot
code --install-extension GitHub.copilot-chat
uv tool install --from https://github.com/saikumar1767/Sentinel-Ops/archive/refs/heads/main.zip sentinel-ops --force

# In another terminal:
ollama serve

# In your project:
cd /path/to/your-project
git init
sentinelops attach --agent copilot --knowledge-backend chroma
sentinelops pull-models
sentinelops doctor
sentinelops start --no-browser
code .
```

## Expected Files

```text
.sentinelops/project.toml
.sentinelops/agent-context.md
.github/copilot-instructions.md
```

## How GitHub Copilot Knows To Use SentinelOps

GitHub Copilot reads the generated `.github/copilot-instructions.md` file in the repository.

When the user asks about logs, incidents, deployment health, readiness, runbooks, or remediation, the instructions tell Copilot to use SentinelOps as the repo-local operational context.

## Company Model Endpoint

```bash
sentinelops attach --agent copilot --knowledge-backend chroma --ollama-host https://models.example.internal
```

