---
type: skill
name: system.incident
version: "1.0"
description: Incident response — track, diagnose, and resolve production incidents
tags: [system, incident, response]
timeout_seconds: 30
max_retries: 2
---

# system.incident

Incident response — track, diagnose, and resolve production incidents

## Overview

This skill provides capabilities for incident response — track, diagnose, and resolve production incidents.
It integrates with the Empire AI agent system through the VaultSkillDiscoverer
and ImmutableSkillRegistry.

## Capabilities

- Create and track incident timelines
- Document root cause analysis and resolution steps
- Link incidents to related alerts and log entries
- Generate post-mortem reports

## Usage

This skill is available to any agent in the Empire AI fleet with access to
the `system.incident` skill. Invoke it through the skills framework:

```python
from skills import ImmutableSkillRegistry, VaultSkillDiscoverer

registry = ImmutableSkillRegistry()
discoverer = VaultSkillDiscoverer(registry)
discoverer.scan_and_register()
result = registry.execute("system.incident", {"params": {}})
```

## Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| params | dict | Execution parameters specific to this skill |
| context | dict | Optional context from calling agent |

## Example

```python
# Execute the skill
result = registry.execute("system.incident", {
    "params": {},
    "context": {"source": "mission-control"}
})
print(result)
```
