---
title: Service 502 Troubleshooting Note
incident_type: service
service: edge-gateway
tags: service, 502, upstream, circuit breaker
---
# Note
HTTP 502 and circuit breaker open events generally mean the upstream dependency is failing or unhealthy. Restarting the proxy without restoring the upstream usually prolongs the incident.

# Immediate Actions
- Inspect the upstream dependency first.
- Verify whether the error is isolated to one cluster or region.
- Hold traffic shifts until the upstream recovers.
