---
type: skill
name: contractor.route
version: "1.0"
description: Lead routing — dispatch qualified leads to the right contractor pipeline
tags: [contractor, routing, dispatch]
timeout_seconds: 30
max_retries: 2
---

# contractor.route

Lead routing — dispatch qualified leads to the right contractor pipeline

## Overview

This skill provides capabilities for lead routing — dispatch qualified leads to the right contractor pipeline.
It integrates with the Empire AI agent system through the VaultSkillDiscoverer
and ImmutableSkillRegistry.

## Capabilities

- Route leads by niche, metro, and urgency
- Apply round-robin or score-based distribution
- Track acceptance and rejection rates
- Re-route unaccepted leads automatically

## Usage

This skill is available to any agent in the Empire AI fleet with access to
the `contractor.route` skill. Invoke it through the skills framework:

```python
from skills import ImmutableSkillRegistry, VaultSkillDiscoverer

registry = ImmutableSkillRegistry()
discoverer = VaultSkillDiscoverer(registry)
discoverer.scan_and_register()
result = registry.execute("contractor.route", {"params": {}})
```

## Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| params | dict | Execution parameters specific to this skill |
| context | dict | Optional context from calling agent |

## Example

```python
# Execute the skill
result = registry.execute("contractor.route", {
    "params": {},
    "context": {"source": "mission-control"}
})
print(result)
```
