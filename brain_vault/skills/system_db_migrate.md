---
type: skill
name: system.db-migrate
version: "1.0"
description: Database migration runner — apply, rollback, and verify schema migrations
tags: [system, database, migrations]
timeout_seconds: 30
max_retries: 2
---

# system.db-migrate

Database migration runner — apply, rollback, and verify schema migrations

## Overview

This skill provides capabilities for database migration runner — apply, rollback, and verify schema migrations.
It integrates with the Empire AI agent system through the VaultSkillDiscoverer
and ImmutableSkillRegistry.

## Capabilities

- List pending and applied migrations
- Apply new migrations in dependency order
- Roll back the most recent migration
- Verify migration state consistency

## Usage

This skill is available to any agent in the Empire AI fleet with access to
the `system.db-migrate` skill. Invoke it through the skills framework:

```python
from skills import ImmutableSkillRegistry, VaultSkillDiscoverer

registry = ImmutableSkillRegistry()
discoverer = VaultSkillDiscoverer(registry)
discoverer.scan_and_register()
result = registry.execute("system.db-migrate", {"params": {}})
```

## Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| params | dict | Execution parameters specific to this skill |
| context | dict | Optional context from calling agent |

## Example

```python
# Execute the skill
result = registry.execute("system.db-migrate", {
    "params": {},
    "context": {"source": "mission-control"}
})
print(result)
```
