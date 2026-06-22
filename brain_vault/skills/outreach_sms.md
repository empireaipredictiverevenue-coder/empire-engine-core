---
type: skill
name: outreach.sms
version: "1.0"
description: SMS campaign management — compose, send, and track bulk text message campaigns
tags: [outreach, sms, messaging]
timeout_seconds: 30
max_retries: 2
---

# outreach.sms

SMS campaign management — compose, send, and track bulk text message campaigns

## Overview

This skill provides capabilities for sms campaign management — compose, send, and track bulk text message campaigns.
It integrates with the Empire AI agent system through the VaultSkillDiscoverer
and ImmutableSkillRegistry.

## Capabilities

- Compose SMS messages with personalization tokens
- Send to segmented contact lists
- Track delivery, read, and reply rates
- Manage opt-out lists and compliance

## Usage

This skill is available to any agent in the Empire AI fleet with access to
the `outreach.sms` skill. Invoke it through the skills framework:

```python
from skills import ImmutableSkillRegistry, VaultSkillDiscoverer

registry = ImmutableSkillRegistry()
discoverer = VaultSkillDiscoverer(registry)
discoverer.scan_and_register()
result = registry.execute("outreach.sms", {"params": {}})
```

## Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| params | dict | Execution parameters specific to this skill |
| context | dict | Optional context from calling agent |

## Example

```python
# Execute the skill
result = registry.execute("outreach.sms", {
    "params": {},
    "context": {"source": "mission-control"}
})
print(result)
```
