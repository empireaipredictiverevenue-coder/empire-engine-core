---
type: skill
name: data.cohort
version: "1.0"
description: Cohort analysis — group users by behavior and track retention over time
tags: [data, cohort, retention]
timeout_seconds: 30
max_retries: 2
---

# data.cohort

Cohort analysis — group users by behavior and track retention over time

## Overview

This skill provides capabilities for cohort analysis — group users by behavior and track retention over time.
It integrates with the Empire AI agent system through the VaultSkillDiscoverer
and ImmutableSkillRegistry.

## Capabilities

- Build cohorts by signup date or first action
- Calculate retention curves and churn rates
- Compare behavior between cohorts
- Visualize cohort heatmaps

## Usage

This skill is available to any agent in the Empire AI fleet with access to
the `data.cohort` skill. Invoke it through the skills framework:

```python
from skills import ImmutableSkillRegistry, VaultSkillDiscoverer

registry = ImmutableSkillRegistry()
discoverer = VaultSkillDiscoverer(registry)
discoverer.scan_and_register()
result = registry.execute("data.cohort", {"params": {}})
```

## Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| params | dict | Execution parameters specific to this skill |
| context | dict | Optional context from calling agent |

## Example

```python
# Execute the skill
result = registry.execute("data.cohort", {
    "params": {},
    "context": {"source": "mission-control"}
})
print(result)
```
