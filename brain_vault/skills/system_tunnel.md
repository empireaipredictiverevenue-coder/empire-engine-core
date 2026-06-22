---
type: skill
name: system.tunnel
version: "1.0"
description: Tunnel and VPN management — secure remote access and port forwarding
tags: [system, tunnel, networking]
timeout_seconds: 30
max_retries: 2
---

# system.tunnel

Tunnel and VPN management — secure remote access and port forwarding

## Overview

This skill provides capabilities for tunnel and vpn management — secure remote access and port forwarding.
It integrates with the Empire AI agent system through the VaultSkillDiscoverer
and ImmutableSkillRegistry.

## Capabilities

- Establish SSH tunnels for secure access
- Manage WireGuard VPN peers and configs
- Monitor tunnel connectivity and latency
- Auto-reconnect failed tunnels

## Usage

This skill is available to any agent in the Empire AI fleet with access to
the `system.tunnel` skill. Invoke it through the skills framework:

```python
from skills import ImmutableSkillRegistry, VaultSkillDiscoverer

registry = ImmutableSkillRegistry()
discoverer = VaultSkillDiscoverer(registry)
discoverer.scan_and_register()
result = registry.execute("system.tunnel", {"params": {}})
```

## Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| params | dict | Execution parameters specific to this skill |
| context | dict | Optional context from calling agent |

## Example

```python
# Execute the skill
result = registry.execute("system.tunnel", {
    "params": {},
    "context": {"source": "mission-control"}
})
print(result)
```
