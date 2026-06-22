---
type: skill
name: devops.env
version: "1.0"
description: Environment setup — bootstrap development, staging, and production environments
tags: [devops, environment, setup]
timeout_seconds: 30
max_retries: 2
---

# devops.env

Environment setup — bootstrap development, staging, and production environments

## Overview

This skill provides capabilities for environment setup — bootstrap development, staging, and production environments.
It integrates with the Empire AI agent system through the VaultSkillDiscoverer
and ImmutableSkillRegistry.

## Capabilities

- Generate .env files from templates
- Install system dependencies and packages
- Initialize databases with schema
- Verify environment readiness checks

## Usage

This skill is available to any agent in the Empire AI fleet with access to
the `devops.env` skill. Invoke it through the skills framework:

```python
from skills import ImmutableSkillRegistry, VaultSkillDiscoverer

registry = ImmutableSkillRegistry()
discoverer = VaultSkillDiscoverer(registry)
discoverer.scan_and_register()
result = registry.execute("devops.env", {"params": {}})
```

## Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| params | dict | Execution parameters specific to this skill |
| context | dict | Optional context from calling agent |

## Example

```python
# Execute the skill
result = registry.execute("devops.env", {
    "params": {},
    "context": {"source": "mission-control"}
})
print(result)
```
