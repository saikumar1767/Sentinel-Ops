---
title: Database Timeout Runbook
incident_type: database
service: checkout-api
tags: database, timeout, connection pool, postgres
---
# Symptoms
Checkout traffic degrades when logs show database connection timeout errors, connection pool exhaustion, or workers stalled waiting for a free postgres connection.

# Checks
- Confirm primary postgres reachability and DNS resolution.
- Check connection pool saturation, long transactions, and lock wait time.
- Compare the failing run with the previous healthy log for new timeout lines.

# Mitigation
- Reduce application concurrency until the database is stable.
- Terminate or recycle stuck workers only after database health is confirmed.
- Escalate to the database owner if lock waits or pool exhaustion persist.
