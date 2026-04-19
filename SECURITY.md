Security Notes

SentinelOps is designed to operate on sensitive operational data. For production use:

- Enable `auth_mode=oidc`.
- Use shared Postgres-backed metadata and workflow checkpoint stores.
- Run with HTTPS in front of the application.
- Keep secrets in a managed secret store or mounted secret files, not in checked-in config.
- Use centralized telemetry and alerting.
- Review retrieved documents and model inputs for sensitive data handling requirements.

If you discover a security issue in the code, handle disclosure privately with the repository owner before public sharing.
