---
title: Disk Pressure Troubleshooting Note
incident_type: disk
service: backup-worker
tags: disk, no space left, storage, backup
---
# Note
If disk usage exceeds 95 percent and logs include no space left on device, treat the node as storage constrained. Backup jobs often fail first because archive writes are large and continuous.

# Immediate Actions
- Delete expired backup artifacts if the retention policy allows it.
- Move large temporary files off the host.
- Confirm that new writes succeed before resuming scheduled backups.
