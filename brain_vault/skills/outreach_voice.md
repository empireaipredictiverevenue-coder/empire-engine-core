---
type: skill
name: outreach.voice
version: "1.0"
description: Voice call management — orchestrate outbound voice calls with AI scripts
tags: [outreach, voice, calls]
timeout_seconds: 30
max_retries: 2
---

# outreach.voice

Voice call management — orchestrate outbound voice calls with AI scripts

## Overview

This skill provides capabilities for voice call management — orchestrate outbound voice calls with ai scripts.
It integrates with the Empire AI agent system through the VaultSkillDiscoverer
and ImmutableSkillRegistry.

## Capabilities

- Initiate AI-powered outbound calls
- Manage call queues and pacing
- Transcribe and analyze call recordings
- Track call outcomes and conversion rates

## Usage

This skill is available to any agent in the Empire AI fleet with access to
the `outreach.voice` skill. Invoke it through the skills framework:

```python
from skills import ImmutableSkillRegistry, VaultSkillDiscoverer

registry = ImmutableSkillRegistry()
discoverer = VaultSkillDiscoverer(registry)
discoverer.scan_and_register()
result = registry.execute("outreach.voice", {"params": {}})
```

## Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| params | dict | Execution parameters specific to this skill |
| context | dict | Optional context from calling agent |

## Example

```python
# Execute the skill
result = registry.execute("outreach.voice", {
    "params": {},
    "context": {"source": "mission-control"}
})
print(result)
```
