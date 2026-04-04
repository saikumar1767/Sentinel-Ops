---
title: Platform Observability README
incident_type: performance
service: monitoring
tags: cpu, latency, performance, alerts
---
# Alerting Notes
Performance alerts trigger when CPU usage stays above 90 percent, request latency exceeds the service SLO, or queue lag remains above the degradation threshold.

# Investigation Guidance
Pair performance metrics with dependency logs before scaling. High CPU plus elevated latency often indicates saturation, while isolated latency without CPU pressure may indicate upstream slowness.

# Reporting
Manager updates should say whether the incident is a degradation or a hard outage and whether the team has contained the blast radius.
