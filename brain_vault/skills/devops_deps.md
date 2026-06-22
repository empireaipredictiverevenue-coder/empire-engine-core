---
type: skill
name: devops.deps
version: "1.0"
description: Dependency audit — check for outdated, vulnerable, or unused packages
tags: [devops, dependencies, security]
timeout_seconds: 30
max_retries: 2
---

# devops.deps

Dependency audit — check for outdated, vulnerable, or unused packages

## Overview

This skill provides capabilities for dependency audit — check for outdated, vulnerable, or unused packages.
It integrates with the Empire AI agent system through the VaultSkillDiscoverer
and ImmutableSkillRegistry.

## Capabilities

- Check requirements.txt for outdated packages
- Scan for known security vulnerabilities
- Detect unused dependencies
- Recommend safe version upgrades

## Usage

This skill is available to any agent in the Empire AI fleet with access to
the `devops.deps` skill. Invoke it through the skills framework:

```python
from skills import ImmutableSkillRegistry, VaultSkillDiscoverer

registry = ImmutableSkillRegistry()
discoverer = VaultSkillDiscoverer(registry)
discoverer.scan_and_register()
result = registry.execute("devops.deps", {"params": {}})
```

## Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| params | dict | Execution parameters specific to this skill |
| context | dict | Optional context from calling agent |

## Example

```python
# Execute the skill
result = registry.execute("devops.deps", {
    "params": {},
    "context": {"source": "mission-control"}
})
print(result)
```
