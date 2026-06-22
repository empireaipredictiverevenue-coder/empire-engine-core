---
type: skill
name: outreach.broadcast
version: "1.0"
description: Broadcast messaging — send one-to-many messages across all channels
tags: [outreach, broadcast, messaging]
timeout_seconds: 30
max_retries: 2
---

# outreach.broadcast

Broadcast messaging — send one-to-many messages across all channels

## Overview

This skill provides capabilities for broadcast messaging — send one-to-many messages across all channels.
It integrates with the Empire AI agent system through the VaultSkillDiscoverer
and ImmutableSkillRegistry.

## Capabilities

- Compose broadcast messages with personalization
- Segment recipients by location, niche, or behavior
- Schedule broadcast delivery windows
- Track broadcast performance metrics

## Usage

This skill is available to any agent in the Empire AI fleet with access to
the `outreach.broadcast` skill. Invoke it through the skills framework:

```python
from skills import ImmutableSkillRegistry, VaultSkillDiscoverer

registry = ImmutableSkillRegistry()
discoverer = VaultSkillDiscoverer(registry)
discoverer.scan_and_register()
result = registry.execute("outreach.broadcast", {"params": {}})
```

## Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| params | dict | Execution parameters specific to this skill |
| context | dict | Optional context from calling agent |

## Example

```python
# Execute the skill
result = registry.execute("outreach.broadcast", {
    "params": {},
    "context": {"source": "mission-control"}
})
print(result)
```
