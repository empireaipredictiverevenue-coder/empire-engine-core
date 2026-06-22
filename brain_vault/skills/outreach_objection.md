---
type: skill
name: outreach.objection
version: "1.0"
description: Objection handling — identify, categorize, and respond to common sales objections
tags: [outreach, objections, sales]
timeout_seconds: 30
max_retries: 2
---

# outreach.objection

Objection handling — identify, categorize, and respond to common sales objections

## Overview

This skill provides capabilities for objection handling — identify, categorize, and respond to common sales objections.
It integrates with the Empire AI agent system through the VaultSkillDiscoverer
and ImmutableSkillRegistry.

## Capabilities

- Categorize objection types from replies
- Generate tailored objection responses
- Track objection frequency by niche and channel
- Recommend objection prevention strategies

## Usage

This skill is available to any agent in the Empire AI fleet with access to
the `outreach.objection` skill. Invoke it through the skills framework:

```python
from skills import ImmutableSkillRegistry, VaultSkillDiscoverer

registry = ImmutableSkillRegistry()
discoverer = VaultSkillDiscoverer(registry)
discoverer.scan_and_register()
result = registry.execute("outreach.objection", {"params": {}})
```

## Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| params | dict | Execution parameters specific to this skill |
| context | dict | Optional context from calling agent |

## Example

```python
# Execute the skill
result = registry.execute("outreach.objection", {
    "params": {},
    "context": {"source": "mission-control"}
})
print(result)
```
