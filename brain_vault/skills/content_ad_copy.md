---
type: skill
name: content.ad-copy
version: "1.0"
description: Ad copy generation — create ads for Facebook, Google, and native platforms
tags: [content, ads, copywriting]
timeout_seconds: 30
max_retries: 2
---

# content.ad-copy

Ad copy generation — create ads for Facebook, Google, and native platforms

## Overview

This skill provides capabilities for ad copy generation — create ads for facebook, google, and native platforms.
It integrates with the Empire AI agent system through the VaultSkillDiscoverer
and ImmutableSkillRegistry.

## Capabilities

- Generate Facebook ad headlines and descriptions
- Write Google Ads copy with keyword integration
- Create native ad content for content discovery
- A/B test ad copy variations

## Usage

This skill is available to any agent in the Empire AI fleet with access to
the `content.ad-copy` skill. Invoke it through the skills framework:

```python
from skills import ImmutableSkillRegistry, VaultSkillDiscoverer

registry = ImmutableSkillRegistry()
discoverer = VaultSkillDiscoverer(registry)
discoverer.scan_and_register()
result = registry.execute("content.ad-copy", {"params": {}})
```

## Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| params | dict | Execution parameters specific to this skill |
| context | dict | Optional context from calling agent |

## Example

```python
# Execute the skill
result = registry.execute("content.ad-copy", {
    "params": {},
    "context": {"source": "mission-control"}
})
print(result)
```
