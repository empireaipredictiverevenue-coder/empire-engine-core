---
type: skill
name: system.logs
version: "1.0"
description: Centralized log analysis — search, filter, and correlate across all Empire services
tags: [system, logs, observability]
timeout_seconds: 30
max_retries: 2
---

# system.logs

Centralized log analysis — search, filter, and correlate across all Empire services

## Overview

This skill provides capabilities for centralized log analysis — search, filter, and correlate across all empire services.
It integrates with the Empire AI agent system through the VaultSkillDiscoverer
and ImmutableSkillRegistry.

## Capabilities

- Search across all service logs by pattern and time range
- Correlate events across multiple services
- Detect error spikes and warning clusters
- Generate log digests for operator review

## Usage

This skill is available to any agent in the Empire AI fleet with access to
the `system.logs` skill. Invoke it through the skills framework:

```python
from skills import ImmutableSkillRegistry, VaultSkillDiscoverer

registry = ImmutableSkillRegistry()
discoverer = VaultSkillDiscoverer(registry)
discoverer.scan_and_register()
result = registry.execute("system.logs", {"params": {}})
```

## Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| params | dict | Execution parameters specific to this skill |
| context | dict | Optional context from calling agent |

## Example

```python
# Execute the skill
result = registry.execute("system.logs", {
    "params": {},
    "context": {"source": "mission-control"}
})
print(result)
```
