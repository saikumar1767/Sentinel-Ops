---
title: Network DNS Failure Runbook
incident_type: network
service: gateway
tags: dns, lookup, resolver, network
---
# Symptoms
Requests back up when services fail to resolve internal hostnames, DNS lookups time out, or repeated connection reset by peer events appear between subnets.

# Checks
- Resolve the affected hostname from the same subnet as the failing service.
- Confirm upstream resolver health, recent DNS changes, and packet loss.
- Compare the current network log against the last known good run.

# Mitigation
- Roll back the last resolver or service discovery change if one occurred.
- Redirect traffic to healthy zones when packet loss or reset rates stay elevated.
- Open a network incident if DNS failures affect multiple services.
