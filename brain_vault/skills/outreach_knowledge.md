---
type: skill
name: outreach.knowledge
version: "1.0"
description: Knowledge base management — build, search, and maintain internal documentation
tags: [outreach, knowledge, docs]
timeout_seconds: 30
max_retries: 2
---

# outreach.knowledge

Knowledge base management — build, search, and maintain internal documentation

## Overview

This skill provides capabilities for knowledge base management — build, search, and maintain internal documentation.
It integrates with the Empire AI agent system through the VaultSkillDiscoverer
and ImmutableSkillRegistry.

## Capabilities

- Create and organize knowledge base articles
- Full-text search across all documentation
- Track article views and usefulness ratings
- Archive and prune outdated content

## Usage

This skill is available to any agent in the Empire AI fleet with access to
the `outreach.knowledge` skill. Invoke it through the skills framework:

```python
from skills import ImmutableSkillRegistry, VaultSkillDiscoverer

registry = ImmutableSkillRegistry()
discoverer = VaultSkillDiscoverer(registry)
discoverer.scan_and_register()
result = registry.execute("outreach.knowledge", {"params": {}})
```

## Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| params | dict | Execution parameters specific to this skill |
| context | dict | Optional context from calling agent |

## Example

```python
# Execute the skill
result = registry.execute("outreach.knowledge", {
    "params": {},
    "context": {"source": "mission-control"}
})
print(result)
```
