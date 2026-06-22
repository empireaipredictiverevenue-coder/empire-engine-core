---
type: skill
name: system.pm2
version: "1.0"
description: PM2 process manager — start, stop, restart, and monitor all Empire PM2 services
tags: [system, pm2, process-management]
timeout_seconds: 30
max_retries: 2
---

# system.pm2

PM2 process manager — start, stop, restart, and monitor all Empire PM2 services

## Overview

This skill provides capabilities for pm2 process manager — start, stop, restart, and monitor all empire pm2 services.
It integrates with the Empire AI agent system through the VaultSkillDiscoverer
and ImmutableSkillRegistry.

## Capabilities

- List all PM2-managed services with status
- Restart individual or all services safely
- Monitor service logs and crash history
- Auto-remediate stopped or errored services

## Usage

This skill is available to any agent in the Empire AI fleet with access to
the `system.pm2` skill. Invoke it through the skills framework:

```python
from skills import ImmutableSkillRegistry, VaultSkillDiscoverer

registry = ImmutableSkillRegistry()
discoverer = VaultSkillDiscoverer(registry)
discoverer.scan_and_register()
result = registry.execute("system.pm2", {"params": {}})
```

## Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| params | dict | Execution parameters specific to this skill |
| context | dict | Optional context from calling agent |

## Example

```python
# Execute the skill
result = registry.execute("system.pm2", {
    "params": {},
    "context": {"source": "mission-control"}
})
print(result)
```
