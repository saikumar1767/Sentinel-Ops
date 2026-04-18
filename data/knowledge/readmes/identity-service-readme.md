---
title: Identity Service README
incident_type: authentication
service: identity-api
tags: auth, login, lockout, credentials
---
# Authentication Controls
The identity service enforces account lock thresholds, login throttling, and credential anomaly detection. Repeated failed login attempts from one source should be treated as a probable brute-force pattern.

# Troubleshooting
Review failed login volume, affected accounts, and source IP concentration. If lock thresholds are climbing quickly, verify that rate limiting and challenge flows are still active.

# Escalation
Security operations should be engaged when credential failures are repeated across privileged accounts.
