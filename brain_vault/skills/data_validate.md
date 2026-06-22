---
type: skill
name: data.validate
version: "1.0"
description: Data validation — check data quality, completeness, and consistency
tags: [data, validation, quality]
timeout_seconds: 30
max_retries: 2
---

# data.validate

Data validation — check data quality, completeness, and consistency

## Overview

This skill provides capabilities for data validation — check data quality, completeness, and consistency.
It integrates with the Empire AI agent system through the VaultSkillDiscoverer
and ImmutableSkillRegistry.

## Capabilities

- Check for missing values and nulls across datasets
- Validate data types and format constraints
- Detect outliers and distribution anomalies
- Generate data quality scorecards

## Usage

This skill is available to any agent in the Empire AI fleet with access to
the `data.validate` skill. Invoke it through the skills framework:

```python
from skills import ImmutableSkillRegistry, VaultSkillDiscoverer

registry = ImmutableSkillRegistry()
discoverer = VaultSkillDiscoverer(registry)
discoverer.scan_and_register()
result = registry.execute("data.validate", {"params": {}})
```

## Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| params | dict | Execution parameters specific to this skill |
| context | dict | Optional context from calling agent |

## Example

```python
# Execute the skill
result = registry.execute("data.validate", {
    "params": {},
    "context": {"source": "mission-control"}
})
print(result)
```
