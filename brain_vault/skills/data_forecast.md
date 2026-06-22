---
type: skill
name: data.forecast
version: "1.0"
description: Forecasting — predict future values using statistical and ML methods
tags: [data, forecast, prediction]
timeout_seconds: 30
max_retries: 2
---

# data.forecast

Forecasting — predict future values using statistical and ML methods

## Overview

This skill provides capabilities for forecasting — predict future values using statistical and ml methods.
It integrates with the Empire AI agent system through the VaultSkillDiscoverer
and ImmutableSkillRegistry.

## Capabilities

- Generate time-series forecasts with confidence intervals
- Apply seasonal decomposition to historical data
- Use linear, exponential, and ARIMA forecasting
- Compare forecast accuracy against actuals

## Usage

This skill is available to any agent in the Empire AI fleet with access to
the `data.forecast` skill. Invoke it through the skills framework:

```python
from skills import ImmutableSkillRegistry, VaultSkillDiscoverer

registry = ImmutableSkillRegistry()
discoverer = VaultSkillDiscoverer(registry)
discoverer.scan_and_register()
result = registry.execute("data.forecast", {"params": {}})
```

## Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| params | dict | Execution parameters specific to this skill |
| context | dict | Optional context from calling agent |

## Example

```python
# Execute the skill
result = registry.execute("data.forecast", {
    "params": {},
    "context": {"source": "mission-control"}
})
print(result)
```
