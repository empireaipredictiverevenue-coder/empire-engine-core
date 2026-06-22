---
type: skill
name: contractor.dispatch
version: "1.0"
description: Dispatch optimization — tune dispatch parameters for max contractor response
tags: [contractor, dispatch, optimization]
timeout_seconds: 30
max_retries: 2
---

# contractor.dispatch

Dispatch optimization — tune dispatch parameters for max contractor response

## Overview

This skill provides capabilities for dispatch optimization — tune dispatch parameters for max contractor response.
It integrates with the Empire AI agent system through the VaultSkillDiscoverer
and ImmutableSkillRegistry.

## Capabilities

- Analyze dispatch response rates by channel
- Optimize dispatch timing and message content
- Balance workload across contractor pool
- Monitor dispatch health and circuit breakers

## Usage

This skill is available to any agent in the Empire AI fleet with access to
the `contractor.dispatch` skill. Invoke it through the skills framework:

```python
from skills import ImmutableSkillRegistry, VaultSkillDiscoverer

registry = ImmutableSkillRegistry()
discoverer = VaultSkillDiscoverer(registry)
discoverer.scan_and_register()
result = registry.execute("contractor.dispatch", {"params": {}})
```

## Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| params | dict | Execution parameters specific to this skill |
| context | dict | Optional context from calling agent |

## Example

```python
# Execute the skill
result = registry.execute("contractor.dispatch", {
    "params": {},
    "context": {"source": "mission-control"}
})
print(result)
```
