# All Agents Setup

Use this guide when a team wants every supported SentinelOps agent/editor integration in one project.

This is the broadest attach mode. If the team only uses one tool, prefer that tool's dedicated guide:

- [Claude Code](claude-code.md)
- [Codex CLI](codex.md)
- [Cursor](cursor.md)
- [Windsurf](windsurf.md)
- [Cline](cline.md)
- [GitHub Copilot](github-copilot.md)

## Windows PowerShell From Scratch

1. Install Git:

```powershell
winget install --id Git.Git -e
```

2. Install `uv`:

```powershell
winget install --id astral-sh.uv -e
```

3. Install Node.js LTS if using Claude Code or Codex CLI:

```powershell
winget install --id OpenJS.NodeJS.LTS -e
```

4. Install Ollama:

```powershell
winget install --id Ollama.Ollama -e
```

5. Optional agent installs:

```powershell
npm install -g @anthropic-ai/claude-code
npm install -g @openai/codex
winget install --id Microsoft.VisualStudioCode -e
code --install-extension saoudrizwan.claude-dev
code --install-extension GitHub.copilot
code --install-extension GitHub.copilot-chat
```

Install Cursor and Windsurf from their official download pages if your team uses them.

6. Open a second terminal and keep Ollama running:

```powershell
ollama serve
```

7. Install SentinelOps:

```powershell
uv tool install --from https://github.com/saikumar1767/Sentinel-Ops/archive/refs/heads/main.zip sentinel-ops --force
```

8. Attach all supported integrations:

```powershell
cd C:\path\to\your-project
git init
sentinelops attach --agent all --knowledge-backend chroma
sentinelops pull-models
sentinelops doctor
sentinelops start --no-browser
```

Skip `git init` if the project is already a Git repo.

## Expected Files

```text
.sentinelops/project.toml
.sentinelops/agent-context.md
AGENTS.md
CLAUDE.md
.claude/skills/
.claude/agents/
.agents/plugins/marketplace.json
plugins/sentinelops-copilot/
.cursor/rules/sentinelops.mdc
.windsurf/rules/sentinelops.md
.clinerules/sentinelops.md
.github/copilot-instructions.md
```

## Company Model Endpoint

```bash
sentinelops attach --agent all --knowledge-backend chroma --ollama-host https://models.example.internal
```

