---
type: skill
name: devops.api-docs
version: "1.0"
description: API documentation — generate and maintain API endpoint documentation
tags: [devops, api, documentation]
timeout_seconds: 30
max_retries: 2
---

# devops.api-docs

API documentation — generate and maintain API endpoint documentation

## Overview

This skill provides capabilities for api documentation — generate and maintain api endpoint documentation.
It integrates with the Empire AI agent system through the VaultSkillDiscoverer
and ImmutableSkillRegistry.

## Capabilities

- Generate OpenAPI/Swagger docs from FastAPI routes
- Write endpoint descriptions and parameter docs
- Create API usage examples with curl
- Document request/response schemas

## Usage

This skill is available to any agent in the Empire AI fleet with access to
the `devops.api-docs` skill. Invoke it through the skills framework:

```python
from skills import ImmutableSkillRegistry, VaultSkillDiscoverer

registry = ImmutableSkillRegistry()
discoverer = VaultSkillDiscoverer(registry)
discoverer.scan_and_register()
result = registry.execute("devops.api-docs", {"params": {}})
```

## Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| params | dict | Execution parameters specific to this skill |
| context | dict | Optional context from calling agent |

## Example

```python
# Execute the skill
result = registry.execute("devops.api-docs", {
    "params": {},
    "context": {"source": "mission-control"}
})
print(result)
```
