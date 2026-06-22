---
type: skill
name: system.secrets
version: "1.0"
description: Secrets management — rotate, audit, and secure API keys and credentials
tags: [system, secrets, security]
timeout_seconds: 30
max_retries: 2
---

# system.secrets

Secrets management — rotate, audit, and secure API keys and credentials

## Overview

This skill provides capabilities for secrets management — rotate, audit, and secure api keys and credentials.
It integrates with the Empire AI agent system through the VaultSkillDiscoverer
and ImmutableSkillRegistry.

## Capabilities

- List configured env vars and their sources
- Rotate API keys and regenerate credentials
- Audit secret usage across all services
- Detect exposed or compromised secrets

## Usage

This skill is available to any agent in the Empire AI fleet with access to
the `system.secrets` skill. Invoke it through the skills framework:

```python
from skills import ImmutableSkillRegistry, VaultSkillDiscoverer

registry = ImmutableSkillRegistry()
discoverer = VaultSkillDiscoverer(registry)
discoverer.scan_and_register()
result = registry.execute("system.secrets", {"params": {}})
```

## Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| params | dict | Execution parameters specific to this skill |
| context | dict | Optional context from calling agent |

## Example

```python
# Execute the skill
result = registry.execute("system.secrets", {
    "params": {},
    "context": {"source": "mission-control"}
})
print(result)
```
