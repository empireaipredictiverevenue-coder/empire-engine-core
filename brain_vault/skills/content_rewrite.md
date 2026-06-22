---
type: skill
name: content.rewrite
version: "1.0"
description: Content rewriting — rephrase, simplify, or expand existing content
tags: [content, rewriting, editing]
timeout_seconds: 30
max_retries: 2
---

# content.rewrite

Content rewriting — rephrase, simplify, or expand existing content

## Overview

This skill provides capabilities for content rewriting — rephrase, simplify, or expand existing content.
It integrates with the Empire AI agent system through the VaultSkillDiscoverer
and ImmutableSkillRegistry.

## Capabilities

- Rephrase content for different reading levels
- Simplify technical language for general audiences
- Expand short content into comprehensive pieces
- Adapt content for different platforms and formats

## Usage

This skill is available to any agent in the Empire AI fleet with access to
the `content.rewrite` skill. Invoke it through the skills framework:

```python
from skills import ImmutableSkillRegistry, VaultSkillDiscoverer

registry = ImmutableSkillRegistry()
discoverer = VaultSkillDiscoverer(registry)
discoverer.scan_and_register()
result = registry.execute("content.rewrite", {"params": {}})
```

## Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| params | dict | Execution parameters specific to this skill |
| context | dict | Optional context from calling agent |

## Example

```python
# Execute the skill
result = registry.execute("content.rewrite", {
    "params": {},
    "context": {"source": "mission-control"}
})
print(result)
```
