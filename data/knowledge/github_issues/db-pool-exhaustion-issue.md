---
title: GitHub Issue 142 - Checkout pool exhaustion after traffic spike
incident_type: database
service: checkout-api
tags: database, pool exhaustion, timeout, postgres
---
# Summary
After a flash sale, checkout workers logged database connection timeout after 30 seconds and connection pool exhausted on primary-postgres. Throughput recovered only after lowering worker concurrency and clearing stuck transactions.

# Resolution
- Reduced worker count temporarily.
- Killed two long-running reporting queries.
- Increased connection timeout visibility in alerts.
