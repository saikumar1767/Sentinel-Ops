# Security Notes

SentinelOps is designed to operate on sensitive operational data. Treat the local and repo-local modes as convenience surfaces, not proof that production hardening is complete.

## Recommended Production Baseline

- Enable `auth_mode=oidc`.
- Use shared Postgres-backed metadata and workflow checkpoint stores.
- Run behind HTTPS.
- Keep secrets in a managed secret store or mounted secret files, not in checked-in config.
- Use centralized telemetry, alerting, and on-call ownership.
- Review retrieved documents, logs, and model inputs for sensitive data handling requirements.
- Validate repo-local adoption guidance before allowing broad team rollout.

## Repo-Local Copilot Considerations

When SentinelOps is attached to a repo, it may read:

- runbooks
- deployment manifests
- CI workflows
- local logs
- generated incident history

That makes adoption easier, but it also increases the importance of:

- least privilege
- secrets hygiene
- model and corpus review
- auditability

## Vulnerability Disclosure

If you discover a security issue in the code, handle disclosure privately with the repository owner before public sharing.
