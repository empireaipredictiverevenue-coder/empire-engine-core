---
type: skill
name: system.ssl
version: "1.0"
description: SSL/TLS certificate management — issuance, renewal, and validation
tags: [system, ssl, security]
timeout_seconds: 30
max_retries: 2
---

# system.ssl

SSL/TLS certificate management — issuance, renewal, and validation

## Overview

This skill provides capabilities for ssl/tls certificate management — issuance, renewal, and validation.
It integrates with the Empire AI agent system through the VaultSkillDiscoverer
and ImmutableSkillRegistry.

## Capabilities

- Check certificate expiry dates across all domains
- Auto-renew Let's Encrypt certificates
- Validate certificate chain and cipher strength
- Alert on certificates expiring within 30 days

## Usage

This skill is available to any agent in the Empire AI fleet with access to
the `system.ssl` skill. Invoke it through the skills framework:

```python
from skills import ImmutableSkillRegistry, VaultSkillDiscoverer

registry = ImmutableSkillRegistry()
discoverer = VaultSkillDiscoverer(registry)
discoverer.scan_and_register()
result = registry.execute("system.ssl", {"params": {}})
```

## Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| params | dict | Execution parameters specific to this skill |
| context | dict | Optional context from calling agent |

## Example

```python
# Execute the skill
result = registry.execute("system.ssl", {
    "params": {},
    "context": {"source": "mission-control"}
})
print(result)
```
