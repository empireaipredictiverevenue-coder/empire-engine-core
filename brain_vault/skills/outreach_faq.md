---
type: skill
name: outreach.faq
version: "1.0"
description: FAQ management — build and maintain auto-response knowledge base
tags: [outreach, faq, knowledge-base]
timeout_seconds: 30
max_retries: 2
---

# outreach.faq

FAQ management — build and maintain auto-response knowledge base

## Overview

This skill provides capabilities for faq management — build and maintain auto-response knowledge base.
It integrates with the Empire AI agent system through the VaultSkillDiscoverer
and ImmutableSkillRegistry.

## Capabilities

- Create FAQ entries from common questions
- Auto-match inbound questions to FAQ answers
- Track FAQ effectiveness and update stale entries
- Generate FAQ suggestions from support logs

## Usage

This skill is available to any agent in the Empire AI fleet with access to
the `outreach.faq` skill. Invoke it through the skills framework:

```python
from skills import ImmutableSkillRegistry, VaultSkillDiscoverer

registry = ImmutableSkillRegistry()
discoverer = VaultSkillDiscoverer(registry)
discoverer.scan_and_register()
result = registry.execute("outreach.faq", {"params": {}})
```

## Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| params | dict | Execution parameters specific to this skill |
| context | dict | Optional context from calling agent |

## Example

```python
# Execute the skill
result = registry.execute("outreach.faq", {
    "params": {},
    "context": {"source": "mission-control"}
})
print(result)
```
