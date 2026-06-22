---
type: skill
name: content.translate
version: "1.0"
description: Translation — translate content between supported languages
tags: [content, translation, languages]
timeout_seconds: 30
max_retries: 2
---

# content.translate

Translation — translate content between supported languages

## Overview

This skill provides capabilities for translation — translate content between supported languages.
It integrates with the Empire AI agent system through the VaultSkillDiscoverer
and ImmutableSkillRegistry.

## Capabilities

- Translate content with context preservation
- Localize tone and cultural references
- Translate technical and niche terminology
- Maintain formatting in translated output

## Usage

This skill is available to any agent in the Empire AI fleet with access to
the `content.translate` skill. Invoke it through the skills framework:

```python
from skills import ImmutableSkillRegistry, VaultSkillDiscoverer

registry = ImmutableSkillRegistry()
discoverer = VaultSkillDiscoverer(registry)
discoverer.scan_and_register()
result = registry.execute("content.translate", {"params": {}})
```

## Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| params | dict | Execution parameters specific to this skill |
| context | dict | Optional context from calling agent |

## Example

```python
# Execute the skill
result = registry.execute("content.translate", {
    "params": {},
    "context": {"source": "mission-control"}
})
print(result)
```
