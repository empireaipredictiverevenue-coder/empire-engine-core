---
type: skill
name: data.anomaly
version: "1.0"
description: Anomaly detection — flag unusual patterns across system and business metrics
tags: [data, anomaly, detection]
timeout_seconds: 30
max_retries: 2
---

# data.anomaly

Anomaly detection — flag unusual patterns across system and business metrics

## Overview

This skill provides capabilities for anomaly detection — flag unusual patterns across system and business metrics.
It integrates with the Empire AI agent system through the VaultSkillDiscoverer
and ImmutableSkillRegistry.

## Capabilities

- Detect statistical outliers in metric streams
- Flag sudden drops or spikes in key KPIs
- Correlate anomalies across multiple data sources
- Score and prioritize detected anomalies

## Usage

This skill is available to any agent in the Empire AI fleet with access to
the `data.anomaly` skill. Invoke it through the skills framework:

```python
from skills import ImmutableSkillRegistry, VaultSkillDiscoverer

registry = ImmutableSkillRegistry()
discoverer = VaultSkillDiscoverer(registry)
discoverer.scan_and_register()
result = registry.execute("data.anomaly", {"params": {}})
```

## Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| params | dict | Execution parameters specific to this skill |
| context | dict | Optional context from calling agent |

## Example

```python
# Execute the skill
result = registry.execute("data.anomaly", {
    "params": {},
    "context": {"source": "mission-control"}
})
print(result)
```
