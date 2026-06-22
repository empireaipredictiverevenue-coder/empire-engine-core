---
type: skill
name: outreach.email
version: "1.0"
description: Email campaign management — design, send, and track email sequences
tags: [outreach, email, marketing]
timeout_seconds: 30
max_retries: 2
---

# outreach.email

Email campaign management — design, send, and track email sequences

## Overview

This skill provides capabilities for email campaign management — design, send, and track email sequences.
It integrates with the Empire AI agent system through the VaultSkillDiscoverer
and ImmutableSkillRegistry.

## Capabilities

- Design email templates with dynamic content
- Send transactional and bulk email campaigns
- Track opens, clicks, and bounce rates
- Manage unsubscribe lists and domain reputation

## Usage

This skill is available to any agent in the Empire AI fleet with access to
the `outreach.email` skill. Invoke it through the skills framework:

```python
from skills import ImmutableSkillRegistry, VaultSkillDiscoverer

registry = ImmutableSkillRegistry()
discoverer = VaultSkillDiscoverer(registry)
discoverer.scan_and_register()
result = registry.execute("outreach.email", {"params": {}})
```

## Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| params | dict | Execution parameters specific to this skill |
| context | dict | Optional context from calling agent |

## Example

```python
# Execute the skill
result = registry.execute("outreach.email", {
    "params": {},
    "context": {"source": "mission-control"}
})
print(result)
```
