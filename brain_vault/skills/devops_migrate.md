---
type: skill
name: devops.migrate
version: "1.0"
description: Script migration — refactor and migrate code between patterns
tags: [devops, migration, refactoring]
timeout_seconds: 30
max_retries: 2
---

# devops.migrate

Script migration — refactor and migrate code between patterns

## Overview

This skill provides capabilities for script migration — refactor and migrate code between patterns.
It integrates with the Empire AI agent system through the VaultSkillDiscoverer
and ImmutableSkillRegistry.

## Capabilities

- Analyze migration impact and dependencies
- Generate migration scripts with rollback support
- Verify migration correctness post-deploy
- Handle data migration alongside code changes

## Usage

This skill is available to any agent in the Empire AI fleet with access to
the `devops.migrate` skill. Invoke it through the skills framework:

```python
from skills import ImmutableSkillRegistry, VaultSkillDiscoverer

registry = ImmutableSkillRegistry()
discoverer = VaultSkillDiscoverer(registry)
discoverer.scan_and_register()
result = registry.execute("devops.migrate", {"params": {}})
```

## Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| params | dict | Execution parameters specific to this skill |
| context | dict | Optional context from calling agent |

## Example

```python
# Execute the skill
result = registry.execute("devops.migrate", {
    "params": {},
    "context": {"source": "mission-control"}
})
print(result)
```
