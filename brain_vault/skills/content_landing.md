---
type: skill
name: content.landing
version: "1.0"
description: Landing page copy — write persuasive, conversion-optimized landing page content
tags: [content, landing, copywriting]
timeout_seconds: 30
max_retries: 2
---

# content.landing

Landing page copy — write persuasive, conversion-optimized landing page content

## Overview

This skill provides capabilities for landing page copy — write persuasive, conversion-optimized landing page content.
It integrates with the Empire AI agent system through the VaultSkillDiscoverer
and ImmutableSkillRegistry.

## Capabilities

- Write hero sections with compelling headlines
- Craft value propositions and feature lists
- Write social proof and testimonial sections
- Create strong calls-to-action

## Usage

This skill is available to any agent in the Empire AI fleet with access to
the `content.landing` skill. Invoke it through the skills framework:

```python
from skills import ImmutableSkillRegistry, VaultSkillDiscoverer

registry = ImmutableSkillRegistry()
discoverer = VaultSkillDiscoverer(registry)
discoverer.scan_and_register()
result = registry.execute("content.landing", {"params": {}})
```

## Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| params | dict | Execution parameters specific to this skill |
| context | dict | Optional context from calling agent |

## Example

```python
# Execute the skill
result = registry.execute("content.landing", {
    "params": {},
    "context": {"source": "mission-control"}
})
print(result)
```
