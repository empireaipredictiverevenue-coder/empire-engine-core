---
type: skill
name: data.csv
version: "1.0"
description: CSV processing — parse, transform, filter, and aggregate CSV data
tags: [data, csv, processing]
timeout_seconds: 30
max_retries: 2
---

# data.csv

CSV processing — parse, transform, filter, and aggregate CSV data

## Overview

This skill provides capabilities for csv processing — parse, transform, filter, and aggregate csv data.
It integrates with the Empire AI agent system through the VaultSkillDiscoverer
and ImmutableSkillRegistry.

## Capabilities

- Parse CSV with automatic type detection
- Filter rows by conditions across columns
- Aggregate and pivot tabular data
- Merge multiple CSV files by key columns

## Usage

This skill is available to any agent in the Empire AI fleet with access to
the `data.csv` skill. Invoke it through the skills framework:

```python
from skills import ImmutableSkillRegistry, VaultSkillDiscoverer

registry = ImmutableSkillRegistry()
discoverer = VaultSkillDiscoverer(registry)
discoverer.scan_and_register()
result = registry.execute("data.csv", {"params": {}})
```

## Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| params | dict | Execution parameters specific to this skill |
| context | dict | Optional context from calling agent |

## Example

```python
# Execute the skill
result = registry.execute("data.csv", {
    "params": {},
    "context": {"source": "mission-control"}
})
print(result)
```
