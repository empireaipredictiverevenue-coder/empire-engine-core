---
type: skill
name: system.discovery
version: "1.0"
description: Service discovery — find and map all Empire services, their ports, and dependencies
tags: [system, discovery, architecture]
timeout_seconds: 30
max_retries: 2
---

# system.discovery

Service discovery — find and map all Empire services, their ports, and dependencies

## Overview

This skill provides capabilities for service discovery — find and map all empire services, their ports, and dependencies.
It integrates with the Empire AI agent system through the VaultSkillDiscoverer
and ImmutableSkillRegistry.

## Capabilities

- Scan for running services across all ports
- Map service dependencies and communication paths
- Document API endpoints and their purposes
- Detect undocumented or zombie services

## Usage

This skill is available to any agent in the Empire AI fleet with access to
the `system.discovery` skill. Invoke it through the skills framework:

```python
from skills import ImmutableSkillRegistry, VaultSkillDiscoverer

registry = ImmutableSkillRegistry()
discoverer = VaultSkillDiscoverer(registry)
discoverer.scan_and_register()
result = registry.execute("system.discovery", {"params": {}})
```

## Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| params | dict | Execution parameters specific to this skill |
| context | dict | Optional context from calling agent |

## Example

```python
# Execute the skill
result = registry.execute("system.discovery", {
    "params": {},
    "context": {"source": "mission-control"}
})
print(result)
```
