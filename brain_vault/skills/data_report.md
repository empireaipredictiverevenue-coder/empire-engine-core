---
type: skill
name: data.report
version: "1.0"
description: Report generation — build structured reports from query results and templates
tags: [data, reporting, documentation]
timeout_seconds: 30
max_retries: 2
---

# data.report

Report generation — build structured reports from query results and templates

## Overview

This skill provides capabilities for report generation — build structured reports from query results and templates.
It integrates with the Empire AI agent system through the VaultSkillDiscoverer
and ImmutableSkillRegistry.

## Capabilities

- Generate PDF reports from SQL queries
- Build HTML dashboards with formatted tables
- Schedule recurring report delivery via email
- Export reports in PDF, HTML, and Markdown formats

## Usage

This skill is available to any agent in the Empire AI fleet with access to
the `data.report` skill. Invoke it through the skills framework:

```python
from skills import ImmutableSkillRegistry, VaultSkillDiscoverer

registry = ImmutableSkillRegistry()
discoverer = VaultSkillDiscoverer(registry)
discoverer.scan_and_register()
result = registry.execute("data.report", {"params": {}})
```

## Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| params | dict | Execution parameters specific to this skill |
| context | dict | Optional context from calling agent |

## Example

```python
# Execute the skill
result = registry.execute("data.report", {
    "params": {},
    "context": {"source": "mission-control"}
})
print(result)
```
