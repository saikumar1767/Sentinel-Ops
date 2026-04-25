# Operational Risk And Human Review

SentinelOps can help teams collect context, draft hypotheses, and structure incident work. It must not be used as a substitute for human judgment or operational controls.

This document is not legal advice, security advice, compliance advice, or a production-readiness certification.

## Mandatory Human Review

Treat every SentinelOps output as an unverified draft.

A qualified human must review and approve any SentinelOps-assisted conclusion or recommendation before it affects:

- production systems
- customer data
- customer availability
- security posture
- compliance posture
- incident declarations
- public communications
- legal communications
- financial decisions
- destructive operations
- privileged operations
- irreversible operations

## No Automatic Remediation Without Controls

Do not allow SentinelOps, generated agent scaffolding, scripts, model output, or integrations to take automatic production action unless all of the following are in place:

- explicit human approval
- least-privilege credentials
- audit logging
- rollback plan
- backup or restore path
- monitoring and alerting
- scoped blast radius
- tested runbook
- separation between diagnosis and execution
- review of model, prompt, and data behavior

## Incident-Response Duties Stay With The User

Users remain responsible for:

- severity assessment
- customer impact analysis
- containment
- escalation
- evidence preservation
- rollback
- remediation
- communications
- post-incident review
- regulatory reporting
- customer notice
- security disclosure
- compliance records

SentinelOps may help prepare or organize information, but it does not own those duties.

## Data Handling Duties Stay With The User

SentinelOps may read or generate sensitive materials, including logs, prompts, retrieved documents, code, runbooks, incident notes, root-cause diagnostics, and indexed incident memory.

Users are responsible for:

- deciding what data SentinelOps may read
- redacting secrets and personal data
- managing retention
- controlling access
- reviewing retrieval corpora
- reviewing model behavior
- reviewing third-party terms
- protecting customer and regulated data
- deleting or exporting data when required
- keeping audit records when required

## Production Rollout Checklist

Before production, shared, hosted, commercial, enterprise, or regulated use, users should verify:

1. A responsible owner is assigned.
2. Human approval is required before production-changing actions.
3. Authentication and authorization are enabled.
4. Network exposure is intentionally limited.
5. Secrets are not stored in checked-in config.
6. Logs and prompts are reviewed for sensitive data.
7. Incident memory retention and deletion rules are defined.
8. Models and retrieval corpora have passed internal review.
9. Backups and restore drills exist for shared storage.
10. Monitoring and alerting exist for the SentinelOps deployment.
11. Security update and vulnerability-response processes are defined.
12. Legal, compliance, and procurement reviews are complete where required.

## Stop Conditions

Stop using SentinelOps output and escalate to qualified humans if:

- output conflicts with observed evidence
- output recommends destructive or irreversible action
- output touches customer data, regulated data, secrets, credentials, keys, tokens, or certificates
- output affects security controls
- output affects production infrastructure
- output may trigger legal, regulatory, contractual, or customer-notice obligations
- output appears hallucinated, incomplete, stale, or based on wrong context
- the team cannot explain why the recommendation is safe

## Practical Rule

SentinelOps can assist the operator. It must not replace the operator.

