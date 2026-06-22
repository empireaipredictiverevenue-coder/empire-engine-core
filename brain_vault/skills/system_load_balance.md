---
type: skill
name: system.load-balance
version: "1.0"
description: Load balancer management — traffic distribution, health checks, and failover
tags: [system, load-balancing, infrastructure]
timeout_seconds: 30
max_retries: 2
---

# system.load-balance

Load balancer management — traffic distribution, health checks, and failover

## Overview

This skill provides capabilities for load balancer management — traffic distribution, health checks, and failover.
It integrates with the Empire AI agent system through the VaultSkillDiscoverer
and ImmutableSkillRegistry.

## Capabilities

- Configure upstream servers and health checks
- Monitor request distribution across backends
- Manage failover and circuit-breaker settings
- Review load balancer metrics and logs

## Usage

This skill is available to any agent in the Empire AI fleet with access to
the `system.load-balance` skill. Invoke it through the skills framework:

```python
from skills import ImmutableSkillRegistry, VaultSkillDiscoverer

registry = ImmutableSkillRegistry()
discoverer = VaultSkillDiscoverer(registry)
discoverer.scan_and_register()
result = registry.execute("system.load-balance", {"params": {}})
```

## Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| params | dict | Execution parameters specific to this skill |
| context | dict | Optional context from calling agent |

## Example

```python
# Execute the skill
result = registry.execute("system.load-balance", {
    "params": {},
    "context": {"source": "mission-control"}
})
print(result)
```
