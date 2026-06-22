---
type: skill
name: outreach.negotiate
version: "1.0"
description: Negotiation script — guide pricing and terms discussions with leads
tags: [outreach, negotiation, pricing]
timeout_seconds: 30
max_retries: 2
---

# outreach.negotiate

Negotiation script — guide pricing and terms discussions with leads

## Overview

This skill provides capabilities for negotiation script — guide pricing and terms discussions with leads.
It integrates with the Empire AI agent system through the VaultSkillDiscoverer
and ImmutableSkillRegistry.

## Capabilities

- Generate negotiation playbooks by niche
- Suggest discount and concession strategies
- Track negotiation outcomes and win rates
- Identify deal-killer patterns early

## Usage

This skill is available to any agent in the Empire AI fleet with access to
the `outreach.negotiate` skill. Invoke it through the skills framework:

```python
from skills import ImmutableSkillRegistry, VaultSkillDiscoverer

registry = ImmutableSkillRegistry()
discoverer = VaultSkillDiscoverer(registry)
discoverer.scan_and_register()
result = registry.execute("outreach.negotiate", {"params": {}})
```

## Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| params | dict | Execution parameters specific to this skill |
| context | dict | Optional context from calling agent |

## Example

```python
# Execute the skill
result = registry.execute("outreach.negotiate", {
    "params": {},
    "context": {"source": "mission-control"}
})
print(result)
```
