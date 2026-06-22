---
type: skill
name: data.enrich
version: "1.0"
description: Data enrichment — augment records with external data sources and computed fields
tags: [data, enrichment, enhancement]
timeout_seconds: 30
max_retries: 2
---

# data.enrich

Data enrichment — augment records with external data sources and computed fields

## Overview

This skill provides capabilities for data enrichment — augment records with external data sources and computed fields.
It integrates with the Empire AI agent system through the VaultSkillDiscoverer
and ImmutableSkillRegistry.

## Capabilities

- Enrich leads with geographic and demographic data
- Append company info from business databases
- Compute derived fields from existing data
- Batch enrich through external API integrations

## Usage

This skill is available to any agent in the Empire AI fleet with access to
the `data.enrich` skill. Invoke it through the skills framework:

```python
from skills import ImmutableSkillRegistry, VaultSkillDiscoverer

registry = ImmutableSkillRegistry()
discoverer = VaultSkillDiscoverer(registry)
discoverer.scan_and_register()
result = registry.execute("data.enrich", {"params": {}})
```

## Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| params | dict | Execution parameters specific to this skill |
| context | dict | Optional context from calling agent |

## Example

```python
# Execute the skill
result = registry.execute("data.enrich", {
    "params": {},
    "context": {"source": "mission-control"}
})
print(result)
```
