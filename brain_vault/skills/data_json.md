---
type: skill
name: data.json
version: "1.0"
description: JSON processing — query, transform, and validate JSON documents
tags: [data, json, processing]
timeout_seconds: 30
max_retries: 2
---

# data.json

JSON processing — query, transform, and validate JSON documents

## Overview

This skill provides capabilities for json processing — query, transform, and validate json documents.
It integrates with the Empire AI agent system through the VaultSkillDiscoverer
and ImmutableSkillRegistry.

## Capabilities

- Query nested JSON with JMESPath or jq expressions
- Transform JSON documents between schemas
- Validate JSON against JSON Schema definitions
- Merge and diff JSON documents

## Usage

This skill is available to any agent in the Empire AI fleet with access to
the `data.json` skill. Invoke it through the skills framework:

```python
from skills import ImmutableSkillRegistry, VaultSkillDiscoverer

registry = ImmutableSkillRegistry()
discoverer = VaultSkillDiscoverer(registry)
discoverer.scan_and_register()
result = registry.execute("data.json", {"params": {}})
```

## Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| params | dict | Execution parameters specific to this skill |
| context | dict | Optional context from calling agent |

## Example

```python
# Execute the skill
result = registry.execute("data.json", {
    "params": {},
    "context": {"source": "mission-control"}
})
print(result)
```
