---
type: skill
name: content.meta
version: "1.0"
description: Meta tag generation — create title tags, descriptions, and OG tags
tags: [content, meta, seo]
timeout_seconds: 30
max_retries: 2
---

# content.meta

Meta tag generation — create title tags, descriptions, and OG tags

## Overview

This skill provides capabilities for meta tag generation — create title tags, descriptions, and og tags.
It integrates with the Empire AI agent system through the VaultSkillDiscoverer
and ImmutableSkillRegistry.

## Capabilities

- Generate SEO-optimized title tags
- Write compelling meta descriptions
- Create Open Graph and Twitter Card tags
- Optimize meta for click-through rate

## Usage

This skill is available to any agent in the Empire AI fleet with access to
the `content.meta` skill. Invoke it through the skills framework:

```python
from skills import ImmutableSkillRegistry, VaultSkillDiscoverer

registry = ImmutableSkillRegistry()
discoverer = VaultSkillDiscoverer(registry)
discoverer.scan_and_register()
result = registry.execute("content.meta", {"params": {}})
```

## Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| params | dict | Execution parameters specific to this skill |
| context | dict | Optional context from calling agent |

## Example

```python
# Execute the skill
result = registry.execute("content.meta", {
    "params": {},
    "context": {"source": "mission-control"}
})
print(result)
```
