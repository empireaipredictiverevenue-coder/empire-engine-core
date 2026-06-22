---
type: skill
name: system.health
version: "1.0"
description: Comprehensive health check — all services, databases, external APIs, and connectivity
tags: [system, health, monitoring]
timeout_seconds: 30
max_retries: 2
---

# system.health

Comprehensive health check — all services, databases, external APIs, and connectivity

## Overview

This skill provides capabilities for comprehensive health check — all services, databases, external apis, and connectivity.
It integrates with the Empire AI agent system through the VaultSkillDiscoverer
and ImmutableSkillRegistry.

## Capabilities

- Check connectivity to Supabase, Redis, and Ollama
- Verify API endpoints respond correctly
- Test external service integrations (Resend, Twilio, etc.)
- Generate health scorecard with red/amber/green status

## Usage

This skill is available to any agent in the Empire AI fleet with access to
the `system.health` skill. Invoke it through the skills framework:

```python
from skills import ImmutableSkillRegistry, VaultSkillDiscoverer

registry = ImmutableSkillRegistry()
discoverer = VaultSkillDiscoverer(registry)
discoverer.scan_and_register()
result = registry.execute("system.health", {"params": {}})
```

## Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| params | dict | Execution parameters specific to this skill |
| context | dict | Optional context from calling agent |

## Example

```python
# Execute the skill
result = registry.execute("system.health", {
    "params": {},
    "context": {"source": "mission-control"}
})
print(result)
```
