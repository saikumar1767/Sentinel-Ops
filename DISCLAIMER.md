# SentinelOps Disclaimer

This document states important limits on responsibility, warranties, support, and operational reliance for SentinelOps. It is intended to be read together with [LICENSE](LICENSE), [NOTICE](NOTICE), [TERMS_OF_USE.md](TERMS_OF_USE.md), [SECURITY.md](SECURITY.md), and the risk guidance in [docs/liability-and-use-boundaries.md](docs/liability-and-use-boundaries.md).

This document is not legal advice. If you need legal advice, compliance approval, insurance guidance, or a binding commercial allocation of risk, consult a qualified lawyer in your jurisdiction.

## No Warranty

SentinelOps is provided under the Apache License, Version 2.0. To the maximum extent permitted by applicable law, SentinelOps is provided as-is, as-available, and with all faults.

No contributor, maintainer, author, distributor, or repository owner makes any warranty, promise, representation, or guarantee that SentinelOps:

- will detect every incident, outage, vulnerability, misconfiguration, root cause, risk, or operational failure
- will produce correct, complete, current, safe, or useful output
- will prevent downtime, data loss, security compromise, compliance failure, customer impact, financial loss, reputational harm, or operational harm
- will be fit for any particular production, enterprise, regulated, security-critical, safety-critical, or business-critical use
- will work with every model, dependency, deployment platform, identity provider, data source, repository, runbook, log format, or operating environment
- will be free from bugs, vulnerabilities, dependency issues, hallucinations, incorrect recommendations, missing context, or unexpected behavior

## No Liability For Use Or Reliance

To the maximum extent permitted by applicable law, no contributor, maintainer, author, distributor, or repository owner is responsible or liable for any claim, damage, loss, cost, injury, penalty, fine, outage, data exposure, business interruption, lost profit, lost revenue, lost goodwill, remediation cost, replacement cost, investigation cost, legal cost, compliance cost, or other consequence arising from or related to:

- using SentinelOps
- not being able to use SentinelOps
- relying on SentinelOps output
- following, not following, modifying, or automating recommendations from SentinelOps
- connecting SentinelOps to models, logs, documents, repositories, incident history, runbooks, services, tickets, alerts, telemetry, databases, identity systems, or third-party tools
- deploying SentinelOps in local, shared, hosted, production, commercial, enterprise, regulated, or customer-facing environments
- misconfiguration, insecure deployment, weak access control, missing authentication, exposed secrets, excessive permissions, insufficient review, or unsafe operational process
- third-party models, data sources, corpora, dependencies, services, hosting providers, identity providers, monitoring tools, or integrations
- user-provided data, generated data, saved incidents, indexed incident memory, root-cause diagnostics, prompts, retrieved documents, or logs

## Human Review Required

SentinelOps is an incident and operations copilot. It is a decision-support tool, not a human operator, legal advisor, security auditor, compliance officer, incident commander, SRE, DevOps engineer, medical device, safety system, or autonomous production-control system.

All output must be reviewed by qualified humans before it is used for operational, security, legal, financial, compliance, customer-impacting, production, or business-critical decisions.

Users are solely responsible for:

- deciding whether SentinelOps is appropriate for their use case
- validating all outputs before relying on them
- testing SentinelOps in their environment
- maintaining backups, rollback plans, incident procedures, observability, access control, and human approval paths
- complying with all laws, regulations, contracts, policies, licenses, and internal governance requirements
- protecting secrets, personal data, confidential data, regulated data, and customer data
- reviewing model licenses, data rights, third-party terms, and security posture before use

## No Professional Advice

SentinelOps output is not legal, compliance, cybersecurity, financial, business, medical, safety, engineering-certification, or professional advice. It may be incomplete, outdated, incorrect, or inappropriate for your environment.

Do not treat SentinelOps output as a substitute for professional judgment, internal review, independent testing, or advice from qualified professionals.

## No Indemnity, Support, SLA, Or Certification

Unless a separate written agreement signed by the responsible party expressly says otherwise, SentinelOps does not include:

- indemnity
- warranty
- support obligations
- service-level commitments
- uptime commitments
- maintenance commitments
- security certification
- compliance certification
- legal sign-off
- production-readiness certification
- insurance coverage
- responsibility for third-party services, models, dependencies, data, or integrations

No statement in documentation, examples, comments, issues, pull requests, demos, samples, generated scaffolding, release notes, or discussions should be interpreted as creating any of those obligations.

## High-Risk And Regulated Use

Do not use SentinelOps as the sole control, decision maker, or source of truth in high-risk, safety-critical, life-critical, mission-critical, regulated, emergency-response, critical-infrastructure, financial-trading, medical, aviation, automotive, defense, law-enforcement, or other environments where failure or incorrect output could reasonably lead to serious harm.

If you use SentinelOps in any such environment, you do so at your own risk and must implement independent review, validation, monitoring, fail-safes, approvals, and legal/compliance controls.

## Third-Party Models, Data, And Services

SentinelOps may be connected to third-party or self-hosted models, data sources, corpora, dependencies, platforms, and services. Those components may have their own licenses, security properties, privacy terms, data-retention behavior, availability risks, and legal restrictions.

The SentinelOps repository license does not grant rights to third-party models, third-party datasets, customer data, internal documents, trademarks, logos, hosted services, or external systems. Users are solely responsible for reviewing and complying with those obligations.

## Security And Data Handling

SentinelOps may read or process sensitive operational material, including logs, runbooks, deployment manifests, workflow metadata, generated incident history, saved root-cause diagnostics, retrieved documents, and indexed incident memory.

Users are solely responsible for configuring, securing, monitoring, and governing their deployment, including authentication, authorization, network exposure, secret management, redaction, retention, auditability, backups, vulnerability management, and incident response.

## Marketing And Documentation Limits

Words such as copilot, diagnostics, root cause, hardening, production, enterprise, security, local-first, reviewed, deterministic, or validation describe product intent, engineering design, or documented behavior. They do not create a guarantee, warranty, SLA, certification, legal assurance, compliance approval, or promise of a particular outcome.

Examples, fixtures, sample incidents, tests, validation scripts, and documentation are illustrative. They do not prove that SentinelOps is safe, complete, correct, compliant, or suitable for every environment.

## Separate Commercial Terms

If SentinelOps is sold, hosted, embedded in a service, provided with support, deployed for customers, or used in an enterprise or regulated environment, separate written commercial terms should define responsibility, support, security obligations, data processing, warranties, liability limits, indemnity, and governing law.

Absent such separate written terms, the Apache-2.0 license, this disclaimer, and the repository notices describe the intended risk boundary to the maximum extent permitted by applicable law.

