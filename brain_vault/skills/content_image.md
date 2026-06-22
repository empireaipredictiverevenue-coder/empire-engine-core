---
type: skill
name: content.image
version: "1.0"
description: Image prompt generation — create prompts for AI image generation
tags: [content, image, ai]
timeout_seconds: 30
max_retries: 2
---

# content.image

Image prompt generation — create prompts for AI image generation

## Overview

This skill provides capabilities for image prompt generation — create prompts for ai image generation.
It integrates with the Empire AI agent system through the VaultSkillDiscoverer
and ImmutableSkillRegistry.

## Capabilities

- Generate detailed image prompts for AI tools
- Design visual concepts from text descriptions
- Suggest image styles and compositions
- Adapt prompts for different AI image generators

## Usage

This skill is available to any agent in the Empire AI fleet with access to
the `content.image` skill. Invoke it through the skills framework:

```python
from skills import ImmutableSkillRegistry, VaultSkillDiscoverer

registry = ImmutableSkillRegistry()
discoverer = VaultSkillDiscoverer(registry)
discoverer.scan_and_register()
result = registry.execute("content.image", {"params": {}})
```

## Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| params | dict | Execution parameters specific to this skill |
| context | dict | Optional context from calling agent |

## Example

```python
# Execute the skill
result = registry.execute("content.image", {
    "params": {},
    "context": {"source": "mission-control"}
})
print(result)
```
