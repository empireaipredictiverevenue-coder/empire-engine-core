---
type: skill
name: data.funnel
version: "1.0"
description: Funnel analysis — track conversion through multi-stage pipelines
tags: [data, funnel, conversion]
timeout_seconds: 30
max_retries: 2
---

# data.funnel

Funnel analysis — track conversion through multi-stage pipelines

## Overview

This skill provides capabilities for funnel analysis — track conversion through multi-stage pipelines.
It integrates with the Empire AI agent system through the VaultSkillDiscoverer
and ImmutableSkillRegistry.

## Capabilities

- Define funnel stages from any data source
- Calculate stage-by-stage conversion rates
- Identify biggest drop-off points in the funnel
- Segment funnel performance by cohort

## Usage

This skill is available to any agent in the Empire AI fleet with access to
the `data.funnel` skill. Invoke it through the skills framework:

```python
from skills import ImmutableSkillRegistry, VaultSkillDiscoverer

registry = ImmutableSkillRegistry()
discoverer = VaultSkillDiscoverer(registry)
discoverer.scan_and_register()
result = registry.execute("data.funnel", {"params": {}})
```

## Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| params | dict | Execution parameters specific to this skill |
| context | dict | Optional context from calling agent |

## Example

```python
# Execute the skill
result = registry.execute("data.funnel", {
    "params": {},
    "context": {"source": "mission-control"}
})
print(result)
```
