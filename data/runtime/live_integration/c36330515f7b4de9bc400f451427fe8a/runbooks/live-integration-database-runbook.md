---
title: Live integration database runbook
incident_type: database
---

# Symptoms

Database timeout incidents often include connection pool exhaustion and stalled workers waiting on postgres.

# Checks

Confirm the database is reachable and compare the failing run with the previous healthy baseline.
