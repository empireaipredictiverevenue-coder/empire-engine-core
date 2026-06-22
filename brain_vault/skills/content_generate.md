---
type: skill
name: content.generate
version: "1.0"
description: Content generation — create high-quality written content with AI
tags: [content, generation, ai]
timeout_seconds: 30
max_retries: 2
---

# content.generate

Content generation — create high-quality written content with AI

## Overview

This skill provides capabilities for content generation — create high-quality written content with ai.
It integrates with the Empire AI agent system through the VaultSkillDiscoverer
and ImmutableSkillRegistry.

## Capabilities

- Generate blog posts and articles from outlines
- Create social media posts for multiple platforms
- Write landing page copy with conversion focus
- Produce email sequences and newsletters

## Usage

This skill is available to any agent in the Empire AI fleet with access to
the `content.generate` skill. Invoke it through the skills framework:

```python
from skills import ImmutableSkillRegistry, VaultSkillDiscoverer

registry = ImmutableSkillRegistry()
discoverer = VaultSkillDiscoverer(registry)
discoverer.scan_and_register()
result = registry.execute("content.generate", {"params": {}})
```

## Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| params | dict | Execution parameters specific to this skill |
| context | dict | Optional context from calling agent |

## Example

```python
# Execute the skill
result = registry.execute("content.generate", {
    "params": {},
    "context": {"source": "mission-control"}
})
print(result)
```
