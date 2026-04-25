# Claude Code Setup

This guide installs SentinelOps as a repo-local copilot for Claude Code.

## Windows PowerShell From Scratch

1. Install Git:

```powershell
winget install --id Git.Git -e
```

2. Install `uv`:

```powershell
winget install --id astral-sh.uv -e
```

3. Install Node.js LTS for the Claude Code npm installer:

```powershell
winget install --id OpenJS.NodeJS.LTS -e
```

4. Install Ollama:

```powershell
winget install --id Ollama.Ollama -e
```

5. Install Claude Code:

```powershell
npm install -g @anthropic-ai/claude-code
```

6. Open a second terminal and keep Ollama running:

```powershell
ollama serve
```

7. Install SentinelOps:

```powershell
uv tool install --from https://github.com/saikumar1767/Sentinel-Ops/archive/refs/heads/main.zip sentinel-ops --force
```

8. Go to the project where Claude Code should use SentinelOps:

```powershell
cd C:\path\to\your-project
```

9. If the project is not a Git repo yet:

```powershell
git init
```

10. Attach SentinelOps for Claude Code:

```powershell
sentinelops attach --agent claude --knowledge-backend chroma
```

11. Pull the local models:

```powershell
sentinelops pull-models
```

12. Verify readiness:

```powershell
sentinelops doctor
```

13. Start SentinelOps when live API or console access is useful:

```powershell
sentinelops start --no-browser
```

14. In the same project directory, start Claude Code:

```powershell
claude
```

## macOS / Linux From Scratch

1. Install Git, Node.js LTS, and `uv` using your package manager.

2. Install Ollama from:

```text
https://ollama.com
```

3. Install Claude Code:

```bash
npm install -g @anthropic-ai/claude-code
```

4. Start Ollama in another terminal:

```bash
ollama serve
```

5. Install SentinelOps:

```bash
uv tool install --from https://github.com/saikumar1767/Sentinel-Ops/archive/refs/heads/main.zip sentinel-ops --force
```

6. Attach inside your project:

```bash
cd /path/to/your-project
git init
sentinelops attach --agent claude --knowledge-backend chroma
sentinelops pull-models
sentinelops doctor
sentinelops start --no-browser
claude
```

Skip `git init` if the project is already a Git repo.

## Expected Files

```text
.sentinelops/project.toml
.sentinelops/agent-context.md
CLAUDE.md
.claude/skills/sentinelops-check/SKILL.md
.claude/skills/sentinelops-investigate/SKILL.md
.claude/skills/sentinelops-start/SKILL.md
.claude/skills/sentinelops-pull-models/SKILL.md
.claude/agents/sentinelops-ops-copilot.md
```

## How Claude Code Knows To Use SentinelOps

Claude Code reads the generated `CLAUDE.md`, `.claude/skills/`, and `.claude/agents/` files.

When a user asks about logs, incidents, readiness, deployment failures, runbooks, or remediation, Claude Code should run SentinelOps commands such as:

```bash
sentinelops paths
sentinelops doctor
sentinelops start --no-browser
```

Then it can use the local API routes such as `/investigate`, `/workflow/investigate`, and `/knowledge/search`.

## Company Model Endpoint

If your company hosts the model runtime:

```bash
sentinelops attach --agent claude --knowledge-backend chroma --ollama-host https://models.example.internal
```

