---
type: skill
name: system.db-backup
version: "1.0"
description: Database backup management — Supabase/Postgres snapshots and point-in-time recovery
tags: [system, database, backup]
timeout_seconds: 30
max_retries: 2
---

# system.db-backup

Database backup management — Supabase/Postgres snapshots and point-in-time recovery

## Overview

This skill provides capabilities for database backup management — supabase/postgres snapshots and point-in-time recovery.
It integrates with the Empire AI agent system through the VaultSkillDiscoverer
and ImmutableSkillRegistry.

## Capabilities

- Create manual database snapshots
- List available backup snapshots with sizes
- Verify backup integrity through restore tests
- Configure automated backup schedules

## Usage

This skill is available to any agent in the Empire AI fleet with access to
the `system.db-backup` skill. Invoke it through the skills framework:

```python
from skills import ImmutableSkillRegistry, VaultSkillDiscoverer

registry = ImmutableSkillRegistry()
discoverer = VaultSkillDiscoverer(registry)
discoverer.scan_and_register()
result = registry.execute("system.db-backup", {"params": {}})
```

## Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| params | dict | Execution parameters specific to this skill |
| context | dict | Optional context from calling agent |

## Example

```python
# Execute the skill
result = registry.execute("system.db-backup", {
    "params": {},
    "context": {"source": "mission-control"}
})
print(result)
```
