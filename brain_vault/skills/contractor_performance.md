---
type: skill
name: contractor.performance
version: "1.0"
description: Performance tracking — monitor contractor metrics, ratings, and reliability
tags: [contractor, performance, analytics]
timeout_seconds: 30
max_retries: 2
---

# contractor.performance

Performance tracking — monitor contractor metrics, ratings, and reliability

## Overview

This skill provides capabilities for performance tracking — monitor contractor metrics, ratings, and reliability.
It integrates with the Empire AI agent system through the VaultSkillDiscoverer
and ImmutableSkillRegistry.

## Capabilities

- Track contractor response and acceptance rates
- Score contractor reliability and quality
- Compare performance across niches and metros
- Generate contractor scorecards

## Usage

This skill is available to any agent in the Empire AI fleet with access to
the `contractor.performance` skill. Invoke it through the skills framework:

```python
from skills import ImmutableSkillRegistry, VaultSkillDiscoverer

registry = ImmutableSkillRegistry()
discoverer = VaultSkillDiscoverer(registry)
discoverer.scan_and_register()
result = registry.execute("contractor.performance", {"params": {}})
```

## Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| params | dict | Execution parameters specific to this skill |
| context | dict | Optional context from calling agent |

## Example

```python
# Execute the skill
result = registry.execute("contractor.performance", {
    "params": {},
    "context": {"source": "mission-control"}
})
print(result)
```
