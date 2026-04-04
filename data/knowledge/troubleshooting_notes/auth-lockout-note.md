---
title: Authentication Lockout Note
incident_type: authentication
service: identity-api
tags: authentication, failed login, lockout, credentials
---
# Note
Repeated failed login attempts plus rising account lock counters usually point to credential stuffing or a broken client using stale secrets.

# Immediate Actions
- Identify the top offending source IPs.
- Confirm whether only one client or many accounts are affected.
- Keep rate limiting enabled while investigating.
