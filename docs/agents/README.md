# SentinelOps Agent Setup Guides

Use these guides when installing SentinelOps into a project for a specific coding agent, editor, or fully local SentinelOps-only workflow.

Each guide assumes the developer's machine may not have the required tools installed yet.

## Pick One

| Agent or Editor | Setup Guide | Attach Command |
| --- | --- | --- |
| Fully local SentinelOps | [local-only.md](local-only.md) | `sentinelops attach --knowledge-backend chroma --ollama-host http://localhost:11434` |
| Claude Code | [claude-code.md](claude-code.md) | `sentinelops attach --agent claude --knowledge-backend chroma` |
| Codex CLI | [codex.md](codex.md) | `sentinelops attach --agent codex --knowledge-backend chroma` |
| Cursor | [cursor.md](cursor.md) | `sentinelops attach --agent cursor --knowledge-backend chroma` |
| Windsurf | [windsurf.md](windsurf.md) | `sentinelops attach --agent windsurf --knowledge-backend chroma` |
| Cline | [cline.md](cline.md) | `sentinelops attach --agent cline --knowledge-backend chroma` |
| GitHub Copilot | [github-copilot.md](github-copilot.md) | `sentinelops attach --agent copilot --knowledge-backend chroma` |
| Everything supported | [all-agents.md](all-agents.md) | `sentinelops attach --agent all --knowledge-backend chroma` |

## Default Model Runtime

For normal developer usage, install Ollama once on the machine and let every attached repo use:

```text
http://localhost:11434
```

For the no-outside-world path, use [local-only.md](local-only.md). That path avoids generated cloud/editor agent integrations and keeps SentinelOps model calls on localhost or a private LAN/VPN Ollama endpoint.

If the company provides a central model endpoint, add it during attach:

```bash
sentinelops attach --agent <agent> --knowledge-backend chroma --ollama-host https://models.example.internal
```

## What Attach Does Not Do

`sentinelops attach` does not change application code, authentication, authorization, database connections, deployment manifests, or business logic.

It only adds SentinelOps config, runtime folders, and agent/editor instruction files.

## Official Agent Install References

- Claude Code: https://code.claude.com/docs/en/setup
- Codex CLI: https://help.openai.com/en/articles/11096431-openai-codex-ci-getting-started
- Cursor: https://cursor.com/download
- Windsurf: https://docs.windsurf.com/windsurf/getting-started
- Cline: https://docs.cline.bot/
- GitHub Copilot: https://docs.github.com/en/copilot/using-github-copilot/getting-started-with-github-copilot
