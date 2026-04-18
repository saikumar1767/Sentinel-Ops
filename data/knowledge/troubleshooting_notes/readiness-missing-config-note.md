---
title: Readiness Failure from Missing Config Note
incident_type: configuration
service: invoice-api
tags: configuration, missing environment variable, readiness, deployment
---
# Note
When a rollout fails readiness immediately after bootstrap and the log also says a required environment variable is missing, classify the incident as configuration before deployment.

# Immediate Actions
- Compare required secrets against the release manifest.
- Verify that the missing environment value is present in the target namespace.
- Retry only after configuration validation passes.
