---
type: skill
name: data.timeseries
version: "1.0"
description: Time series analysis — sliding windows, rolling averages, and period comparisons
tags: [data, timeseries, analytics]
timeout_seconds: 30
max_retries: 2
---

# data.timeseries

Time series analysis — sliding windows, rolling averages, and period comparisons

## Overview

This skill provides capabilities for time series analysis — sliding windows, rolling averages, and period comparisons.
It integrates with the Empire AI agent system through the VaultSkillDiscoverer
and ImmutableSkillRegistry.

## Capabilities

- Compute rolling averages and moving medians
- Compare current period to previous periods
- Calculate compound growth rates
- Forecast forward using naive and trend methods

## Usage

This skill is available to any agent in the Empire AI fleet with access to
the `data.timeseries` skill. Invoke it through the skills framework:

```python
from skills import ImmutableSkillRegistry, VaultSkillDiscoverer

registry = ImmutableSkillRegistry()
discoverer = VaultSkillDiscoverer(registry)
discoverer.scan_and_register()
result = registry.execute("data.timeseries", {"params": {}})
```

## Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| params | dict | Execution parameters specific to this skill |
| context | dict | Optional context from calling agent |

## Example

```python
# Execute the skill
result = registry.execute("data.timeseries", {
    "params": {},
    "context": {"source": "mission-control"}
})
print(result)
```
