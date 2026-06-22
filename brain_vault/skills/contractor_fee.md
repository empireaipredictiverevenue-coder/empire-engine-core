---
type: skill
name: contractor.fee
version: "1.0"
description: Fee management — calculate, track, and collect Empire's per-claim fees
tags: [contractor, fees, revenue]
timeout_seconds: 30
max_retries: 2
---

# contractor.fee

Fee management — calculate, track, and collect Empire's per-claim fees

## Overview

This skill provides capabilities for fee management — calculate, track, and collect empire's per-claim fees.
It integrates with the Empire AI agent system through the VaultSkillDiscoverer
and ImmutableSkillRegistry.

## Capabilities

- Calculate 3% fee on settled claims
- Track fee event lifecycle from creation to collection
- Generate fee collection reports by period
- Flag overdue fees for follow-up

## Usage

This skill is available to any agent in the Empire AI fleet with access to
the `contractor.fee` skill. Invoke it through the skills framework:

```python
from skills import ImmutableSkillRegistry, VaultSkillDiscoverer

registry = ImmutableSkillRegistry()
discoverer = VaultSkillDiscoverer(registry)
discoverer.scan_and_register()
result = registry.execute("contractor.fee", {"params": {}})
```

## Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| params | dict | Execution parameters specific to this skill |
| context | dict | Optional context from calling agent |

## Example

```python
# Execute the skill
result = registry.execute("contractor.fee", {
    "params": {},
    "context": {"source": "mission-control"}
})
print(result)
```
