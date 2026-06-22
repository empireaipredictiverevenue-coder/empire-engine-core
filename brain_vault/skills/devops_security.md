---
type: skill
name: devops.security
version: "1.0"
description: Security scan — audit code and config for security issues
tags: [devops, security, audit]
timeout_seconds: 30
max_retries: 2
---

# devops.security

Security scan — audit code and config for security issues

## Overview

This skill provides capabilities for security scan — audit code and config for security issues.
It integrates with the Empire AI agent system through the VaultSkillDiscoverer
and ImmutableSkillRegistry.

## Capabilities

- Scan for hardcoded secrets and API keys
- Check file permissions and ownership
- Audit network port exposure
- Review authentication and authorization patterns

## Usage

This skill is available to any agent in the Empire AI fleet with access to
the `devops.security` skill. Invoke it through the skills framework:

```python
from skills import ImmutableSkillRegistry, VaultSkillDiscoverer

registry = ImmutableSkillRegistry()
discoverer = VaultSkillDiscoverer(registry)
discoverer.scan_and_register()
result = registry.execute("devops.security", {"params": {}})
```

## Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| params | dict | Execution parameters specific to this skill |
| context | dict | Optional context from calling agent |

## Example

```python
# Execute the skill
result = registry.execute("devops.security", {
    "params": {},
    "context": {"source": "mission-control"}
})
print(result)
```
