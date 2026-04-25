# SentinelOps Liability And Use Boundaries

This guide explains the practical risk boundary for SentinelOps in plain operational terms. It should be read with [../LICENSE](../LICENSE), [../NOTICE](../NOTICE), [../DISCLAIMER.md](../DISCLAIMER.md), [../TERMS_OF_USE.md](../TERMS_OF_USE.md), [../SECURITY.md](../SECURITY.md), and [commercial-and-enterprise-usage.md](commercial-and-enterprise-usage.md).

This guide is not legal advice.

## Plain-English Summary

SentinelOps is a tool that helps investigate incidents. It is not a promise that incidents will be prevented, found, fixed, explained correctly, or handled safely.

If you use SentinelOps, you are responsible for checking its output and deciding what to do. Do not blame the project authors for your outage, data loss, security issue, compliance problem, wrong action, missed alert, customer harm, or business loss.

## What SentinelOps Is

SentinelOps is:

- an incident and operations copilot
- a local-first repo assistant
- a diagnostic and workflow aid
- a retrieval and incident-memory tool
- a way to organize operational context for human review

## What SentinelOps Is Not

SentinelOps is not:

- a guarantee of root cause
- a guarantee of incident prevention
- a guarantee of security
- a guarantee of compliance
- a guarantee of uptime
- a production operator
- an autonomous remediation system
- a legal, compliance, financial, safety, or professional advisor
- a replacement for SRE, security, DevOps, legal, compliance, or incident-command review
- a certified product for regulated or safety-critical environments

## User Assumes The Risk

Users assume the risk of:

- installing SentinelOps
- configuring SentinelOps
- exposing SentinelOps on a network
- running SentinelOps with access to sensitive repositories, logs, runbooks, documents, tickets, alerts, or incident history
- connecting SentinelOps to models, retrieval backends, databases, identity providers, monitoring systems, or third-party services
- relying on SentinelOps output
- automating actions based on SentinelOps output
- deploying SentinelOps in production, shared, customer-facing, commercial, enterprise, or regulated environments

## Human Review Boundary

Every operational conclusion from SentinelOps must be treated as a draft until a qualified human reviews it.

Before acting on SentinelOps output, users should independently verify:

- the logs and evidence used
- the timeline
- the affected services
- the blast radius
- the proposed root cause
- the proposed remediation
- rollback impact
- customer impact
- security impact
- compliance impact
- data-retention and redaction impact

## No Responsibility For User Environment

SentinelOps contributors, maintainers, authors, distributors, and repository owners do not control the user's:

- repositories
- secrets
- logs
- prompts
- documents
- runbooks
- incident history
- models
- retrieval backends
- production systems
- cloud accounts
- identity providers
- monitoring stack
- deployment topology
- access-control policy
- internal approvals
- legal and compliance duties

Because those are outside the project author's control, users are responsible for securing and governing them.

## Claims And Marketing Boundary

Do not interpret documentation, examples, badges, tests, scripts, comments, or demos as promises of a particular result.

In this repository:

- local-first means the intended default deployment shape, not a guarantee that data can never leave a machine
- root-cause diagnostics means a structured diagnostic output, not guaranteed truth
- deterministic means specific code paths aim for reproducible behavior, not perfect correctness
- production profile means a configuration profile with stronger defaults, not a production-readiness certification
- hardening means selected security controls exist, not a guarantee of security
- enterprise usage guidance means rollout guidance, not legal approval or compliance certification

## Suggested Proof Package

If there is ever a dispute about what SentinelOps promised, the following files should be reviewed together:

- [../LICENSE](../LICENSE)
- [../NOTICE](../NOTICE)
- [../DISCLAIMER.md](../DISCLAIMER.md)
- [../TERMS_OF_USE.md](../TERMS_OF_USE.md)
- [../SECURITY.md](../SECURITY.md)
- [commercial-and-enterprise-usage.md](commercial-and-enterprise-usage.md)
- [operational-risk-and-human-review.md](operational-risk-and-human-review.md)

Those files are intended to show that SentinelOps is provided without warranty, without guaranteed outcomes, without indemnity, and with user responsibility for deployment and reliance.

## Important Legal Limit

Documentation can help show the intended risk boundary, but no markdown file can guarantee that nobody will sue or that every court will enforce every disclaimer. Applicable law, contracts, facts, conduct, marketing statements, paid services, gross negligence, willful misconduct, consumer-protection law, data-protection law, and jurisdiction may affect the result.

For commercial distribution, paid support, SaaS hosting, enterprise deployment, or regulated use, get jurisdiction-specific legal review and written terms.

