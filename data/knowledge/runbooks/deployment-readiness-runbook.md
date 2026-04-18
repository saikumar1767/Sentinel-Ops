---
title: Deployment Readiness Runbook
incident_type: deployment
service: invoice-api
tags: deployment, readiness, rollout, kubernetes
---
# Symptoms
A rollout pauses when new pods fail readiness probes, health checks do not recover, or bootstrap exits before the deployment reaches steady state.

# Checks
- Read the failing pod startup log and readiness endpoint responses.
- Validate required configuration values and referenced secrets.
- Compare the failed release with the previous healthy deployment log.

# Mitigation
- Pause the rollout and keep traffic on the previous stable replica set.
- Fix missing configuration or failing dependencies before resuming.
- Re-run readiness validation in staging before promoting again.
