SentinelOps Commercial And Enterprise Usage

What this repo now covers
- Apache-2.0 license for the SentinelOps application code in the repo root `LICENSE`
- Default model/config policy aimed at commercially friendlier self-hosted components
- Production startup validation that rejects unsafe production profiles
- Shared Postgres-capable metadata persistence and Postgres-backed workflow checkpoint support

What this repo does not magically solve
- Your company's legal review
- Data retention policy
- PII handling policy
- Export-control review
- Industry-specific compliance obligations
- Vendor review of your chosen identity provider, hosting platform, monitoring stack, and model artifacts

Practical meaning
- The repo's own code is now explicitly licensed under Apache-2.0.
- That does not automatically grant rights for every model, dataset, logo, document corpus, or third-party service you connect to SentinelOps.
- The default model policy in `config/sentinelops.toml` and `config/sentinelops.production.toml` is intentionally conservative, but it is still a guardrail, not legal advice.

Recommended company checklist before live rollout
1. Confirm the production deployment uses `config/sentinelops.production.toml` or an equivalent env-backed profile.
2. Confirm OIDC is enabled and mapped to real company roles.
3. Confirm Postgres backups and restore drills are tested.
4. Confirm telemetry export, alerting, and on-call ownership are live.
5. Confirm your connected models and corpora have passed internal legal and security review.
6. Confirm retention/redaction policies for logs, prompts, and retrieved artifacts.

Why this still matters even with an Apache-2.0 app license
- The application license covers the SentinelOps source in this repository.
- It does not replace review of deployed models or internal company data use.
- It does not create indemnity, compliance certification, or legal sign-off.
