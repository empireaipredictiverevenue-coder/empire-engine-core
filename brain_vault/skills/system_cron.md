---
type: skill
name: system.cron
version: "1.0"
description: Cron job management — schedule, monitor, and review cron task execution
tags: [system, cron, scheduler]
timeout_seconds: 30
max_retries: 2
---

# system.cron

Cron job management — schedule, monitor, and review cron task execution

## Overview

This skill provides capabilities for cron job management — schedule, monitor, and review cron task execution.
It integrates with the Empire AI agent system through the VaultSkillDiscoverer
and ImmutableSkillRegistry.

## Capabilities

- List all cron jobs with schedules and last run times
- Check for missed or failed cron executions
- Add, modify, or disable cron entries
- Review cron output logs for errors

## Usage

This skill is available to any agent in the Empire AI fleet with access to
the `system.cron` skill. Invoke it through the skills framework:

```python
from skills import ImmutableSkillRegistry, VaultSkillDiscoverer

registry = ImmutableSkillRegistry()
discoverer = VaultSkillDiscoverer(registry)
discoverer.scan_and_register()
result = registry.execute("system.cron", {"params": {}})
```

## Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| params | dict | Execution parameters specific to this skill |
| context | dict | Optional context from calling agent |

## Example

```python
# Execute the skill
result = registry.execute("system.cron", {
    "params": {},
    "context": {"source": "mission-control"}
})
print(result)
```
