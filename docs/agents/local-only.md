# Fully Local Setup

Use this guide when the goal is SentinelOps incident investigation without sending repository content, logs, prompts, runbooks, diagnostics, or model requests to an external model provider.

This path is model-agnostic. SentinelOps only needs an Ollama-compatible local model runtime and configured model names. The model can be any suitable local chat model and local embedding model that your hardware can run.

## What This Path Guarantees

In normal operation, this setup keeps SentinelOps model calls on the configured Ollama endpoint:

```text
http://localhost:11434
```

or a private LAN/VPN endpoint such as:

```text
http://10.0.0.25:11434
```

This path does not generate Claude Code, Codex, Cursor, Windsurf, Cline, or GitHub Copilot instruction files. Those tools may have their own cloud-backed model behavior unless separately configured for local inference.

## What Still Needs Internet

Initial installation may use the internet if you install Git, uv, Ollama, SentinelOps, or model files from public sources.

After installation and model download are complete, the debugging and root-cause workflow can run locally if:

- Ollama uses local models, not `:cloud` models
- SentinelOps points only to localhost or a private LAN/VPN Ollama endpoint
- no cloud coding agent is used in the investigation loop
- web search, external retrieval, telemetry forwarding, and third-party integrations are not enabled

## Windows PowerShell From Scratch

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

4. Open a second terminal and keep Ollama running:

```powershell
ollama serve
```

5. Install SentinelOps:

```powershell
uv tool install --from https://github.com/saikumar1767/Sentinel-Ops/archive/refs/heads/main.zip sentinel-ops --force
```

6. Go to the project where SentinelOps should run:

```powershell
cd C:\path\to\your-project
```

7. If the project is not a Git repo yet:

```powershell
git init
```

8. Attach SentinelOps without any external coding-agent integration:

```powershell
sentinelops attach --knowledge-backend chroma --ollama-host http://localhost:11434
```

9. Pull the configured local model set:

```powershell
sentinelops pull-models
```

10. Verify readiness:

```powershell
sentinelops doctor
```

11. Start SentinelOps:

```powershell
sentinelops start --no-browser
```

## macOS / Linux From Scratch

1. Install Git and `uv` using your package manager.

2. Install Ollama from:

```text
https://ollama.com
```

3. Start Ollama in another terminal:

```bash
ollama serve
```

4. Install SentinelOps:

```bash
uv tool install --from https://github.com/saikumar1767/Sentinel-Ops/archive/refs/heads/main.zip sentinel-ops --force
```

5. Attach inside your project without external coding-agent integrations:

```bash
cd /path/to/your-project
git init
sentinelops attach --knowledge-backend chroma --ollama-host http://localhost:11434
sentinelops pull-models
sentinelops doctor
sentinelops start --no-browser
```

Skip `git init` if the project is already a Git repo.

## Expected Files

```text
.sentinelops/project.toml
.sentinelops/agent-context.md
```

SentinelOps may also add a `.gitignore` entry for repo-local runtime state.

This setup intentionally does not create:

```text
CLAUDE.md
AGENTS.md SentinelOps block
.claude/
.agents/plugins/
.cursor/rules/sentinelops.mdc
.windsurf/rules/sentinelops.md
.clinerules/sentinelops.md
.github/copilot-instructions.md SentinelOps block
```

## Model-Agnostic Configuration

The attach command writes `.sentinelops/project.toml`. To use a different local model, edit the model names:

```toml
[models]
analyze = "your-local-chat-model"
investigate = "your-local-chat-model"
embedding = "your-local-embedding-model"

[runtime]
ollama_host = "http://localhost:11434"
```

Then run:

```bash
sentinelops pull-models
sentinelops doctor
```

Use any local Ollama model that satisfies your quality, latency, context-window, hardware, and license requirements. Avoid names ending in `:cloud` when the requirement is no outside model call.

## Peer PC Ollama Host

For a team with one stronger office PC running Ollama, point each developer's repo at that machine:

```bash
sentinelops attach --knowledge-backend chroma --ollama-host http://10.0.0.25:11434
```

Use this only on a trusted LAN or VPN. The peer PC should be firewalled so only approved developer machines can reach Ollama.

This is not single-machine local, but it can still be no-outside-world local if traffic stays inside the private network and the peer Ollama host uses local models only.

## How To Avoid Accidental Cloud Calls

- Do not pass `--agent claude`, `--agent codex`, `--agent cursor`, `--agent windsurf`, `--agent cline`, `--agent copilot`, or `--agent all` for this path.
- Do not run Claude Code, GitHub Copilot, Cursor, Windsurf, Codex, or Cline unless that tool is separately configured to use a local model provider.
- Do not use Ollama model names ending in `:cloud`.
- Do not enable web search or external retrieval during incident investigation.
- Keep `ollama_host` set to localhost, a private LAN IP, or a VPN-only address.
- Review `.sentinelops/project.toml` before running investigations.

## Quick Verification

Run:

```bash
sentinelops paths
sentinelops doctor
```

Confirm:

- `project_ollama_host` is `http://localhost:11434` or a private LAN/VPN endpoint
- configured model names are local model names
- readiness reports Ollama and retrieval as available
- no external agent/editor integration files were generated

