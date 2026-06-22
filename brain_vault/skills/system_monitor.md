---
type: skill
name: system.monitor
version: "1.0"
description: Real-time system monitoring — CPU, memory, disk, network, and process health
tags: [system, monitoring, infrastructure]
timeout_seconds: 30
max_retries: 2
---

# system.monitor

Real-time system monitoring — CPU, memory, disk, network, and process health

## Overview

This skill provides capabilities for real-time system monitoring — cpu, memory, disk, network, and process health.
It integrates with the Empire AI agent system through the VaultSkillDiscoverer
and ImmutableSkillRegistry.

## Capabilities

- Check CPU load, memory usage, and disk space
- Monitor network traffic and connection stats
- Track process health and resource consumption
- Generate system health reports with trend data

## Usage

This skill is available to any agent in the Empire AI fleet with access to
the `system.monitor` skill. Invoke it through the skills framework:

```python
from skills import ImmutableSkillRegistry, VaultSkillDiscoverer

registry = ImmutableSkillRegistry()
discoverer = VaultSkillDiscoverer(registry)
discoverer.scan_and_register()
result = registry.execute("system.monitor", {"params": {}})
```

## Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| params | dict | Execution parameters specific to this skill |
| context | dict | Optional context from calling agent |

## Example

```python
# Execute the skill
result = registry.execute("system.monitor", {
    "params": {},
    "context": {"source": "mission-control"}
})
print(result)
```
