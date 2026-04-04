---
title: Queue Backlog Runbook
incident_type: queue
service: payments-events
tags: queue, backlog, consumer lag, sla
---
# Symptoms
Queue incidents usually present as backlog growth, increasing consumer lag, breached downstream processing SLA, or workers unable to drain messages fast enough.

# Checks
- Confirm whether producers spiked or consumers slowed down.
- Review dead-letter queue volume and downstream dependency health.
- Identify the oldest message age and the current worker throughput.

# Mitigation
- Scale consumers only if downstream systems can absorb the load.
- Pause noisy producers when backlog growth is caused by one tenant or workflow.
- Clear poison messages after confirming they are safe to quarantine.
