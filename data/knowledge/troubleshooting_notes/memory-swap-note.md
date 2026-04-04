---
title: Memory and Swap Pressure Note
incident_type: memory
service: analytics-worker
tags: memory, swap, pressure, latency
---
# Note
When available memory drops below a few percent and swap activity stays elevated, the host is under memory pressure even if there is no explicit out-of-memory crash yet.

# Immediate Actions
- Reduce background compaction or batch size.
- Check for runaway processes or cache growth.
- Monitor whether latency improves after reclaiming memory.
