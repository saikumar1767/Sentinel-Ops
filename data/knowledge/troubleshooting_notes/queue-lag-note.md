---
title: Queue Lag Troubleshooting Note
incident_type: queue
service: payments-events
tags: queue, backlog, lag, consumer
---
# Note
Consumer lag that rises together with a large queue backlog is usually a throughput issue, not a producer outage. Downstream processing delay can breach the SLA before the queue fully saturates.

# Immediate Actions
- Compare enqueue rate versus consumer throughput.
- Inspect retry storms and poison messages.
- Scale workers carefully to avoid overloading downstream systems.
