---
title: Payments Service README
incident_type: database
service: checkout-api
tags: payments, postgres, checkout, dependency
---
# Dependencies
The payments stack depends on primary-postgres for checkout persistence and on billing-api for charge submission. Checkout workers share a bounded connection pool to avoid overrunning postgres.

# Operational Notes
When pool exhaustion occurs, checkout requests stall before downstream billing work begins. The first signs are database timeout lines, retries, and warnings about waiting for a free connection.

# Escalation
Escalate to the database owner when timeout errors persist for more than five minutes or when long-running transactions block pool recovery.
