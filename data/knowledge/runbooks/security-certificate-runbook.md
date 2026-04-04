---
title: Security Certificate Failure Runbook
incident_type: security
service: edge-gateway
tags: tls, certificate, expired, security
---
# Symptoms
TLS handshake failures, expired certificates, or secure connection errors indicate that clients can no longer establish trusted encrypted sessions.

# Checks
- Inspect certificate expiration, chain completeness, and hostname match.
- Confirm whether the issue is limited to one edge gateway or all regions.
- Review the last certificate rotation or load balancer change.

# Mitigation
- Renew or roll back the broken certificate immediately.
- Restart only the affected edge component after certificate validation passes.
- Treat widespread TLS failure as a high-severity security incident.
