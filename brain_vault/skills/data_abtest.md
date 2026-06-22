---
type: skill
name: data.abtest
version: "1.0"
description: A/B test analysis — design, measure, and interpret split tests
tags: [data, ab-test, experimentation]
timeout_seconds: 30
max_retries: 2
---

# data.abtest

A/B test analysis — design, measure, and interpret split tests

## Overview

This skill provides capabilities for a/b test analysis — design, measure, and interpret split tests.
It integrates with the Empire AI agent system through the VaultSkillDiscoverer
and ImmutableSkillRegistry.

## Capabilities

- Design A/B test variants and allocation
- Calculate statistical significance and power
- Analyze results across multiple metrics
- Recommend winning variant with confidence level

## Usage

This skill is available to any agent in the Empire AI fleet with access to
the `data.abtest` skill. Invoke it through the skills framework:

```python
from skills import ImmutableSkillRegistry, VaultSkillDiscoverer

registry = ImmutableSkillRegistry()
discoverer = VaultSkillDiscoverer(registry)
discoverer.scan_and_register()
result = registry.execute("data.abtest", {"params": {}})
```

## Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| params | dict | Execution parameters specific to this skill |
| context | dict | Optional context from calling agent |

## Example

```python
# Execute the skill
result = registry.execute("data.abtest", {
    "params": {},
    "context": {"source": "mission-control"}
})
print(result)
```
