# SentinelOps Commercial And Enterprise Usage

## What The Repo Covers Today

The repository now includes:

- Apache-2.0 licensing for SentinelOps application code in [LICENSE](../LICENSE)
- a repo distribution notice in [NOTICE](../NOTICE)
- a default model/config policy aimed at commercially friendlier self-hosted components
- production startup validation that rejects unsafe production profiles
- repo-local copilot installation and generated agent/editor integrations
- a single repo-local project config in `.sentinelops/project.toml`
- Claude Code skills and project memory generation for attached repos
- one-command local model bootstrap via `sentinelops pull-models`
- shared Postgres-capable metadata persistence and Postgres-backed workflow checkpoint support
- deterministic local retrieval pins for Chroma `0.4.24`, NumPy `<2`, ONNX Runtime `<1.20`, and PostHog `<3` after live Windows validation exposed native crashes in newer transitive versions

## Personal Mode Versus Shared Mode

SentinelOps now has two practical operating shapes:

### Personal mode

- local-first on one engineer's machine
- repo-local `.sentinelops/project.toml` as the main control file
- auth disabled by default
- repo-local runtime state

This is the correct shape when each engineer installs SentinelOps on their own office PC for their own repositories.

### Shared mode

- one deployment for multiple users
- shared persistence
- OIDC and stronger governance
- centralized telemetry and backups

This is optional. It is not required to use SentinelOps as a local repo copilot.

## What The Repo Does Not Magically Solve

This repo does not replace:

- your company's legal review
- data retention policy
- PII handling policy
- export-control review
- industry-specific compliance obligations
- vendor review of your chosen identity provider, hosting platform, monitoring stack, and model artifacts

## Practical Meaning

- The repo's own source code is explicitly licensed under Apache-2.0.
- That does not automatically grant rights for every model, dataset, logo, document corpus, or third-party service you connect to SentinelOps.
- The default model policy in `config/sentinelops.toml` and `config/sentinelops.production.toml` is intentionally conservative, but it is a guardrail, not legal advice.

## Why Repo-Local Installation Changes The Risk Story

Repo-local installation makes SentinelOps easier to adopt, but it also means the tool may read:

- project runbooks
- internal deployment files
- operational logs
- workflow metadata
- generated incident history

That is useful, but it also raises the importance of:

- auth and RBAC in shared environments
- internal model approval
- retention and redaction policy
- secrets management
- auditability

## Recommended Company Checklist Before Live Rollout

1. Confirm the deployment uses `config/sentinelops.production.toml` or an equivalent env-backed profile.
2. Confirm OIDC is enabled and mapped to real company roles.
3. Confirm Postgres backups and restore drills are tested.
4. Confirm telemetry export, alerting, and on-call ownership are live.
5. Confirm your connected models and corpora have passed internal legal and security review.
6. Confirm retention and redaction policies for logs, prompts, and retrieved artifacts.
7. Confirm repo-local adoption guidance exists for the teams that will attach SentinelOps to their projects.

## Why This Still Matters Even With Apache-2.0

- The application license covers SentinelOps source in this repository.
- It does not replace review of deployed models or internal company data use.
- It does not create indemnity, compliance certification, or legal sign-off.

## Practical Bottom Line

- If each engineer runs SentinelOps locally in their own repo, login is not required and the local-first path is the intended product shape.
- If a company later wants one shared SentinelOps deployment, auth, shared storage, and stronger operational controls become mandatory.

## Recommended Reading

- [README.md](../README.md)
- [SECURITY.md](../SECURITY.md)
- [docs/architecture.md](architecture.md)
- [docs/repo-copilot-validation.md](repo-copilot-validation.md)
