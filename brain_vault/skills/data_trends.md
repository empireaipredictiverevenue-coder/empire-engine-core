---
type: skill
name: data.trends
version: "1.0"
description: Trend analysis — identify patterns, seasonality, and shifts in time-series data
tags: [data, trends, analytics]
timeout_seconds: 30
max_retries: 2
---

# data.trends

Trend analysis — identify patterns, seasonality, and shifts in time-series data

## Overview

This skill provides capabilities for trend analysis — identify patterns, seasonality, and shifts in time-series data.
It integrates with the Empire AI agent system through the VaultSkillDiscoverer
and ImmutableSkillRegistry.

## Capabilities

- Detect upward and downward trends in metrics
- Identify seasonal patterns and day-of-week effects
- Spot sudden shifts and changepoints
- Visualize trend lines with confidence bands

## Usage

This skill is available to any agent in the Empire AI fleet with access to
the `data.trends` skill. Invoke it through the skills framework:

```python
from skills import ImmutableSkillRegistry, VaultSkillDiscoverer

registry = ImmutableSkillRegistry()
discoverer = VaultSkillDiscoverer(registry)
discoverer.scan_and_register()
result = registry.execute("data.trends", {"params": {}})
```

## Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| params | dict | Execution parameters specific to this skill |
| context | dict | Optional context from calling agent |

## Example

```python
# Execute the skill
result = registry.execute("data.trends", {
    "params": {},
    "context": {"source": "mission-control"}
})
print(result)
```
