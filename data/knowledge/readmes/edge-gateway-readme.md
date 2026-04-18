---
title: Edge Gateway README
incident_type: service
service: edge-gateway
tags: gateway, upstream, 502, circuit breaker
---
# Failure Modes
The edge gateway returns HTTP 502 when upstream services fail health checks or when the circuit breaker opens after repeated dependency errors.

# Operator Notes
If 502 responses coincide with open circuit breakers, check the failing upstream first. Restarting the gateway rarely fixes the underlying dependency outage by itself.

# Communication
Use a plain-language summary that distinguishes user-facing failure from internal degradation.
