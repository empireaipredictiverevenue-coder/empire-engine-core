---
type: skill
name: system.dns
version: "1.0"
description: DNS management — A, CNAME, MX, TXT records and domain health
tags: [system, dns, networking]
timeout_seconds: 30
max_retries: 2
---

# system.dns

DNS management — A, CNAME, MX, TXT records and domain health

## Overview

This skill provides capabilities for dns management — a, cname, mx, txt records and domain health.
It integrates with the Empire AI agent system through the VaultSkillDiscoverer
and ImmutableSkillRegistry.

## Capabilities

- Look up and verify DNS records
- Check propagation status across nameservers
- Validate SPF, DKIM, and DMARC records
- Troubleshoot DNS resolution issues

## Usage

This skill is available to any agent in the Empire AI fleet with access to
the `system.dns` skill. Invoke it through the skills framework:

```python
from skills import ImmutableSkillRegistry, VaultSkillDiscoverer

registry = ImmutableSkillRegistry()
discoverer = VaultSkillDiscoverer(registry)
discoverer.scan_and_register()
result = registry.execute("system.dns", {"params": {}})
```

## Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| params | dict | Execution parameters specific to this skill |
| context | dict | Optional context from calling agent |

## Example

```python
# Execute the skill
result = registry.execute("system.dns", {
    "params": {},
    "context": {"source": "mission-control"}
})
print(result)
```
