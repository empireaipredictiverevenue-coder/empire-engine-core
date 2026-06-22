---
type: skill
name: content.video
version: "1.0"
description: Video script generation — write scripts for promotional and educational videos
tags: [content, video, scripts]
timeout_seconds: 30
max_retries: 2
---

# content.video

Video script generation — write scripts for promotional and educational videos

## Overview

This skill provides capabilities for video script generation — write scripts for promotional and educational videos.
It integrates with the Empire AI agent system through the VaultSkillDiscoverer
and ImmutableSkillRegistry.

## Capabilities

- Write short-form video scripts (30-60s)
- Write long-form educational video scripts
- Generate storyboards and scene descriptions
- Include hooks, CTAs, and pacing notes

## Usage

This skill is available to any agent in the Empire AI fleet with access to
the `content.video` skill. Invoke it through the skills framework:

```python
from skills import ImmutableSkillRegistry, VaultSkillDiscoverer

registry = ImmutableSkillRegistry()
discoverer = VaultSkillDiscoverer(registry)
discoverer.scan_and_register()
result = registry.execute("content.video", {"params": {}})
```

## Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| params | dict | Execution parameters specific to this skill |
| context | dict | Optional context from calling agent |

## Example

```python
# Execute the skill
result = registry.execute("content.video", {
    "params": {},
    "context": {"source": "mission-control"}
})
print(result)
```
