---
type: skill
name: system.nginx
version: "1.0"
description: Nginx configuration and management — sites, proxies, SSL, and rewrites
tags: [system, nginx, web-server]
timeout_seconds: 30
max_retries: 2
---

# system.nginx

Nginx configuration and management — sites, proxies, SSL, and rewrites

## Overview

This skill provides capabilities for nginx configuration and management — sites, proxies, ssl, and rewrites.
It integrates with the Empire AI agent system through the VaultSkillDiscoverer
and ImmutableSkillRegistry.

## Capabilities

- Validate and reload nginx configurations
- Manage site-enabled and available configs
- Configure reverse proxies and load balancing
- Check SSL certificate expiry and renewal status

## Usage

This skill is available to any agent in the Empire AI fleet with access to
the `system.nginx` skill. Invoke it through the skills framework:

```python
from skills import ImmutableSkillRegistry, VaultSkillDiscoverer

registry = ImmutableSkillRegistry()
discoverer = VaultSkillDiscoverer(registry)
discoverer.scan_and_register()
result = registry.execute("system.nginx", {"params": {}})
```

## Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| params | dict | Execution parameters specific to this skill |
| context | dict | Optional context from calling agent |

## Example

```python
# Execute the skill
result = registry.execute("system.nginx", {
    "params": {},
    "context": {"source": "mission-control"}
})
print(result)
```
