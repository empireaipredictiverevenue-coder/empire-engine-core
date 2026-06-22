---
type: skill
name: contractor.match
version: "1.0"
description: Contractor matching — match leads to the best-fit contractors by location and niche
tags: [contractor, matching, dispatch]
timeout_seconds: 30
max_retries: 2
---

# contractor.match

Contractor matching — match leads to the best-fit contractors by location and niche

## Overview

This skill provides capabilities for contractor matching — match leads to the best-fit contractors by location and niche.
It integrates with the Empire AI agent system through the VaultSkillDiscoverer
and ImmutableSkillRegistry.

## Capabilities

- Match leads to contractors by metro and niche
- Score match quality based on multiple factors
- Optimize for response rate and conversion
- Handle overflow and fallback routing

## Usage

This skill is available to any agent in the Empire AI fleet with access to
the `contractor.match` skill. Invoke it through the skills framework:

```python
from skills import ImmutableSkillRegistry, VaultSkillDiscoverer

registry = ImmutableSkillRegistry()
discoverer = VaultSkillDiscoverer(registry)
discoverer.scan_and_register()
result = registry.execute("contractor.match", {"params": {}})
```

## Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| params | dict | Execution parameters specific to this skill |
| context | dict | Optional context from calling agent |

## Example

```python
# Execute the skill
result = registry.execute("contractor.match", {
    "params": {},
    "context": {"source": "mission-control"}
})
print(result)
```
