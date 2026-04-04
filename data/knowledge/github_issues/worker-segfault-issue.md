---
title: GitHub Issue 188 - Reporting worker segmentation fault
incident_type: service
service: reporting-service
tags: service, crash, segmentation fault, restart
---
# Summary
Reporting workers crashed with segmentation fault, then repeatedly restarted under supervisor control. Health checks kept failing after restart until the bad native image extension was removed.

# Resolution
- Rolled back the native extension.
- Rebuilt the worker image.
- Added a canary check for repeated crash loops.
