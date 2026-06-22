---
type: skill
name: system.deploy
version: "1.0"
description: Deployment automation — push code, run migrations, restart services
tags: [system, deployment, cicd]
timeout_seconds: 30
max_retries: 2
---

# system.deploy

Deployment automation — push code, run migrations, restart services

## Overview

This skill provides capabilities for deployment automation — push code, run migrations, restart services.
It integrates with the Empire AI agent system through the VaultSkillDiscoverer
and ImmutableSkillRegistry.

## Capabilities

- Pull latest code from git and run deploy scripts
- Execute database migrations safely
- Roll back failed deployments
- Verify deployment health post-deploy

## Usage

This skill is available to any agent in the Empire AI fleet with access to
the `system.deploy` skill. Invoke it through the skills framework:

```python
from skills import ImmutableSkillRegistry, VaultSkillDiscoverer

registry = ImmutableSkillRegistry()
discoverer = VaultSkillDiscoverer(registry)
discoverer.scan_and_register()
result = registry.execute("system.deploy", {"params": {}})
```

## Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| params | dict | Execution parameters specific to this skill |
| context | dict | Optional context from calling agent |

## Example

```python
# Execute the skill
result = registry.execute("system.deploy", {
    "params": {},
    "context": {"source": "mission-control"}
})
print(result)
```
