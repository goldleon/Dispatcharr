# Ponytail Debt Ledger

This file tracks the deliberate shortcuts and deferrals marked with `ponytail:` comments in the codebase.

## Active Debt Items

### `core/views.py`
- [core/views.py:19](file:///Users/anassbouchtaoui/Documents/GitHub/Dispatcharr/core/views.py#L19) - global Redis lock. ceiling: global Redis lock. upgrade: per-resource locks if concurrency contention becomes a bottleneck. (Author: Anass Bouchtaoui)

### `core/api_views.py`
- [core/api_views.py:486](file:///Users/anassbouchtaoui/Documents/GitHub/Dispatcharr/core/api_views.py#L486) - in-memory sorting. ceiling: in-memory sorting. upgrade: cached or paginated response if timezone list size causes rendering bottlenecks. (Author: Anass Bouchtaoui)

### `apps/proxy/vod_proxy/views.py`
- [apps/proxy/vod_proxy/views.py:398](file:///Users/anassbouchtaoui/Documents/GitHub/Dispatcharr/apps/proxy/vod_proxy/views.py#L398) - stdlib re module. ceiling: stdlib re module. upgrade: third-party regex library if complex backtracking or JS features are required. (Author: Anass Bouchtaoui)

### `apps/proxy/live_proxy/services/log_parsers.py`
- [apps/proxy/live_proxy/services/log_parsers.py:3](file:///Users/anassbouchtaoui/Documents/GitHub/Dispatcharr/apps/proxy/live_proxy/services/log_parsers.py#L3) - plain dict lookup. ceiling: plain dict lookup. upgrade: ABC hierarchy if we add more than 10 concrete parsers or need runtime pluggability. (Author: Anass Bouchtaoui)
- [apps/proxy/live_proxy/services/log_parsers.py:332](file:///Users/anassbouchtaoui/Documents/GitHub/Dispatcharr/apps/proxy/live_proxy/services/log_parsers.py#L332) - plain dict registry. ceiling: plain dict registry. upgrade: dynamic factory registration if parser plugins require runtime loading. (Author: Anass Bouchtaoui)

---
**Summary:** 5 markers, 0 with no trigger.
