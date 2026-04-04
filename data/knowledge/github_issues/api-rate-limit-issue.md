---
title: GitHub Issue 201 - Billing partner API throttling
incident_type: api
service: billing-api
tags: api, 429, rate limit, throttle
---
# Summary
Partner billing integration returned HTTP 429 after rate limit ceilings were exceeded on the charges endpoint. Retries amplified the spike and extended customer checkout delays.

# Resolution
- Added jittered backoff for retry traffic.
- Lowered request burst size per tenant.
- Coordinated a higher partner throttle budget.
