---
type: skill
name: system.alert
version: "1.0"
description: Alert management — configure, route, and silence alerts across channels
tags: [system, alerting, notification]
timeout_seconds: 30
max_retries: 2
---

# system.alert

Alert management — configure, route, and silence alerts across channels

## Overview

This skill provides capabilities for alert management — configure, route, and silence alerts across channels.
It integrates with the Empire AI agent system through the VaultSkillDiscoverer
and ImmutableSkillRegistry.

## Capabilities

- Configure alert thresholds for system metrics
- Route alerts to Telegram, email, or SMS
- Silence or snooze non-critical alerts
- Review alert history and acknowledgement status

## Usage

This skill is available to any agent in the Empire AI fleet with access to
the `system.alert` skill. Invoke it through the skills framework:

```python
from skills import ImmutableSkillRegistry, VaultSkillDiscoverer

registry = ImmutableSkillRegistry()
discoverer = VaultSkillDiscoverer(registry)
discoverer.scan_and_register()
result = registry.execute("system.alert", {"params": {}})
```

## Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| params | dict | Execution parameters specific to this skill |
| context | dict | Optional context from calling agent |

## Example

```python
# Execute the skill
result = registry.execute("system.alert", {
    "params": {},
    "context": {"source": "mission-control"}
})
print(result)
```
