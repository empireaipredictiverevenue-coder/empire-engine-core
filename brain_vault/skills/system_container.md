---
type: skill
name: system.container
version: "1.0"
description: Docker container management — build, run, monitor, and clean up containers
tags: [system, docker, containers]
timeout_seconds: 30
max_retries: 2
---

# system.container

Docker container management — build, run, monitor, and clean up containers

## Overview

This skill provides capabilities for docker container management — build, run, monitor, and clean up containers.
It integrates with the Empire AI agent system through the VaultSkillDiscoverer
and ImmutableSkillRegistry.

## Capabilities

- List running and stopped containers
- Build images from Dockerfiles and docker-compose
- Monitor container logs and resource usage
- Clean up unused images, volumes, and networks

## Usage

This skill is available to any agent in the Empire AI fleet with access to
the `system.container` skill. Invoke it through the skills framework:

```python
from skills import ImmutableSkillRegistry, VaultSkillDiscoverer

registry = ImmutableSkillRegistry()
discoverer = VaultSkillDiscoverer(registry)
discoverer.scan_and_register()
result = registry.execute("system.container", {"params": {}})
```

## Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| params | dict | Execution parameters specific to this skill |
| context | dict | Optional context from calling agent |

## Example

```python
# Execute the skill
result = registry.execute("system.container", {
    "params": {},
    "context": {"source": "mission-control"}
})
print(result)
```
