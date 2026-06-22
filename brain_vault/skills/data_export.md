---
type: skill
name: data.export
version: "1.0"
description: Data export — extract data from Supabase to CSV, JSON, or Parquet
tags: [data, export, etl]
timeout_seconds: 30
max_retries: 2
---

# data.export

Data export — extract data from Supabase to CSV, JSON, or Parquet

## Overview

This skill provides capabilities for data export — extract data from supabase to csv, json, or parquet.
It integrates with the Empire AI agent system through the VaultSkillDiscoverer
and ImmutableSkillRegistry.

## Capabilities

- Export arbitrary tables and queries to CSV
- Export with filters, sorting, and column selection
- Schedule recurring data exports
- Compress and archive exported files

## Usage

This skill is available to any agent in the Empire AI fleet with access to
the `data.export` skill. Invoke it through the skills framework:

```python
from skills import ImmutableSkillRegistry, VaultSkillDiscoverer

registry = ImmutableSkillRegistry()
discoverer = VaultSkillDiscoverer(registry)
discoverer.scan_and_register()
result = registry.execute("data.export", {"params": {}})
```

## Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| params | dict | Execution parameters specific to this skill |
| context | dict | Optional context from calling agent |

## Example

```python
# Execute the skill
result = registry.execute("data.export", {
    "params": {},
    "context": {"source": "mission-control"}
})
print(result)
```
