---
type: skill
name: outreach.followup
version: "1.0"
description: Follow-up sequencing — design multi-touch follow-up cadences across channels
tags: [outreach, followup, sequences]
timeout_seconds: 30
max_retries: 2
---

# outreach.followup

Follow-up sequencing — design multi-touch follow-up cadences across channels

## Overview

This skill provides capabilities for follow-up sequencing — design multi-touch follow-up cadences across channels.
It integrates with the Empire AI agent system through the VaultSkillDiscoverer
and ImmutableSkillRegistry.

## Capabilities

- Design follow-up sequences with timing rules
- Multi-channel follow-up (SMS, email, call)
- Auto-escalate based on response signals
- Track sequence completion rates

## Usage

This skill is available to any agent in the Empire AI fleet with access to
the `outreach.followup` skill. Invoke it through the skills framework:

```python
from skills import ImmutableSkillRegistry, VaultSkillDiscoverer

registry = ImmutableSkillRegistry()
discoverer = VaultSkillDiscoverer(registry)
discoverer.scan_and_register()
result = registry.execute("outreach.followup", {"params": {}})
```

## Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| params | dict | Execution parameters specific to this skill |
| context | dict | Optional context from calling agent |

## Example

```python
# Execute the skill
result = registry.execute("outreach.followup", {
    "params": {},
    "context": {"source": "mission-control"}
})
print(result)
```
