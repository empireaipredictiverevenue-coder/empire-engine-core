---
type: skill
name: system.resources
version: "1.0"
description: Resource capacity planning — monitor utilization trends and forecast needs
tags: [system, resources, capacity]
timeout_seconds: 30
max_retries: 2
---

# system.resources

Resource capacity planning — monitor utilization trends and forecast needs

## Overview

This skill provides capabilities for resource capacity planning — monitor utilization trends and forecast needs.
It integrates with the Empire AI agent system through the VaultSkillDiscoverer
and ImmutableSkillRegistry.

## Capabilities

- Track CPU, memory, and disk utilization trends
- Forecast resource exhaustion dates
- Recommend scaling actions based on usage patterns
- Monitor cloud provider costs and usage limits

## Usage

This skill is available to any agent in the Empire AI fleet with access to
the `system.resources` skill. Invoke it through the skills framework:

```python
from skills import ImmutableSkillRegistry, VaultSkillDiscoverer

registry = ImmutableSkillRegistry()
discoverer = VaultSkillDiscoverer(registry)
discoverer.scan_and_register()
result = registry.execute("system.resources", {"params": {}})
```

## Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| params | dict | Execution parameters specific to this skill |
| context | dict | Optional context from calling agent |

## Example

```python
# Execute the skill
result = registry.execute("system.resources", {
    "params": {},
    "context": {"source": "mission-control"}
})
print(result)
```
