---
type: skill
name: outreach.multichannel
version: "1.0"
description: Multi-channel orchestration — coordinate outreach across SMS, email, and voice
tags: [outreach, multi-channel, orchestration]
timeout_seconds: 30
max_retries: 2
---

# outreach.multichannel

Multi-channel orchestration — coordinate outreach across SMS, email, and voice

## Overview

This skill provides capabilities for multi-channel orchestration — coordinate outreach across sms, email, and voice.
It integrates with the Empire AI agent system through the VaultSkillDiscoverer
and ImmutableSkillRegistry.

## Capabilities

- Design multi-channel outreach sequences
- Auto-select best channel based on lead preferences
- Prevent cross-channel message conflicts
- Unified analytics across all channels

## Usage

This skill is available to any agent in the Empire AI fleet with access to
the `outreach.multichannel` skill. Invoke it through the skills framework:

```python
from skills import ImmutableSkillRegistry, VaultSkillDiscoverer

registry = ImmutableSkillRegistry()
discoverer = VaultSkillDiscoverer(registry)
discoverer.scan_and_register()
result = registry.execute("outreach.multichannel", {"params": {}})
```

## Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| params | dict | Execution parameters specific to this skill |
| context | dict | Optional context from calling agent |

## Example

```python
# Execute the skill
result = registry.execute("outreach.multichannel", {
    "params": {},
    "context": {"source": "mission-control"}
})
print(result)
```
