---
type: skill
name: system.backup
version: "1.0"
description: Backup and restore — databases, configs, and critical data
tags: [system, backup, disaster-recovery]
timeout_seconds: 30
max_retries: 2
---

# system.backup

Backup and restore — databases, configs, and critical data

## Overview

This skill provides capabilities for backup and restore — databases, configs, and critical data.
It integrates with the Empire AI agent system through the VaultSkillDiscoverer
and ImmutableSkillRegistry.

## Capabilities

- Schedule and execute database backups
- Backup configuration files and env vars
- Restore from verified backup snapshots
- List available backups with timestamps

## Usage

This skill is available to any agent in the Empire AI fleet with access to
the `system.backup` skill. Invoke it through the skills framework:

```python
from skills import ImmutableSkillRegistry, VaultSkillDiscoverer

registry = ImmutableSkillRegistry()
discoverer = VaultSkillDiscoverer(registry)
discoverer.scan_and_register()
result = registry.execute("system.backup", {"params": {}})
```

## Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| params | dict | Execution parameters specific to this skill |
| context | dict | Optional context from calling agent |

## Example

```python
# Execute the skill
result = registry.execute("system.backup", {
    "params": {},
    "context": {"source": "mission-control"}
})
print(result)
```
