---
type: skill
name: data.import
version: "1.0"
description: Data import — load CSV, JSON, or Excel files into Supabase tables
tags: [data, import, etl]
timeout_seconds: 30
max_retries: 2
---

# data.import

Data import — load CSV, JSON, or Excel files into Supabase tables

## Overview

This skill provides capabilities for data import — load csv, json, or excel files into supabase tables.
It integrates with the Empire AI agent system through the VaultSkillDiscoverer
and ImmutableSkillRegistry.

## Capabilities

- Import CSV files with header mapping
- Validate data types and constraints before import
- Handle duplicate detection and upsert logic
- Roll back failed imports cleanly

## Usage

This skill is available to any agent in the Empire AI fleet with access to
the `data.import` skill. Invoke it through the skills framework:

```python
from skills import ImmutableSkillRegistry, VaultSkillDiscoverer

registry = ImmutableSkillRegistry()
discoverer = VaultSkillDiscoverer(registry)
discoverer.scan_and_register()
result = registry.execute("data.import", {"params": {}})
```

## Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| params | dict | Execution parameters specific to this skill |
| context | dict | Optional context from calling agent |

## Example

```python
# Execute the skill
result = registry.execute("data.import", {
    "params": {},
    "context": {"source": "mission-control"}
})
print(result)
```
