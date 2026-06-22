---
type: skill
name: contractor.enrich
version: "1.0"
description: Contractor enrichment — research and append intel on contractors
tags: [contractor, enrichment, intel]
timeout_seconds: 30
max_retries: 2
---

# contractor.enrich

Contractor enrichment — research and append intel on contractors

## Overview

This skill provides capabilities for contractor enrichment — research and append intel on contractors.
It integrates with the Empire AI agent system through the VaultSkillDiscoverer
and ImmutableSkillRegistry.

## Capabilities

- Research contractor licenses and credentials
- Look up reviews and reputation signals
- Verify insurance and bonding status
- Enrich with social media and web presence

## Usage

This skill is available to any agent in the Empire AI fleet with access to
the `contractor.enrich` skill. Invoke it through the skills framework:

```python
from skills import ImmutableSkillRegistry, VaultSkillDiscoverer

registry = ImmutableSkillRegistry()
discoverer = VaultSkillDiscoverer(registry)
discoverer.scan_and_register()
result = registry.execute("contractor.enrich", {"params": {}})
```

## Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| params | dict | Execution parameters specific to this skill |
| context | dict | Optional context from calling agent |

## Example

```python
# Execute the skill
result = registry.execute("contractor.enrich", {
    "params": {},
    "context": {"source": "mission-control"}
})
print(result)
```
