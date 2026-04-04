---
title: GitHub Issue 176 - Resolver failover regression
incident_type: network
service: gateway
tags: dns, resolver, failover, network
---
# Summary
A resolver failover change caused failed to resolve internal names and DNS lookup timed out messages during startup. Packet loss was not the main issue; the resolver endpoint list was incomplete.

# Resolution
- Reverted the resolver failover change.
- Rebuilt the DNS cache on affected nodes.
- Added a validation check for missing resolver targets.
